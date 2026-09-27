"""Read-only probes for the fixed SDK review input."""

import hashlib
import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input-v1"
sys.path[:0] = [str(INPUT), str(INPUT / "tests")]

import kubernetes
import pydantic
import urllib3
from kubernetes.client import ApiClient, Configuration
from urllib3.util import Retry

from kubernetes_client import KubernetesClient
from test_interface import Wire, response


def emit(name, value):
    print(json.dumps({"probe": name, "result": value}, ensure_ascii=False))


def run_wire(name, wire, operation):
    with KubernetesClient.from_configuration(
        Configuration(host="https://review.invalid")
    ) as client:
        client.api_client.rest_client.pool_manager.request = wire.request
        try:
            value = operation(client)
            result = {"value": value}
        except Exception as error:
            result = {
                "exception": type(error).__name__,
                "message": str(error),
                "status": getattr(error, "status", None),
            }
        result["routes"] = [call[1] for call in wire.calls]
        emit(name, result)


class UnrelatedFailure(Wire):
    def request(self, method, url, **options):
        if urlsplit(url).path == "/apis/apps/v1":
            self.calls.append((method, "/apis/apps/v1", {}, options))
            result = response({"reason": "ServiceUnavailable"}, 503)
            self.responses.append(result)
            return result
        return super().request(method, url, **options)


class Malformed(Wire):
    def __init__(self, target, body):
        super().__init__()
        self.target = target
        self.body = body

    def request(self, method, url, **options):
        if urlsplit(url).path == self.target:
            self.calls.append((method, self.target, {}, options))
            result = response(self.body)
            self.responses.append(result)
            return result
        return super().request(method, url, **options)


def transport_disconnect(*, borrowed_retry, method):
    writes = []

    class Stub(BaseHTTPRequestHandler):
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
            route = urlsplit(self.path).path
            if route == "/version":
                self.send_json({"gitVersion": "v1.37.0"})
            elif route == "/apis":
                self.send_json({"kind": "APIGroupList", "groups": []})
            elif route == "/api/v1":
                self.send_json({"kind": "APIResourceList", "resources": [{
                    "name": "configmaps", "kind": "ConfigMap",
                    "namespaced": True, "verbs": ["get", "update", "delete"],
                }]})
            else:
                self.send_json({"metadata": {"name": "demo"}})

        def do_PUT(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            writes.append(self.path)
            if len(writes) == 1:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.send_json({"metadata": {"name": "demo"}})

        do_DELETE = do_PUT

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    configuration = Configuration(
        host=f"http://127.0.0.1:{server.server_port}"
    )
    configuration.retries = 0
    client = None if borrowed_retry else (
        KubernetesClient.from_configuration(configuration)
    )
    api = ApiClient(configuration) if borrowed_retry else client.api_client
    manager = api.rest_client.pool_manager
    pool = manager.connection_from_url(configuration.host)
    if borrowed_retry:
        pool.retries = Retry(total=1, read=1, allowed_methods={method})
    result = {
        "manager_retries": str(manager.connection_pool_kw["retries"]),
        "pool_retries_total": pool.retries.total,
    }
    try:
        client = client or KubernetesClient.from_api_client(api)
        with client:
            result["accepted"] = True
            try:
                if method == "PUT":
                    result["response"] = client.config_maps.replace({
                        "metadata": {"name": "demo", "resourceVersion": "1"}
                    })
                else:
                    deletion = client.config_maps.delete("demo")
                    result["response"] = deletion.action
            except Exception as error:
                result["exception"] = type(error).__name__
        result["wire_request_count"] = len(writes)
    finally:
        api.close()
        manager.clear()
        server.shutdown()
        server.server_close()
        thread.join()
    ownership = "borrowed_existing_pool_retry" if borrowed_retry else (
        "owned_no_retry_disconnect"
    )
    emit(f"{ownership}_{method}", result)


emit("sdk", kubernetes.__version__)
emit("runtime", {"python": sys.version, "pydantic": pydantic.__version__,
                 "urllib3": urllib3.__version__})
entries = (ROOT / "input-v1.sha256").read_text().splitlines()
matched = all(
    hashlib.sha256((INPUT / path.replace("\\", "/")).read_bytes())
    .hexdigest().upper() == digest
    for digest, path in (entry.split(" ", 1) for entry in entries)
)
emit("snapshot_hashes", matched)
run_wire("core_unrelated_group_503", UnrelatedFailure(),
         lambda client: client.config_maps.get("demo"))
run_wire("synthetic_list_kind", Wire(),
         lambda client: client.resource("v1", "ConfigMapList").get("demo"))
run_wire("malformed_core_resource_kind", Malformed("/api/v1", {
    "kind": "APIResourceList",
    "resources": [{"name": "configmaps", "kind": "", "namespaced": True,
                   "verbs": ["get"]}],
}), lambda client: client.config_maps.get("demo"))
run_wire("malformed_preferred_version", Malformed("/apis", {
    "kind": "APIGroupList",
    "groups": [{"name": "apps", "versions": [{
        "groupVersion": "apps/v1", "version": "v1"
    }], "preferredVersion": {}}],
}), lambda client: client.deployments.get("demo"))
run_wire("missing_discovery_kind", Malformed("/api/v1", {
    "resources": [],
}), lambda client: client.config_maps.get("demo"))
for verb in ("PUT", "DELETE"):
    transport_disconnect(borrowed_retry=True, method=verb)
    transport_disconnect(borrowed_retry=False, method=verb)
