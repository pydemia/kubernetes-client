"""Local HTTP probes without modifying the reviewed source."""

import json
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread


ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / ".worknote/implementation/review/input-v2"
sys.path.insert(0, str(SNAPSHOT))
sys.stdout.reconfigure(encoding="utf-8")

import kubernetes
from kubernetes.client import Configuration
from kubernetes_client import KubernetesClient


def record(name, **values):
    print(json.dumps({"probe": name, **values}, ensure_ascii=False))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    calls = []
    idle_entered = Event()
    idle_release = Event()

    def log_message(self, *args):
        pass

    def send_json(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        type(self).calls.append(("GET", self.path))
        route = self.path.split("?", 1)[0]
        if route == "/version":
            self.send_json({"gitVersion": "v1.37.0"})
        elif route == "/apis":
            self.send_json({"kind": "APIGroupList", "groups": []})
        elif route == "/api/v1":
            self.send_json({"kind": "APIResourceList", "resources": [
                {"name": name, "kind": kind, "namespaced": True,
                 "verbs": ["get", "list", "create", "update", "patch",
                           "delete", "watch"]}
                for name, kind in (
                    ("configmaps", "ConfigMap"), ("pods", "Pod"),
                )
            ]})
        elif route.endswith("/pods"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.flush()
            type(self).idle_entered.set()
            type(self).idle_release.wait(3)
            try:
                self.wfile.write(b"0\r\n\r\n")
            except (OSError, ConnectionError):
                pass
        else:
            type(self).idle_entered.set()
            type(self).idle_release.wait(3)
            try:
                self.send_json({"metadata": {"uid": "uid"}, "status": {
                    "conditions": [{"type": "Ready", "status": "True"}]
                }})
            except (OSError, ConnectionError):
                pass

    def disconnect(self):
        type(self).calls.append((self.command, self.path))
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.connection.shutdown(socket.SHUT_RDWR)
        self.connection.close()
        self.close_connection = True

    do_PUT = disconnect
    do_DELETE = disconnect


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
server.daemon_threads = True
server_thread = Thread(target=server.serve_forever, daemon=True)
server_thread.start()
host = f"http://127.0.0.1:{server.server_address[1]}"
record("input", sdk=kubernetes.__version__, host=host)
try:
    with KubernetesClient.from_configuration(
        Configuration(host=host), request_timeout=(0.2, 0.2),
    ) as client:
        resource = client.config_maps
        resource._resolve("update")
        for method, operation in (
            ("PUT", lambda: resource.replace({"metadata": {
                "name": "demo", "resourceVersion": "rv"}})),
            ("DELETE", lambda: resource.delete("demo")),
        ):
            try:
                operation()
                error = None
            except Exception as cause:
                error = type(cause).__name__
            count = sum(call[0] == method for call in Handler.calls)
            assert count == 1, (method, count)
            record("disconnect_no_retry", method=method, calls=count,
                   error=error)

        client.pods._resolve("get")
        started = time.monotonic()
        try:
            client.pods.wait_ready("demo", timeout_seconds=0.05)
            error = None
        except Exception as cause:
            error = type(cause).__name__
        record("wait_idle_timeout", error=error,
               elapsed=round(time.monotonic() - started, 3),
               object_gets=sum(call[1].split("?", 1)[0].endswith("/pods/demo")
                               for call in Handler.calls))
        Handler.idle_release.set()

        Handler.idle_entered.clear()
        Handler.idle_release.clear()
        stream = client.pods.watch()
        body_read_entered = Event()
        original_fetch = stream._fetch

        def fetch(**options):
            result = original_fetch(**options)
            original_stream = result.stream

            def chunks(**arguments):
                body_read_entered.set()
                yield from original_stream(**arguments)

            result.stream = chunks
            return result

        stream._fetch = fetch
        reader_result = []

        def read():
            try:
                reader_result.append({"events": list(stream)})
            except Exception as cause:
                reader_result.append({"error": type(cause).__name__,
                                      "message": str(cause)})

        reader = Thread(target=read, daemon=True)
        reader.start()
        assert body_read_entered.wait(3), "Watch body read was not reached"
        try:
            stream.stop()
            stop_error = None
        except Exception as cause:
            stop_error = type(cause).__name__ + ": " + str(cause)
        Handler.idle_release.set()
        reader.join(3)
        record("watch_idle_stop", stop_error=stop_error,
               reader_alive=reader.is_alive(), reader_result=reader_result,
               closed=stream._closed, registered=len(client._streams))
finally:
    Handler.idle_release.set()
    server.shutdown()
    server.server_close()
    server_thread.join(3)
