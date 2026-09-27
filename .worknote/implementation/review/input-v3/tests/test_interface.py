import copy
import io
import json
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from kubernetes.client import (
    ApiClient,
    Configuration,
    V1ConfigMap,
    V1ObjectMeta,
)
from urllib3.response import HTTPResponse

from kubernetes_client import KubernetesClient
from kubernetes_client.errors import (
    ApiRequestError,
    ClientClosedError,
    ConfigurationError,
    DiscoveryFormatError,
    DiscoveryRequestError,
    PaginationError,
    ResourceChangedError,
    ResourceNotServedError,
    ResourceReplacedError,
    ResponseFormatError,
    WaitCancelledError,
    WaitTimeoutError,
)
from kubernetes_client.manifests import (
    basic_auth_secret,
    docker_registry_secret,
    namespace_manifest,
    opaque_secret,
    resource_requirements,
    service_account_manifest,
)


def response(body, status=200):
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    result = HTTPResponse(
        body=data,
        status=status,
        preload_content=False,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(data)),
        },
    )
    # In-memory bodies have no socket EOF for urllib3.stream to observe.
    result.stream = lambda *args, **kwargs: iter([data])
    return result


class Wire:
    def __init__(self):
        self.calls = []
        self.responses = []
        self.result = {"metadata": {"name": "demo", "uid": "uid"}}
        self.discovery_error = None
        self.plural = "configmaps"
        self.groups = None

    def request(self, method, url, **options):
        route = urlsplit(url)
        query = parse_qs(route.query)
        for key, value in options.get("fields", []):
            query.setdefault(key, []).append(str(value))
        self.calls.append((method, route.path, query, options))
        groups = [
            {
                "name": "apps",
                "versions": [
                    {
                        "groupVersion": "apps/v1",
                        "version": "v1",
                    }
                ],
                "preferredVersion": {
                    "groupVersion": "apps/v1",
                    "version": "v1",
                },
            }
        ]
        if self.groups is not None:
            groups = self.groups
        if route.path == "/version":
            result = response({"gitVersion": "v1.37.0"})
        elif route.path == "/apis":
            result = response({"kind": "APIGroupList", "groups": groups})
        elif route.path in ("/api/v1", "/apis/apps/v1"):
            if self.discovery_error is not None:
                body, status = self.discovery_error
                result = response(body, status)
            else:
                resources = (
                    [
                        (self.plural, "ConfigMap", True),
                        ("secrets", "Secret", True),
                        ("pods", "Pod", True),
                        ("namespaces", "Namespace", False),
                    ]
                    if route.path == "/api/v1"
                    else [
                        ("deployments", "Deployment", True),
                    ]
                )
                result = response(
                    {
                        "kind": "APIResourceList",
                        "resources": [
                            {
                                "name": name,
                                "kind": kind,
                                "namespaced": namespaced,
                                "verbs": [
                                    "get",
                                    "list",
                                    "create",
                                    "update",
                                    "patch",
                                    "delete",
                                    "watch",
                                ],
                            }
                            for name, kind, namespaced in resources
                        ],
                    }
                )
        else:
            result = (
                self.result()
                if callable(self.result)
                else response(self.result)
            )
        self.responses.append(result)
        return result


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.client = KubernetesClient.from_configuration(
            Configuration(host="https://unit.invalid"),
            default_namespace="team",
        )
        self.addCleanup(self.client.close)
        self.wire = Wire()
        self.client.api_client.rest_client.pool_manager.request = (
            self.wire.request
        )

    def last(self):
        return self.wire.calls[-1]

    def test_single_object_names_and_boolean_options(self):
        for name in (None, "", 1, False):
            with self.subTest(name=name):
                for call in (
                    lambda: self.client.config_maps.get(name),
                    lambda: self.client.config_maps.exists(name),
                    lambda: self.client.config_maps.patch(name, {}),
                    lambda: self.client.config_maps.delete(name),
                ):
                    with self.assertRaises(ValueError):
                        call()
        self.assertEqual(self.wire.calls, [])
        with self.assertRaises(ValueError):
            self.client.config_maps.list(all_namespaces="false")
        with self.assertRaises(ValueError):
            self.client.config_maps.delete("demo", ignore_not_found="false")

    def test_core_lookup_does_not_visit_other_version_endpoint(self):
        self.client.config_maps.get("demo")
        self.assertNotIn("/apis/apps/v1", [c[1] for c in self.wire.calls])
        with self.assertRaises(ResourceNotServedError):
            self.client.resource("v1", "ConfigMapList").get("demo")

    def test_existing_pool_retry_policy_is_rejected_without_mutation(self):
        from urllib3.util import Retry

        api = self.client.api_client
        pool = api.rest_client.pool_manager.connection_from_url(
            "https://unit.invalid"
        )
        pool.retries = Retry(total=1)
        with self.assertRaises(ConfigurationError):
            KubernetesClient.from_api_client(api)
        self.assertEqual(pool.retries.total, 1)
        with self.assertRaises(ConfigurationError):
            self.client.config_maps.get("demo")

    def test_custom_transport_is_rejected(self):
        from urllib3 import PoolManager

        class CustomPool(PoolManager):
            pass

        api = self.client.api_client
        api.rest_client.pool_manager = CustomPool(retries=0)
        with self.assertRaises(ConfigurationError):
            KubernetesClient.from_api_client(api)

    def test_malformed_discovery_is_explicit(self):
        for body in (
            {"resources": []},
            {
                "kind": "APIResourceList",
                "resources": [
                    {
                        "name": "configmaps",
                        "kind": "",
                        "namespaced": True,
                        "verbs": ["get"],
                    }
                ],
            },
        ):
            self.wire.discovery_error = (body, 200)
            self.client.refresh_discovery()
            with self.assertRaises(DiscoveryFormatError):
                self.client.config_maps.get("demo")

    def test_invalid_group_version_is_a_discovery_format_error(self):
        for version in ("", " ", "v1 "):
            entry = {"groupVersion": f"apps/{version}", "version": version}
            self.wire.groups = [
                {
                    "name": "apps",
                    "versions": [entry],
                    "preferredVersion": entry,
                }
            ]
            with self.assertRaises(DiscoveryFormatError):
                self.client.deployments.get("demo")
            self.assertIsNone(self.client._dynamic)
        self.wire.groups = [
            {
                "name": "apps",
                "versions": [{"groupVersion": "other/v1", "version": "v1"}],
                "preferredVersion": {
                    "groupVersion": "apps/v1",
                    "version": "v1",
                },
            }
        ]
        with self.assertRaises(DiscoveryFormatError):
            self.client.deployments.get("demo")

    def test_watch_framing_and_iterator_close_before_next(self):
        for raw in (
            b'{"type": "ADDED"',
            b'{"type":"ADDED","object":{"metadata":{"resourceVersion":"rv"},"bad":"\xff"}}\n',
        ):
            self.wire.result = lambda: response(raw)
            with self.assertRaises(ResponseFormatError):
                with self.client.pods.watch() as stream:
                    list(stream)
            self.assertFalse(self.client._streams)
        stream = self.client.pods.watch()
        iter(stream).close()
        self.assertFalse(self.client._streams)
        self.assertTrue(stream._closed)
        text = (
            json.dumps(
                {
                    "type": "ADDED",
                    "object": {
                        "metadata": {"resourceVersion": "rv"},
                        "value": "한글",
                    },
                },
                ensure_ascii=False,
            ).encode()
            + b"\n"
        )
        split = text.index("한".encode()) + 1
        raw_response = response(text)
        raw_response.stream = lambda *a, **k: iter(
            [text[:split], text[split:]]
        )
        self.wire.result = lambda: raw_response
        with self.client.pods.watch() as stream:
            self.assertEqual(next(iter(stream))["object"]["value"], "한글")

    def test_stale_deployment_failure_is_not_current_generation_failure(self):
        self.wire.result = {
            "metadata": {"uid": "uid", "generation": 2},
            "spec": {"replicas": 0},
            "status": {
                "observedGeneration": 1,
                "conditions": [
                    {
                        "type": "Progressing",
                        "status": "False",
                        "reason": "ProgressDeadlineExceeded",
                    }
                ],
            },
        }
        with patch(
            "kubernetes_client.watch.time.monotonic",
            side_effect=[0, 0, 0, 2, 2],
        ):
            with self.assertRaises(WaitTimeoutError):
                self.client.deployments.wait_ready(
                    "demo", target_generation=2, timeout_seconds=1
                )

    def test_auth_isolation_and_lazy_discovery(self):
        global_before = Configuration.get_default_copy().host
        source = Configuration(host="https://one.invalid")
        source.api_key["authorization"] = "Bearer one"
        with KubernetesClient.from_configuration(source) as one:
            with KubernetesClient.from_configuration(source) as two:
                one.api_client.configuration.host = "https://changed.invalid"
                self.assertEqual(
                    two.api_client.configuration.host, source.host
                )
                self.assertIsNone(one._dynamic)
                self.assertEqual(one.api_client.configuration.retries, 0)
        self.assertEqual(Configuration.get_default_copy().host, global_before)
        self.assertEqual(source.host, "https://one.invalid")

    def test_kubeconfig_factories_do_not_set_global_config(self):
        kubeconfig = {
            "apiVersion": "v1",
            "kind": "Config",
            "current-context": "one",
            "clusters": [
                {"name": n, "cluster": {"server": f"https://{n}.invalid"}}
                for n in ("one", "two")
            ],
            "users": [
                {"name": n, "user": {"token": n}} for n in ("one", "two")
            ],
            "contexts": [
                {"name": n, "context": {"cluster": n, "user": n}}
                for n in ("one", "two")
            ],
        }
        original = copy.deepcopy(kubeconfig)
        global_before = Configuration.get_default_copy().host
        for context in ("one", "two"):
            with KubernetesClient.from_kubeconfig_dict(
                kubeconfig, context=context
            ) as client:
                self.assertEqual(
                    client.api_client.configuration.host,
                    f"https://{context}.invalid",
                )
                self.assertEqual(
                    client.api_client.configuration.auth_settings()[
                        "BearerToken"
                    ]["value"],
                    f"Bearer {context}",
                )
        self.assertEqual(kubeconfig, original)
        self.assertEqual(Configuration.get_default_copy().host, global_before)

    def test_borrowed_transport_and_close(self):
        api = ApiClient(Configuration())
        self.addCleanup(api.close)
        with self.assertRaises(ConfigurationError):
            KubernetesClient.from_api_client(api)
        config = Configuration()
        config.retries = 0
        api = ApiClient(config)
        self.addCleanup(api.close)
        with patch.object(api, "close") as close:
            borrowed = KubernetesClient.from_api_client(api)
            borrowed.close()
            borrowed.close()
            close.assert_not_called()
        with self.assertRaises(ClientClosedError):
            borrowed.pods.get("demo")

    def test_owned_cache_response_and_pool_cleanup(self):
        resource = self.client.config_maps
        resource.get("demo")
        cache = Path(self.client._cache.name)
        self.assertTrue(cache.exists())
        self.assertTrue(all(r.closed for r in self.wire.responses))
        with patch.object(
            self.client.api_client.rest_client.pool_manager, "clear"
        ) as clear:
            self.client.close()
            self.client.close()
            clear.assert_called_once()
        self.assertFalse(cache.exists())
        with self.assertRaises(ClientClosedError):
            resource.get("demo")

    def test_namespace_and_unknown_fields_are_preserved(self):
        body = {
            "metadata": {"name": "demo", "namespace": "other"},
            "data": {"empty": None},
            "unknown": {"nested": []},
        }
        original = copy.deepcopy(body)
        self.client.config_maps.create(body)
        self.assertEqual(self.last()[1], "/api/v1/namespaces/other/configmaps")
        payload = json.loads(self.last()[3]["body"])
        self.assertEqual(payload["unknown"], {"nested": []})
        self.assertIsNone(payload["data"]["empty"])
        self.assertEqual(body, original)
        self.client.config_maps.get("demo")
        self.assertEqual(
            self.last()[1], "/api/v1/namespaces/team/configmaps/demo"
        )
        with self.assertRaises(ValueError):
            self.client.resource("v1", "ConfigMap", namespace="bound").create(
                body
            )
        with self.assertRaises(ValueError):
            self.client.namespaces.create(body)
        with self.assertRaises(ValueError):
            self.client.resource("v1", "ConfigMap", namespace=None)

    def test_model_uses_wire_aliases(self):
        self.client.config_maps.create(
            V1ConfigMap(
                metadata=V1ObjectMeta(name="demo", generate_name="prefix-"),
                binary_data={"x": "eA=="},
            )
        )
        payload = json.loads(self.last()[3]["body"])
        self.assertIn("binaryData", payload)
        self.assertIn("generateName", payload["metadata"])
        self.assertNotIn("binary_data", payload)

    def test_write_queries_and_empty_json_patch(self):
        self.client.config_maps.patch("demo", [], patch_type="json")
        method, path, query, options = self.last()
        self.assertEqual(method, "PATCH")
        self.assertEqual(options["body"], "[]")
        self.assertEqual(
            options["headers"]["Content-Type"], "application/json-patch+json"
        )
        self.assertEqual(query["fieldValidation"], ["Strict"])
        self.client.config_maps.apply({"metadata": {"name": "demo"}})
        query, options = self.last()[2:]
        self.assertEqual(query["fieldManager"], ["kubernetes-client"])
        self.assertIn(query["force"], (["false"], ["False"]))
        self.assertEqual(query["fieldValidation"], ["Strict"])
        self.assertEqual(
            options["headers"]["Content-Type"], "application/apply-patch+yaml"
        )
        with self.assertRaises(ValueError):
            self.client.config_maps.replace({"metadata": {"name": "demo"}})
        with self.assertRaises(ValueError):
            self.client.secrets.apply(
                {
                    "metadata": {"name": "demo"},
                    "stringData": {"password": "sensitive"},
                }
            )

    def test_discovery_errors_are_not_missing_resources(self):
        self.wire.discovery_error = ({"reason": "ServiceUnavailable"}, 503)
        with self.assertRaises(DiscoveryRequestError) as caught:
            self.client.config_maps.exists("demo")
        self.assertEqual(caught.exception.status, 503)
        self.assertIsNotNone(caught.exception.__cause__)
        self.assertEqual(sum(c[1] == "/api/v1" for c in self.wire.calls), 1)
        self.assertTrue(all(r.closed for r in self.wire.responses))
        self.client.refresh_discovery()
        self.wire.discovery_error = (b"{broken", 200)
        with self.assertRaises(DiscoveryFormatError):
            self.client.config_maps.get("demo")

    def test_negative_lookup_refreshes_once_and_stale_handle_refreshes(self):
        with self.assertRaises(ResourceNotServedError):
            self.client.resource("v1", "Absent").get("demo")
        self.assertEqual(sum(c[1] == "/api/v1" for c in self.wire.calls), 2)
        handle = self.client.config_maps
        handle.get("demo")
        self.wire.plural = "irregularplural"
        self.client.refresh_discovery()
        handle.get("demo")
        self.assertTrue(self.last()[1].endswith("/irregularplural/demo"))
        self.assertTrue(
            all(c[3]["timeout"].connect_timeout == 5 for c in self.wire.calls)
        )

    def missing(self, *, kind="configmaps", group="", name="demo"):
        return response(
            {
                "kind": "Status",
                "reason": "NotFound",
                "code": 404,
                "details": {"kind": kind, "group": group, "name": name},
            },
            404,
        )

    def test_404_classification_and_delete_preconditions(self):
        self.wire.result = self.missing
        self.assertFalse(self.client.config_maps.exists("demo"))
        result = self.client.config_maps.delete("demo", ignore_not_found=True)
        self.assertEqual(result.action, "already_absent")
        for missing in (
            lambda: self.missing(kind="namespaces", name="team"),
            lambda: response({"reason": "NotFound"}, 404),
        ):
            self.wire.result = missing
            with self.assertRaises(ApiRequestError):
                self.client.config_maps.exists("demo")
        self.wire.result = {"kind": "Status", "status": "Success"}
        result = self.client.config_maps.delete(
            "demo",
            expected_uid="uid",
            resource_version="rv",
            propagation_policy="Foreground",
            grace_period_seconds=0,
        )
        self.assertEqual(result.action, "requested")
        self.assertEqual(
            json.loads(self.last()[3]["body"]),
            {
                "preconditions": {"uid": "uid", "resourceVersion": "rv"},
                "propagationPolicy": "Foreground",
                "gracePeriodSeconds": 0,
            },
        )

    def test_pagination_and_snapshot_errors(self):
        pages = iter(
            [
                {
                    "metadata": {
                        "resourceVersion": "opaque",
                        "continue": "next",
                    },
                    "items": [],
                },
                {
                    "metadata": {"resourceVersion": "opaque"},
                    "items": [{"x": None}],
                },
            ]
        )
        self.wire.result = lambda: response(next(pages))
        items = list(
            self.client.config_maps.iter_items(
                resource_version="old",
                resource_version_match="NotOlderThan",
                limit=2,
                label_selector="app=demo",
                all_namespaces=True,
            )
        )
        self.assertEqual(items, [{"x": None}])
        collection = [
            c for c in self.wire.calls if c[1] == "/api/v1/configmaps"
        ]
        self.assertEqual(
            collection[0][2]["resourceVersionMatch"], ["NotOlderThan"]
        )
        self.assertNotIn("resourceVersionMatch", collection[1][2])
        self.assertNotIn("resourceVersion", collection[1][2])
        self.assertEqual(collection[1][2]["continue"], ["next"])
        self.assertEqual(collection[1][2]["labelSelector"], ["app=demo"])
        self.wire.result = {
            "metadata": {"resourceVersion": "a", "continue": "same"},
            "items": [],
        }
        with self.assertRaises(PaginationError):
            list(self.client.config_maps.iter_items())

    def test_wait_identity_races_and_deadline(self):
        self.wire.result = {
            "metadata": {"uid": "replacement"},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }
        with self.assertRaises(ResourceReplacedError):
            self.client.pods.wait_ready("demo", expected_uid="written")
        with self.assertRaises(ResourceReplacedError):
            self.client.pods.wait_deleted("demo", expected_uid="written")
        self.wire.result = {
            "metadata": {"uid": "uid", "generation": 2},
            "status": {"observedGeneration": 2},
            "spec": {"replicas": 0},
        }
        with self.assertRaises(ResourceChangedError):
            self.client.deployments.wait_ready("demo", target_generation=1)
        result = self.client.deployments.wait_ready(
            "demo", target_generation=2
        )
        self.assertEqual(result["metadata"]["generation"], 2)
        self.client.pods._resolve("get")
        with patch(
            "kubernetes_client.watch.time.monotonic", side_effect=[0, 0, 2]
        ):
            with self.assertRaises(WaitTimeoutError):
                self.client.pods.wait_ready("demo", timeout_seconds=1)
        cancellation = Event()
        cancellation.set()
        with self.assertRaises(WaitCancelledError):
            self.client.pods.wait_ready("demo", cancel_event=cancellation)
        with self.assertRaises(ValueError):
            self.client.pods.wait_ready("demo", target_generation=1)
        self.wire.result = lambda: self.missing(kind="pods")
        self.assertIsNone(
            self.client.pods.wait_deleted("demo", expected_uid="uid")
        )

    def test_watch_bookmarks_malformed_error_and_cleanup(self):
        events = [
            {
                "type": "BOOKMARK",
                "object": {"metadata": {"resourceVersion": "rv"}},
            }
        ]
        raw = b"\n".join(json.dumps(e).encode() for e in events) + b"\n"
        self.wire.result = lambda: response(raw)
        with self.client.pods.watch(
            name="demo", field_selector="status.phase=Running"
        ) as stream:
            results = list(stream)
        self.assertEqual(results[0]["resource_version"], "rv")
        self.assertEqual(
            self.last()[2]["fieldSelector"],
            ["status.phase=Running,metadata.name=demo"],
        )
        self.assertEqual(self.last()[2]["timeoutSeconds"], ["300"])
        self.assertTrue(self.wire.responses[-1].closed)
        self.assertFalse(self.client._streams)
        self.wire.result = lambda: response(b"{broken\n")
        with self.assertRaises(ResponseFormatError):
            with self.client.pods.watch() as stream:
                list(stream)
        self.wire.result = lambda: response(
            json.dumps(
                {
                    "type": "ERROR",
                    "object": {
                        "code": 410,
                        "reason": "Expired",
                        "message": "expired",
                    },
                }
            ).encode()
            + b"\n"
        )
        with self.assertRaises(ApiRequestError) as caught:
            with self.client.pods.watch() as stream:
                list(stream)
        self.assertEqual(caught.exception.status, 410)
        self.assertEqual(
            json.loads(caught.exception.body)["reason"], "Expired"
        )


