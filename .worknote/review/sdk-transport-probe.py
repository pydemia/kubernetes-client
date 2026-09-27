import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

import kubernetes
import pydantic
import urllib3
from kubernetes.client import ApiClient, Configuration
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.resource import Resource, ResourceInstance
from urllib3.response import HTTPResponse


print("Python", sys.version)
print(
    "versions", kubernetes.__version__, urllib3.__version__,
    pydantic.__version__,
)


def resp(body, status=200):
    return HTTPResponse(
        body=json.dumps(body).encode(), status=status,
        headers={"Content-Type": "application/json"}, preload_content=False,
    )


api = ApiClient(Configuration(host="https://unit.invalid"))
api.rest_client.pool_manager.request = Mock(
    side_effect=lambda *a, **k: resp({
        "apiVersion": "v1", "kind": "Status", "status": "Success",
    })
)
dyn = object.__new__(DynamicClient)
dyn.client = api
dyn.configuration = api.configuration
dyn.request(
    "patch", "/apis/example.com/v1/namespaces/n/widgets/w",
    body={"spec": {"x": 1}}, field_validation="Strict", serialize=False,
)
a, k = api.rest_client.pool_manager.request.call_args
url = a[1]
print("field_validation keyword URL:", url, "fields:", k.get("fields"))
assert "fieldValidation" not in url
assert "fieldValidation" not in str(k.get("fields"))
dyn.request(
    "patch", "/apis/example.com/v1/namespaces/n/widgets/w",
    body={"spec": {"x": 1}},
    query_params=[("fieldValidation", "Strict")], serialize=False,
)
a, k = api.rest_client.pool_manager.request.call_args
print("query_params URL:", a[1])
assert "fieldValidation=Strict" in a[1]
r = Resource(
    prefix="apis", group="example.com", api_version="v1", kind="Widget",
    namespaced=True, name="widgets", verbs=["get", "patch"], client=dyn,
)
dyn.patch(
    r, body=[], name="w", namespace="n",
    content_type="application/json-patch+json", serialize=False,
)
a, k = api.rest_client.pool_manager.request.call_args
print(
    "empty JSONPatch wire body:", k["body"], "Content-Type:",
    k["headers"]["Content-Type"],
)
assert k["body"] == "{}"
assert k["headers"]["Content-Type"] == (
    "application/strategic-merge-patch+json"
)
dyn.request(
    "patch", r.path(name="w", namespace="n"), body=[],
    content_type="application/json-patch+json", serialize=False,
)
a, k = api.rest_client.pool_manager.request.call_args
print(
    "direct request wire body:", k["body"], "Content-Type:",
    k["headers"]["Content-Type"],
)
assert k["body"] == "[]"
assert k["headers"]["Content-Type"] == "application/json-patch+json"
api.close()
api.rest_client.pool_manager.clear()

api = ApiClient(Configuration(host="https://unit.invalid"))
count = []


def discovery_request(method, url, **kwargs):
    path = url.split("unit.invalid")[-1]
    count.append(path)
    if path == "/version":
        return resp({"gitVersion": "v1.37.0"})
    if path == "/apis":
        return resp({
            "apiVersion": "v1", "kind": "APIGroupList",
            "groups": [{
                "name": "example.com",
                "versions": [{
                    "groupVersion": "example.com/v1", "version": "v1",
                }],
                "preferredVersion": {
                    "groupVersion": "example.com/v1", "version": "v1",
                },
            }],
        })
    if path == "/apis/example.com/v1":
        return resp({
            "apiVersion": "v1", "kind": "Status", "status": "Failure",
            "code": 503, "reason": "ServiceUnavailable",
            "message": "unavailable",
        }, 503)
    raise AssertionError(path)


api.rest_client.pool_manager.request = discovery_request
with tempfile.TemporaryDirectory() as temp:
    dyn = DynamicClient(api, cache_file=str(Path(temp) / "discovery.json"))
    try:
        dyn.resources.get(api_version="example.com/v1", kind="Widget")
    except Exception as e:
        print("discovery 503 outcome:", type(e).__name__, str(e))
        assert type(e).__name__ == "ResourceNotFoundError"
    else:
        raise AssertionError("expected error")
    print("discovery requests:", count)
api.close()
api.rest_client.pool_manager.clear()

original = {
    "apiVersion": "example.com/v1", "kind": "WidgetList",
    "metadata": {"resourceVersion": "10"},
    "items": [{
        "metadata": {"name": "w"},
        "spec": {"unknown": {"nested": None, "empty": []}},
    }],
}
actual = ResourceInstance(None, original).to_dict()
assert actual["items"][0]["spec"]["unknown"] == {
    "nested": None, "empty": [],
}
print("unknown field roundtrip:", actual["items"][0]["spec"]["unknown"])
print("ALL PROBES PASSED")
