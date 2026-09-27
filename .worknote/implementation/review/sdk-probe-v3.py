"""Targeted discovery group/version recheck for the fixed v3 input."""

import copy
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input-v3"
sys.path[:0] = [str(INPUT), str(INPUT / "tests")]

import kubernetes
import pydantic
import urllib3
from kubernetes.client import Configuration

from kubernetes_client import KubernetesClient
from kubernetes_client.errors import DiscoveryFormatError
from test_interface import Wire, response


def emit(name, value):
    print(json.dumps({"probe": name, "result": value}, ensure_ascii=False))


class GroupWire(Wire):
    def __init__(self, group):
        super().__init__()
        self.group = copy.deepcopy(group)
        self.custom = True

    def request(self, method, url, **options):
        if self.custom and urlsplit(url).path == "/apis":
            self.calls.append((method, "/apis", {}, options))
            result = response({"kind": "APIGroupList", "groups": [self.group]})
            self.responses.append(result)
            return result
        return super().request(method, url, **options)


def group_for(version="v1", group_version=None):
    version_entry = {
        "groupVersion": f"apps/{version}" if group_version is None else (
            group_version
        ),
        "version": version,
    }
    return {
        "name": "apps", "versions": [version_entry],
        "preferredVersion": copy.deepcopy(version_entry),
    }


def check(name, group, *, valid=False):
    wire = GroupWire(group)
    with KubernetesClient.from_configuration(
        Configuration(host="https://review.invalid")
    ) as client:
        client.api_client.rest_client.pool_manager.request = wire.request
        try:
            result = client.deployments.get("demo")
        except DiscoveryFormatError as error:
            assert not valid, name
            observed = {"exception": type(error).__name__, "message": str(error)}
            assert [call[1] for call in wire.calls] == ["/version", "/apis"]
            assert client._dynamic is None
            assert client._cache is None
            observed["routes"] = [call[1] for call in wire.calls]
            observed["responses_closed"] = all(r.closed for r in wire.responses)
            assert observed["responses_closed"]
            wire.custom = False
            client.deployments.get("demo")
            observed["same_client_recovery"] = True
        else:
            assert valid, name
            assert result["metadata"]["name"] == "demo"
            assert wire.calls[-1][1] == (
                "/apis/apps/v1/namespaces/default/deployments/demo"
            )
            observed = {
                "value": result, "routes": [call[1] for call in wire.calls],
                "responses_closed": all(r.closed for r in wire.responses),
            }
        emit(name, observed)


emit("sdk", kubernetes.__version__)
emit("runtime", {"python": sys.version, "pydantic": pydantic.__version__,
                 "urllib3": urllib3.__version__})
entries = (ROOT / "input-v3.sha256").read_text().splitlines()
matched = all(
    hashlib.sha256((INPUT / path.replace("\\", "/")).read_bytes())
    .hexdigest().lower() == digest.lower()
    for digest, path in (entry.split(maxsplit=1) for entry in entries)
)
assert matched
emit("snapshot_hashes", {"matched": matched, "files": len(entries)})

for version in ("", " ", "\t", "\n", " v1", "v1 ", "v1\t"):
    check(f"invalid_version_{version!r}", group_for(version))
for group_version in ("", " ", "\t", " apps/v1", "apps/v1 "):
    check(f"invalid_group_version_{group_version!r}",
          group_for(group_version=group_version))
check("contradictory_group_name", group_for(group_version="other/v1"))
check("contradictory_group_version", group_for(group_version="apps/v2"))

for preferred_field in ("groupVersion", "version"):
    for value in ("", " ", "\t", " padded "):
        group = group_for()
        group["preferredVersion"][preferred_field] = value
        check(f"invalid_preferred_{preferred_field}_{value!r}", group)

group = group_for()
group["preferredVersion"] = {"groupVersion": "apps/v2", "version": "v2"}
check("preferred_version_not_served", group)
group["preferredVersion"] = {"groupVersion": "apps/v2", "version": "v1"}
check("preferred_pair_contradictory", group)

group = group_for()
group["versions"] = []
check("empty_served_version_list", group)
check("valid_single_version", group_for(), valid=True)
group = group_for()
group["versions"].append({"groupVersion": "apps/v2", "version": "v2"})
group["preferredVersion"] = copy.deepcopy(group["versions"][1])
check("valid_other_preferred_exact_v1", group, valid=True)