class ManifestTests(unittest.TestCase):
    def test_pure_helpers_and_secret_encoding(self):
        self.assertEqual(
            namespace_manifest("team")["metadata"], {"name": "team"}
        )
        self.assertEqual(
            opaque_secret("demo", string_data={"unicode": "한글"})["data"],
            {"unicode": "7ZWc6riA"},
        )
        self.assertNotIn("stringData", basic_auth_secret("demo", 0, ""))
        self.assertEqual(
            docker_registry_secret("demo", "registry", "u", "p")["type"],
            "kubernetes.io/dockerconfigjson",
        )
        self.assertFalse(
            service_account_manifest(
                "demo", automount_service_account_token=False
            )["automountServiceAccountToken"]
        )
        with self.assertRaises(ValueError):
            opaque_secret("demo", data={"x": "eA=="}, string_data={"x": "x"})
        with self.assertRaises(ValueError):
            basic_auth_secret("demo", None, "p")
        with self.assertRaises(ValueError):
            service_account_manifest("demo", image_pull_secrets="registry")

    def test_resource_quantities_do_not_adjust_limits(self):
        result = resource_requirements(
            requests={"cpu": "100m"}, limits={"cpu": "1"}
        )
        self.assertEqual(result.requests, {"cpu": "100m"})
        for value in ("-1", "NaN", "Infinity", "invalid"):
            with self.assertRaises(ValueError):
                resource_requirements(requests={"cpu": value})
        with self.assertRaises(ValueError):
            resource_requirements(
                requests={"memory": "2Gi"}, limits={"memory": "1Gi"}
            )


if __name__ == "__main__":
    unittest.main()
