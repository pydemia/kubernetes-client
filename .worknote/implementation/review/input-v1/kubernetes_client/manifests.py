"""Pure manifest builders; callers explicitly choose create or apply."""

import base64
import copy
import json
from collections.abc import Mapping

from kubernetes.client import V1ResourceRequirements
from kubernetes.utils.quantity import parse_quantity

from .client import required_string


def _metadata(name, namespace, labels, annotations):
    result = {"name": required_string(name, "name")}
    if namespace is not None:
        result["namespace"] = required_string(namespace, "namespace")
    for field, value in (("labels", labels), ("annotations", annotations)):
        if value is not None:
            if not isinstance(value, Mapping) or not all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in value.items()
            ):
                raise ValueError(f"{field} must contain string keys and values")
            result[field] = dict(value)
    return result


def namespace_manifest(name, *, labels=None, annotations=None):
    return {
        "apiVersion": "v1", "kind": "Namespace",
        "metadata": _metadata(name, None, labels, annotations),
    }


def opaque_secret(name, *, namespace=None, data=None, string_data=None,
                  labels=None, annotations=None):
    encoded = dict(data) if data is not None else {}
    plaintext = dict(string_data) if string_data is not None else {}
    if encoded.keys() & plaintext.keys():
        raise ValueError("data and string_data keys overlap")
    for key, value in encoded.items():
        required_string(key, "Secret key")
        if not isinstance(value, str):
            raise ValueError("Secret data values must be base64 strings")
        try:
            base64.b64decode(value, validate=True)
        except ValueError as cause:
            raise ValueError("Secret data must be valid base64") from cause
    for key, value in plaintext.items():
        required_string(key, "Secret key")
        if not isinstance(value, str):
            raise ValueError("Secret string_data values must be strings")
        encoded[key] = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return {
        "apiVersion": "v1", "kind": "Secret", "type": "Opaque",
        "metadata": _metadata(name, namespace, labels, annotations),
        "data": encoded,
    }


def basic_auth_secret(name, username, password, *, namespace=None):
    if username is None or password is None:
        raise ValueError("username and password must be supplied")
    result = opaque_secret(name, namespace=namespace, string_data={
        "username": str(username), "password": str(password),
    })
    result["type"] = "kubernetes.io/basic-auth"
    return result


def docker_registry_secret(name, server, username, password, *,
                           namespace=None, email=None):
    required_string(server, "server")
    if username is None or password is None:
        raise ValueError("username and password must be supplied")
    user, secret = str(username), str(password)
    auth = {
        "username": user, "password": secret,
        "auth": base64.b64encode(f"{user}:{secret}".encode()).decode("ascii"),
    }
    if email is not None:
        auth["email"] = str(email)
    result = opaque_secret(name, namespace=namespace, string_data={
        ".dockerconfigjson": json.dumps({"auths": {server: auth}}),
    })
    result["type"] = "kubernetes.io/dockerconfigjson"
    return result


def service_account_manifest(name, *, namespace=None, labels=None,
                             annotations=None, image_pull_secrets=None,
                             automount_service_account_token=None):
    result = {
        "apiVersion": "v1", "kind": "ServiceAccount",
        "metadata": _metadata(name, namespace, labels, annotations),
    }
    if image_pull_secrets is not None:
        result["imagePullSecrets"] = [
            {"name": required_string(name, "image pull Secret name")}
            for name in image_pull_secrets
        ]
    if automount_service_account_token is not None:
        if not isinstance(automount_service_account_token, bool):
            raise ValueError("automount_service_account_token must be boolean")
        result["automountServiceAccountToken"] = automount_service_account_token
    return result


def resource_requirements(*, requests=None, limits=None):
    parsed = {}
    for field, values in (("requests", requests), ("limits", limits)):
        if values is None:
            continue
        if not isinstance(values, Mapping):
            raise ValueError(f"{field} must be a resource quantity mapping")
        parsed[field] = {}
        for key, value in values.items():
            required_string(key, "resource key")
            required_string(value, "resource quantity")
            try:
                quantity = parse_quantity(value)
            except (ValueError, ArithmeticError) as cause:
                raise ValueError("Invalid Kubernetes resource quantity") from cause
            if not quantity.is_finite() or quantity < 0:
                raise ValueError("Resource quantities must be finite and non-negative")
            parsed[field][key] = quantity
    for key in parsed.get("requests", {}).keys() & parsed.get("limits", {}).keys():
        if parsed["requests"][key] > parsed["limits"][key]:
            raise ValueError(f"Request exceeds limit for {key}")
    return V1ResourceRequirements(
        requests=copy.deepcopy(requests), limits=copy.deepcopy(limits)
    )
