"""Run in a disposable namespace; all created objects are removed."""

import argparse

from kubernetes_client import KubernetesClient
from kubernetes_client.manifests import namespace_manifest, opaque_secret


def run(config_file, namespace):
    with KubernetesClient.from_kubeconfig(
        config_file,
        default_namespace=namespace,
        field_manager="quickstart-example",
    ) as client:
        created = client.namespaces.create(namespace_manifest(namespace))
        namespace_uid = created["metadata"]["uid"]
        try:
            secrets = client.resource("v1", "Secret", namespace=namespace)
            body = opaque_secret(
                "credentials", string_data={"username": "example"}
            )
            applied = secrets.apply(body)
            assert (
                secrets.get("credentials")["data"]["username"]
                == "ZXhhbXBsZQ=="
            )
            assert (
                secrets.apply(body)["metadata"]["uid"]
                == applied["metadata"]["uid"]
            )
            uid = applied["metadata"]["uid"]
            assert (
                secrets.delete("credentials", expected_uid=uid).action
                == "requested"
            )
            secrets.wait_deleted("credentials", expected_uid=uid)
            assert not secrets.exists("credentials")
        finally:
            client.namespaces.delete(namespace, expected_uid=namespace_uid)
            client.namespaces.wait_deleted(
                namespace, expected_uid=namespace_uid, timeout_seconds=60
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--kubeconfig", required=True)
    parser.add_argument("--namespace", required=True)
    args = parser.parse_args()
    run(args.kubeconfig, args.namespace)
