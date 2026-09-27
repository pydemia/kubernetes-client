import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from kubernetes.client import (
    ApiClient,
    V1Namespace,
    V1ObjectMeta,
    V1Pod,
    V1PodCondition,
    V1PodStatus,
)
from pydantic import ValidationError

from kubernetes_client import KubernetesManager
from kubernetes_client.__version__ import __version__
from kubernetes_client.schema import ResourceSpec, Spec


class CompatibilityTests(unittest.TestCase):
    def test_version_and_bearer_configuration(self):
        self.assertEqual(__version__, "0.9.0")
        configuration = KubernetesManager.set_default_config(
            "https://cluster.example", token="example"
        )
        self.assertEqual(
            configuration.auth_settings()["BearerToken"]["value"],
            "Bearer example",
        )

    def test_resource_quantities_and_alias(self):
        spec = Spec(cpu=0.5, memory=2.5, gpu=1)
        self.assertEqual(
            spec.model_dump(by_alias=True),
            {"cpu": "0.5", "memory": "2.5Gi", "nvidia.com/gpu": "1"},
        )
        self.assertEqual(
            Spec(**{"nvidia.com/gpu": 2}).gpu,
            2,
        )
        self.assertEqual(
            Spec(cpu=None, memory=None, gpu=None).model_dump(
                by_alias=True, exclude_none=True
            ),
            {},
        )
        with self.assertRaises(ValidationError):
            Spec(cpu=0.15)

    def test_resource_limits_are_at_least_requests(self):
        requests = Spec(cpu=2, memory=4, gpu=1)
        limits = Spec(cpu=1, memory=2, gpu=0)
        resource = ResourceSpec(requests=requests, limits=limits)

        self.assertEqual(resource.limits.cpu, 2)
        self.assertEqual(resource.limits.memory, 4)
        self.assertEqual(resource.limits.gpu, 1)
        self.assertEqual(limits.cpu, 1)

    def test_build_resource_spec_uses_kubernetes_quantities(self):
        manager = object.__new__(KubernetesManager)
        resource = manager.build_resource_spec(
            cpu_req=0.5,
            mem_req=2,
            gpu_req=1,
            cpu_limit=1,
            mem_limit=4,
            gpu_limit=1,
        )
        self.assertEqual(
            resource.requests,
            {"cpu": "0.5", "memory": "2Gi", "nvidia.com/gpu": "1"},
        )
        self.assertEqual(
            resource.limits,
            {"cpu": "1", "memory": "4Gi", "nvidia.com/gpu": "1"},
        )
        serialized = ApiClient().sanitize_for_serialization(resource)
        self.assertEqual(serialized["requests"], resource.requests)
        self.assertEqual(serialized["limits"], resource.limits)
        empty = manager.build_resource_spec()
        self.assertEqual(empty.requests, {})
        self.assertEqual(empty.limits, {})

    def test_watch_pod_accepts_model_and_dict_events(self):
        manager = object.__new__(KubernetesManager)
        manager.client = Mock()
        pod = V1Pod(
            metadata=V1ObjectMeta(name="target"),
            status=V1PodStatus(
                conditions=[V1PodCondition(type="Ready", status="True")]
            ),
        )
        events = [
            {"object": V1Pod(metadata=V1ObjectMeta(name="other"))},
            {"object": pod},
            {"object": {
                "metadata": {"name": "target"},
                "status": {"conditions": [
                    {"type": "Ready", "status": "False"}
                ]},
            }},
        ]
        output = io.StringIO()
        with patch("kubernetes_client.base.k8s_watch.Watch") as watch:
            watch.return_value.stream.return_value = events
            with redirect_stdout(output):
                manager.watch_pod(
                    "target", label_selector={"tier": "api", "app": "demo"}
                )

        self.assertEqual(
            watch.return_value.stream.call_args.kwargs["label_selector"],
            "app=demo,tier=api",
        )
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("NAME", lines[0])
        self.assertIn("True", lines[1])
        self.assertIn("False", lines[2])

    def test_patch_namespace_uses_model_metadata(self):
        manager = object.__new__(KubernetesManager)
        manager.client = Mock()
        manager.client.read_namespace.return_value = V1Namespace(
            metadata=V1ObjectMeta(
                name="target", labels={"old": "label"},
                annotations={"old": "annotation"},
            )
        )
        manager.patch_namespace(
            "target", labels={"new": "label"},
            annotations={"new": "annotation"},
        )

        body = manager.client.patch_namespace.call_args.kwargs["body"]
        self.assertEqual(body.metadata.labels, {
            "old": "label", "new": "label"
        })
        self.assertEqual(body.metadata.annotations, {
            "old": "annotation", "new": "annotation"
        })

    def test_prepare_namespace_handles_missing_existing_labels(self):
        manager = object.__new__(KubernetesManager)
        manager.client = Mock()
        manager.check_ns_exists = Mock(return_value=True)
        manager.client.read_namespace.return_value = V1Namespace(
            metadata=V1ObjectMeta(name="target")
        )
        manager.prepare_namespace(
            "target", project_id=7, annotations={"owner": "demo"}
        )

        body = manager.client.patch_namespace.call_args.kwargs["body"]
        self.assertEqual(body.metadata.labels["runtime/project-id"], "7")
        self.assertEqual(body.metadata.annotations, {"owner": "demo"})


if __name__ == "__main__":
    unittest.main()
