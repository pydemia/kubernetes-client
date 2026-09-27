"""Use real sockets to detect HTTP retries and blocked stream cleanup."""

import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from kubernetes.client import Configuration
from urllib3.exceptions import HTTPError

from kubernetes_client import KubernetesClient
from test_interface import Wire


class SocketTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.started = threading.Event()
        self.release = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_PUT(self):
                self.disconnect()

            def do_DELETE(self):
                self.disconnect()

            def disconnect(self):
                owner.requests.append(self.command)
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                self.close_connection = True

            def do_GET(self):
                owner.requests.append("GET")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                payload = (
                    json.dumps(
                        {
                            "type": "BOOKMARK",
                            "object": {
                                "metadata": {"resourceVersion": "opaque"},
                            },
                        }
                    ).encode()
                    + b"\n"
                )
                self.wfile.write(f"{len(payload):x}\r\n".encode())
                self.wfile.write(payload + b"\r\n")
                self.wfile.flush()
                owner.started.set()
                owner.release.wait(5)
                self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.worker = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.worker.start()
        self.addCleanup(self.finish)
        self.client = KubernetesClient.from_configuration(
            Configuration(host=f"http://127.0.0.1:{self.server.server_port}"),
            request_timeout=(1, 1),
        )
        pool = self.client.api_client.rest_client.pool_manager
        actual = pool.request
        wire = Wire()

        def request(method, url, **options):
            path = urlsplit(url).path
            if path in ("/version", "/apis", "/api/v1"):
                return wire.request(method, url, **options)
            return actual(method, url, **options)

        pool.request = request

    def finish(self):
        self.release.set()
        self.client.close()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)

    def test_put_and_delete_disconnect_are_not_replayed(self):
        with self.assertRaises(HTTPError):
            self.client.config_maps.replace(
                {
                    "metadata": {
                        "name": "demo",
                        "resourceVersion": "rv",
                    }
                }
            )
        with self.assertRaises(HTTPError):
            self.client.config_maps.delete("demo")
        self.assertEqual(self.requests, ["PUT", "DELETE"])

    def test_stop_unblocks_idle_watch_and_cleans_up(self):
        received = threading.Event()
        ended = threading.Event()
        errors = []
        stream = self.client.pods.watch()

        def consume():
            try:
                with stream:
                    for event in stream:
                        received.set()
            except HTTPError:
                # Socket shutdown can surface an incomplete chunked response.
                pass
            except Exception as error:
                errors.append(error)
            finally:
                ended.set()

        consumer = threading.Thread(target=consume, daemon=True)
        consumer.start()
        self.assertTrue(received.wait(2))
        stream.stop()
        self.assertTrue(ended.wait(2))
        consumer.join(2)
        self.assertEqual(errors, [])
        self.assertFalse(self.client._streams)
        self.assertEqual(self.requests, ["GET"])

    def test_idle_watch_honors_socket_read_timeout(self):
        with self.assertRaises(HTTPError):
            with self.client.pods.watch() as stream:
                list(stream)
        self.assertTrue(self.started.is_set())
        self.assertFalse(self.client._streams)
        self.assertEqual(self.requests, ["GET"])


if __name__ == "__main__":
    unittest.main()
