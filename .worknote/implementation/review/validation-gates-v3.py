"""Exercise fixture version checks and guide checks with explicit fakes."""

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / ".worknote/implementation/review/input-v3"
sys.path.insert(0, str(SNAPSHOT))
sys.stdout.reconfigure(encoding="utf-8")


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, SNAPSHOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cluster = load("review_cluster_v3", "tests/integration/test_cluster.py")
guide = load("review_guide_v3", "examples/quickstart.py")


def record(name, **values):
    print(json.dumps({"probe": name, "optimize": sys.flags.optimize,
                      **values}, ensure_ascii=False))


class Namespaces:
    def __init__(self, calls):
        self.calls = calls

    def create(self, body):
        self.calls.append("namespace.create")
        return {"metadata": {"uid": "namespace-uid"}}

    def delete(self, *args, **kwargs):
        self.calls.append("namespace.delete")

    def wait_deleted(self, *args, **kwargs):
        self.calls.append("namespace.wait_deleted")


class Secrets:
    def __init__(self, calls, failure):
        self.calls = calls
        self.failure = failure
        self.applies = 0

    def apply(self, body):
        self.calls.append("secret.apply")
        self.applies += 1
        uid = "secret-uid"
        if self.failure == "reapply" and self.applies == 2:
            uid = "replacement-uid"
        return {"metadata": {"uid": uid}}

    def get(self, name):
        self.calls.append("secret.get")
        value = "wrong" if self.failure == "roundtrip" else "ZXhhbXBsZQ=="
        return {"data": {"username": value}}

    def delete(self, *args, **kwargs):
        self.calls.append("secret.delete")
        action = "wrong" if self.failure == "delete" else "requested"
        return SimpleNamespace(action=action)

    def wait_deleted(self, *args, **kwargs):
        self.calls.append("secret.wait_deleted")

    def exists(self, name):
        self.calls.append("secret.exists")
        return self.failure == "exists"


class FakeClient:
    def __init__(self, actual_version="v1.37.1", failure=None):
        self.calls = []
        self.namespaces = Namespaces(self.calls)
        self.secrets = Secrets(self.calls, failure)
        self._dynamic_client = SimpleNamespace(
            version={"kubernetes": {"gitVersion": actual_version}},
        )

    def resource(self, *args, **kwargs):
        return self.secrets

    def close(self):
        self.calls.append("client.close")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


for actual in ("v1.37.1", "v1.37.0", "v1.36.4", "v1.37.1+other"):
    fake = FakeClient(actual_version=actual)
    with patch.dict(os.environ, {
        "KUBERNETES_CLIENT_TEST_CONFIG": "fake-config",
        "KUBERNETES_CLIENT_TEST_SERVER_VERSION": "v1.37.1",
    }):
        with patch.object(cluster.KubernetesClient, "from_kubeconfig",
                          return_value=fake):
            try:
                cluster.ClusterTests.setUpClass()
                error = None
            except Exception as cause:
                error = type(cause).__name__
            finally:
                cluster.ClusterTests.doClassCleanups()
    expected_error = None if actual == "v1.37.1" else "AssertionError"
    if error != expected_error:
        raise RuntimeError(f"Unexpected version-check result: {actual}: {error}")
    record("exact_server_version", actual=actual, error=error, calls=fake.calls)

for failure in (None, "roundtrip", "reapply", "delete", "exists"):
    fake = FakeClient(failure=failure)
    with patch.object(guide.KubernetesClient, "from_kubeconfig",
                      return_value=fake):
        try:
            guide.run("fake-config", "guide-fake")
            error = None
        except Exception as cause:
            error = type(cause).__name__
    expected_error = None if failure is None else "RuntimeError"
    if error != expected_error:
        raise RuntimeError(f"Unexpected guide result: {failure}: {error}")
    if fake.calls[-3:] != ["namespace.delete", "namespace.wait_deleted",
                          "client.close"]:
        raise RuntimeError("Guide cleanup was not executed")
    if failure is None and fake.calls.count("secret.apply") != 2:
        raise RuntimeError("Optimized guide omitted repeated apply")
    if failure is None and "secret.exists" not in fake.calls:
        raise RuntimeError("Optimized guide omitted exists check")
    record("guide_validation", failure=failure, error=error, calls=fake.calls)
