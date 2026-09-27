"""Required live checks. Set KUBERNETES_CLIENT_TEST_CONFIG explicitly."""

import copy
import os
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from threading import Event

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from kubernetes_client import KubernetesClient
from kubernetes_client.errors import (
    ApiRequestError,
    DiscoveryRequestError,
    ResourceChangedError,
    ResourceReplacedError,
    WaitCancelledError,
    WaitTimeoutError,
)
from kubernetes_client.manifests import namespace_manifest, opaque_secret


IMAGE = (
    "registry.k8s.io/pause:3.10@sha256:"
    "ee6521f290b2168b6e0935a181d4cff9be1ac3f505666ef0e3c98fae8199917a"
)


class ClusterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_file = os.environ["KUBERNETES_CLIENT_TEST_CONFIG"]
        cls.prefix = "kc-v1-" + uuid.uuid4().hex[:8]
        cls.namespace = cls.prefix
        cls.client = KubernetesClient.from_kubeconfig(
            cls.config_file,
            default_namespace=cls.namespace,
            field_manager="integration-owner",
        )
        cls.addClassCleanup(cls.client.close)
        for name in (cls.namespace, cls.namespace + "-other"):
            created = cls.client.namespaces.create(namespace_manifest(name))
            cls.addClassCleanup(
                cls.cleanup,
                cls.client.namespaces,
                name,
                created["metadata"]["uid"],
            )
        version = cls.client._dynamic_client.version["kubernetes"][
            "gitVersion"
        ]
        cls.version = version
        expected_version = os.environ.get(
            "KUBERNETES_CLIENT_TEST_SERVER_VERSION"
        )
        if expected_version and version != expected_version:
            raise AssertionError(
                f"Expected server {expected_version}, received {version}"
            )
        print(f"LIVE server={version} namespace={cls.namespace} image={IMAGE}")

    @classmethod
    def cleanup(cls, resource, name, uid):
        resource.delete(name, expected_uid=uid, ignore_not_found=True)
        resource.wait_deleted(
            name, expected_uid=uid, timeout_seconds=60, poll_interval=0.1
        )

    def created(self, resource, body):
        value = resource.create(body)
        self.addCleanup(
            self.cleanup,
            resource,
            value["metadata"]["name"],
            value["metadata"]["uid"],
        )
        return value

    def test_builtin_groups_and_dra(self):
        fixtures = [
            ("v1", "ServiceAccount", {}),
            ("v1", "Service", {"spec": {"ports": [{"port": 80}]}}),
            (
                "v1",
                "PersistentVolumeClaim",
                {
                    "spec": {
                        "accessModes": ["ReadWriteOnce"],
                        "resources": {"requests": {"storage": "1Mi"}},
                    }
                },
            ),
            (
                "batch/v1",
                "Job",
                {
                    "spec": {
                        "suspend": True,
                        "template": {
                            "spec": {
                                "restartPolicy": "Never",
                                "containers": [
                                    {"name": "pause", "image": IMAGE},
                                ],
                            },
                        },
                    }
                },
            ),
            (
                "batch/v1",
                "CronJob",
                {
                    "spec": {
                        "schedule": "0 0 * * *",
                        "suspend": True,
                        "jobTemplate": {
                            "spec": {
                                "template": {
                                    "spec": {
                                        "restartPolicy": "Never",
                                        "containers": [
                                            {"name": "pause", "image": IMAGE},
                                        ],
                                    }
                                }
                            },
                        },
                    }
                },
            ),
            (
                "autoscaling/v2",
                "HorizontalPodAutoscaler",
                {
                    "spec": {
                        "scaleTargetRef": {
                            "apiVersion": "apps/v1",
                            "kind": "Deployment",
                            "name": "absent",
                        },
                        "minReplicas": 1,
                        "maxReplicas": 2,
                    }
                },
            ),
            (
                "networking.k8s.io/v1",
                "Ingress",
                {
                    "spec": {
                        "defaultBackend": {
                            "service": {
                                "name": "absent",
                                "port": {"number": 80},
                            },
                        }
                    }
                },
            ),
            (
                "discovery.k8s.io/v1",
                "EndpointSlice",
                {"addressType": "IPv4", "endpoints": [], "ports": []},
            ),
            (
                "policy/v1",
                "PodDisruptionBudget",
                {
                    "spec": {
                        "maxUnavailable": 1,
                        "selector": {"matchLabels": {"app": "absent"}},
                    }
                },
            ),
            (
                "coordination.k8s.io/v1",
                "Lease",
                {"spec": {"holderIdentity": "test"}},
            ),
            ("rbac.authorization.k8s.io/v1", "Role", {"rules": []}),
            (
                "storage.k8s.io/v1",
                "StorageClass",
                {
                    "provisioner": "test.example",
                    "volumeBindingMode": "WaitForFirstConsumer",
                },
            ),
            ("resource.k8s.io/v1", "ResourceClaim", {"spec": {"devices": {}}}),
            (
                "resource.k8s.io/v1",
                "ResourceClaimTemplate",
                {
                    "spec": {
                        "spec": {"devices": {}},
                    }
                },
            ),
            (
                "resource.k8s.io/v1",
                "ResourceSlice",
                {
                    "spec": {
                        "driver": "test.example",
                        "pool": {
                            "name": "test",
                            "generation": 1,
                            "resourceSliceCount": 1,
                        },
                        "allNodes": True,
                        "devices": [],
                    }
                },
            ),
        ]
        for index, (api_version, kind, fields) in enumerate(fixtures):
            with self.subTest(kind=kind):
                resource = self.client.resource(api_version, kind)
                name = f"{self.prefix}-{index}"
                body = dict(fields, metadata={"name": name})
                created = self.created(resource, body)
                self.assertEqual(
                    resource.get(name)["metadata"]["uid"],
                    created["metadata"]["uid"],
                )
                changed = resource.patch(
                    name, {"metadata": {"labels": {"test": "yes"}}}
                )
                self.assertEqual(changed["metadata"]["labels"]["test"], "yes")
                # Controllers can update status/RV between GET and PUT.
                # The facade preserves 409; this test explicitly re-reads.
                for attempt in range(5):
                    current = resource.get(name)
                    try:
                        replaced = resource.replace(current)
                        break
                    except ApiRequestError as conflict:
                        if conflict.status != 409 or attempt == 4:
                            raise
                self.assertEqual(
                    replaced["metadata"]["uid"], created["metadata"]["uid"]
                )
                applied = resource.apply(
                    {
                        "metadata": {
                            "name": name,
                            "annotations": {"wrapper-test": "yes"},
                        }
                    }
                )
                self.assertEqual(
                    applied["metadata"]["annotations"]["wrapper-test"], "yes"
                )
                self.assertIsInstance(resource.list(limit=1)["items"], list)

    def test_namespace_crud_pagination_and_watch(self):
        resource = self.client.config_maps
        for index in range(3):
            self.created(
                resource,
                {
                    "metadata": {
                        "name": f"page-{index}",
                        "labels": {"page": "yes"},
                    },
                    "data": {"value": "initial"},
                },
            )
        self.assertEqual(
            len(list(resource.iter_items(limit=1, label_selector="page=yes"))),
            3,
        )
        other = self.client.resource(
            "v1", "ConfigMap", namespace=self.namespace + "-other"
        )
        self.created(
            other, {"metadata": {"name": "page-0"}, "data": {"value": "other"}}
        )
        self.assertEqual(other.get("page-0")["data"]["value"], "other")
        with self.assertRaises(ApiRequestError) as duplicate:
            resource.create({"metadata": {"name": "page-0"}})
        self.assertEqual(duplicate.exception.status, 409)
        before = resource.list()["metadata"]["resourceVersion"]
        self.created(resource, {"metadata": {"name": "watch-target"}})
        with resource.watch(
            name="watch-target", resource_version=before, timeout_seconds=5
        ) as stream:
            event = next(iter(stream))
            self.assertEqual(event["type"], "ADDED")
            self.assertEqual(
                event["object"]["metadata"]["name"], "watch-target"
            )
        resource.patch("page-0", [], patch_type="json")
        with self.assertRaises(ApiRequestError) as invalid:
            resource.create(
                {"metadata": {"name": "invalid"}, "data": {"x": 1}}
            )
        self.assertEqual(invalid.exception.status, 400)

    def test_secret_ssa_conflict_and_force(self):
        resource = self.client.secrets
        body = opaque_secret("ssa-secret", string_data={"password": "test"})
        initial = resource.apply(body)
        self.addCleanup(
            self.cleanup, resource, "ssa-secret", initial["metadata"]["uid"]
        )
        self.assertEqual(resource.apply(body)["data"], body["data"])
        changed = opaque_secret(
            "ssa-secret", string_data={"password": "changed"}
        )
        with self.assertRaises(ApiRequestError) as conflict:
            resource.apply(changed, field_manager="other-owner")
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(
            resource.apply(changed, field_manager="other-owner", force=True)[
                "data"
            ],
            changed["data"],
        )
        self.assertNotIn("changed", str(conflict.exception))

    def test_finalizer_uid_race_timeout_and_cancel(self):
        resource = self.client.config_maps
        value = self.created(
            resource,
            {
                "metadata": {
                    "name": "finalizer",
                    "finalizers": ["tests.example/hold"],
                }
            },
        )
        uid = value["metadata"]["uid"]
        with self.assertRaises(ApiRequestError) as conflict:
            resource.delete("finalizer", expected_uid="wrong")
        self.assertEqual(conflict.exception.status, 409)
        try:
            self.assertEqual(
                resource.delete("finalizer", expected_uid=uid).action,
                "requested",
            )
            with self.assertRaises(WaitTimeoutError):
                resource.wait_deleted(
                    "finalizer",
                    expected_uid=uid,
                    timeout_seconds=0.3,
                    poll_interval=0.05,
                )
            cancel = Event()
            cancel.set()
            with self.assertRaises(WaitCancelledError):
                resource.wait_deleted(
                    "finalizer", expected_uid=uid, cancel_event=cancel
                )
        finally:
            resource.patch("finalizer", {"metadata": {"finalizers": []}})
        resource.wait_deleted(
            "finalizer", expected_uid=uid, timeout_seconds=30
        )
        replacement = resource.create({"metadata": {"name": "finalizer"}})
        self.addCleanup(
            self.cleanup, resource, "finalizer", replacement["metadata"]["uid"]
        )
        # Remove cleanup for the deleted UID; it must not delete a replacement.
        self._cleanups = [
            entry for entry in self._cleanups if uid not in entry[1]
        ]
        with self.assertRaises(ResourceReplacedError):
            resource.wait_deleted("finalizer", expected_uid=uid)

    def test_pod_and_deployment_waits(self):
        pod = self.created(
            self.client.pods,
            {
                "metadata": {"name": "ready-pod"},
                "spec": {"containers": [{"name": "pause", "image": IMAGE}]},
            },
        )
        ready = self.client.pods.wait_ready(
            "ready-pod",
            expected_uid=pod["metadata"]["uid"],
            timeout_seconds=120,
            poll_interval=0.2,
        )
        self.assertEqual(ready["status"]["phase"], "Running")
        deployment = self.created(
            self.client.deployments,
            {
                "metadata": {"name": "rollout"},
                "spec": {
                    "replicas": 1,
                    "selector": {"matchLabels": {"app": "rollout"}},
                    "template": {
                        "metadata": {"labels": {"app": "rollout"}},
                        "spec": {
                            "containers": [{"name": "pause", "image": IMAGE}]
                        },
                    },
                },
            },
        )
        uid = deployment["metadata"]["uid"]
        generation = deployment["metadata"]["generation"]
        self.client.deployments.wait_ready(
            "rollout",
            expected_uid=uid,
            target_generation=generation,
            timeout_seconds=120,
            poll_interval=0.2,
        )
        self.client.deployments.patch("rollout", {"spec": {"replicas": 0}})
        with self.assertRaises(ResourceChangedError):
            self.client.deployments.wait_ready(
                "rollout", expected_uid=uid, target_generation=generation
            )

    def test_crds_scope_versions_unknown_fields_and_schema(self):
        for namespaced in (True, False):
            kind = "Mouse" if namespaced else "ClusterMouse"
            plural = "mice" if namespaced else "clustermice"
            group = "wrapper-tests.example"
            schema = {
                "type": "object",
                "properties": {
                    "spec": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer"},
                            "payload": {
                                "type": "object",
                                "x-kubernetes-preserve-unknown-fields": True,
                            },
                        },
                    }
                },
            }
            crds = self.client.resource(
                "apiextensions.k8s.io/v1", "CustomResourceDefinition"
            )
            self.created(
                crds,
                {
                    "metadata": {"name": f"{plural}.{group}"},
                    "spec": {
                        "group": group,
                        "scope": "Namespaced" if namespaced else "Cluster",
                        "names": {
                            "plural": plural,
                            "singular": kind.lower(),
                            "kind": kind,
                        },
                        "versions": [
                            {
                                "name": version,
                                "served": True,
                                "storage": version == "v1",
                                "schema": {"openAPIV3Schema": schema},
                            }
                            for version in ("v1", "v2")
                        ],
                    },
                },
            )
            deadline = time.monotonic() + 30
            while not any(
                c["type"] == "Established" and c["status"] == "True"
                for c in (
                    crds.get(f"{plural}.{group}")
                    .get("status", {})
                    .get("conditions")
                    or []
                )
            ):
                if time.monotonic() >= deadline:
                    self.fail("CRD did not become established")
                Event().wait(0.1)
            self.client.refresh_discovery()
            resource = self.client.resource(f"{group}/v1", kind)
            payload = {
                "nested": {"null": None, "empty": [], "newField": "preserved"}
            }
            value = self.created(
                resource,
                {
                    "metadata": {"name": "roundtrip"},
                    "spec": {"count": 1, "payload": payload},
                },
            )
            self.assertEqual(value["spec"]["payload"], payload)
            version_two = self.client.resource(f"{group}/v2", kind)
            self.assertEqual(
                version_two.get("roundtrip")["spec"]["payload"], payload
            )
            with self.assertRaises(ApiRequestError) as invalid:
                resource.patch("roundtrip", {"spec": {"count": "invalid"}})
            self.assertEqual(invalid.exception.status, 422)

    def test_get_only_rbac_and_discovery_denial(self):
        name = "rbac-target"
        self.created(self.client.config_maps, {"metadata": {"name": name}})
        user = self.prefix + "-reader"
        self.created(
            self.client.resource("rbac.authorization.k8s.io/v1", "Role"),
            {
                "metadata": {"name": "get-only"},
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["configmaps"],
                        "verbs": ["get"],
                    }
                ],
            },
        )
        self.created(
            self.client.resource(
                "rbac.authorization.k8s.io/v1", "RoleBinding"
            ),
            {
                "metadata": {"name": "get-only"},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "Role",
                    "name": "get-only",
                },
                "subjects": [
                    {
                        "apiGroup": "rbac.authorization.k8s.io",
                        "kind": "User",
                        "name": user,
                    }
                ],
            },
        )
        with KubernetesClient.from_kubeconfig(
            self.config_file, default_namespace=self.namespace
        ) as restricted:
            restricted.api_client.default_headers["Impersonate-User"] = user
            restricted.api_client.default_headers["Impersonate-Group"] = (
                "system:authenticated"
            )
            self.assertTrue(restricted.config_maps.exists(name))
            with self.assertRaises(ApiRequestError) as forbidden:
                restricted.config_maps.list()
            self.assertEqual(forbidden.exception.status, 403)
        # RBAC grants are additive. Isolate discovery denial in this disposable
        # cluster by temporarily removing the default discovery grant.
        roles = self.client.resource(
            "rbac.authorization.k8s.io/v1", "ClusterRole"
        )
        original = roles.get("system:discovery")["rules"]
        try:
            roles.patch("system:discovery", {"rules": []})
            with KubernetesClient.from_kubeconfig(self.config_file) as denied:
                denied.api_client.default_headers["Impersonate-User"] = (
                    self.prefix + "-denied"
                )
                with self.assertRaises(DiscoveryRequestError) as forbidden:
                    denied.config_maps.get(name)
                self.assertEqual(forbidden.exception.status, 403)
        finally:
            roles.patch("system:discovery", {"rules": original})

    def test_latest_stable_cluster_trust_bundle(self):
        if not self.version.startswith("v1.37."):
            self.skipTest(
                "Latest stable ClusterTrustBundle case requires server 1.37"
            )
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "wrapper-test")]
        )
        now = datetime.now(timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None), critical=True
            )
            .sign(key, hashes.SHA256())
        )
        pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
        resource = self.client.resource(
            "certificates.k8s.io/v1", "ClusterTrustBundle"
        )
        value = self.created(
            resource,
            {
                "metadata": {"name": self.prefix + "-trust"},
                "spec": {"trustBundle": pem},
            },
        )
        self.assertEqual(
            resource.get(value["metadata"]["name"])["spec"]["trustBundle"], pem
        )
        changed = resource.patch(
            value["metadata"]["name"],
            {"metadata": {"labels": {"latest-stable": "yes"}}},
        )
        self.assertEqual(changed["metadata"]["labels"]["latest-stable"], "yes")


if __name__ == "__main__":
    unittest.main()
