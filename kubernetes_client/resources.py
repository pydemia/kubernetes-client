"""Common resource operations using exact, discovered GVKs."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from collections.abc import Iterator
from threading import Event
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from kubernetes.client import V1DeleteOptions, V1Preconditions
from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from kubernetes.dynamic.resource import ResourceInstance, ResourceList

from .client import UNSET, _Unset, required_string
from .errors import (
    AmbiguousResourceError,
    ApiRequestError,
    DiscoveryFormatError,
    DiscoveryRequestError,
    PaginationError,
    ResourceNotServedError,
    ResponseFormatError,
    UnsupportedOperationError,
)

if TYPE_CHECKING:
    from .client import KubernetesClient
    from .watch import ResourceWatch


class _DiscoveryClient(DynamicClient):
    def __init__(self, api_client, *, cache_file, request_timeout):
        self._default_timeout = request_timeout
        super().__init__(api_client, cache_file=cache_file)

    def request(self, method, path, body=None, **params):
        route = "/" + path.strip("/")
        discovery = bool(
            re.fullmatch(
                r"/(version|api|apis|api/[^/]+|apis/[^/]+/[^/]+)", route
            )
        )
        serialize = params.pop("serialize", True)
        serializer = params.pop("serializer", ResourceInstance)
        params.setdefault("_request_timeout", self._default_timeout)
        # SDK mutates query/header arguments while preparing each request.
        params["query_params"] = list(params.get("query_params", []))
        params["header_params"] = dict(params.get("header_params", {}))
        try:
            response = super().request(
                method, path, body=body, serialize=False, **params
            )
        except ApiException as cause:
            if discovery:
                raise DiscoveryRequestError(cause) from cause
            raise
        if not serialize and not discovery:
            return response
        try:
            try:
                value = json.loads(response.data.decode("utf-8"))
            except (ValueError, UnicodeError) as cause:
                error = (
                    DiscoveryFormatError if discovery else ResponseFormatError
                )
                raise error("Invalid JSON in Kubernetes response") from cause
            if discovery:
                self._validate_discovery(route, value)
            return serializer(self, value) if serialize else value
        finally:
            response.close()
            response.release_conn()

    @staticmethod
    def _validate_discovery(route, value):
        if not isinstance(value, dict):
            raise DiscoveryFormatError("Discovery response must be an object")
        expected_kind = {
            "/api": "APIVersions",
            "/apis": "APIGroupList",
        }.get(route, "APIResourceList")
        if route != "/version" and value.get("kind") != expected_kind:
            raise DiscoveryFormatError("Invalid discovery kind")
        field = (
            "gitVersion"
            if route == "/version"
            else (
                "groups"
                if route == "/apis"
                else ("versions" if route == "/api" else "resources")
            )
        )
        expected = str if field == "gitVersion" else list
        if not isinstance(value.get(field), expected) or (
            field == "gitVersion" and not value[field]
        ):
            raise DiscoveryFormatError(f"Discovery response requires {field}")
        if field == "resources":
            for item in value[field]:
                if not isinstance(item, dict) or not (
                    isinstance(item.get("name"), str)
                    and bool(item["name"])
                    and isinstance(item.get("kind"), str)
                    and bool(item["kind"])
                    and isinstance(item.get("namespaced"), bool)
                    and isinstance(item.get("verbs"), list)
                    and all(isinstance(verb, str) for verb in item["verbs"])
                ):
                    raise DiscoveryFormatError("Invalid APIResource entry")
        elif field == "groups":
            for group in value[field]:
                if not isinstance(group, dict) or not (
                    isinstance(group.get("name"), str)
                    and bool(group["name"].strip())
                    and isinstance(group.get("versions"), list)
                    and bool(group["versions"])
                    and isinstance(group.get("preferredVersion"), dict)
                ):
                    raise DiscoveryFormatError("Invalid APIGroup entry")
                for version in group["versions"]:
                    if not isinstance(version, dict) or not all(
                        isinstance(version.get(key), str)
                        and bool(version[key])
                        and version[key] == version[key].strip()
                        for key in ("groupVersion", "version")
                    ):
                        raise DiscoveryFormatError("Invalid group version")
                    if (
                        version["groupVersion"]
                        != f"{group['name']}/{version['version']}"
                    ):
                        raise DiscoveryFormatError(
                            "Contradictory group version"
                        )
                if not all(
                    isinstance(group["preferredVersion"].get(key), str)
                    and bool(group["preferredVersion"][key])
                    and group["preferredVersion"][key]
                    == group["preferredVersion"][key].strip()
                    for key in ("groupVersion", "version")
                ):
                    raise DiscoveryFormatError(
                        "Invalid preferred group version"
                    )
                if not any(
                    all(
                        group["preferredVersion"][key] == version[key]
                        for key in ("groupVersion", "version")
                    )
                    for version in group["versions"]
                ):
                    raise DiscoveryFormatError(
                        "Preferred version is not served"
                    )


@dataclass(frozen=True)
class DeleteResult:
    action: str
    response: dict[str, Any] | None


def _object_missing(error, descriptor, name):
    if error.status != 404:
        return False
    try:
        status = json.loads(error.body)
    except (TypeError, ValueError):
        return False
    if not isinstance(status, dict):
        return False
    details = status.get("details")
    return (
        status.get("kind") == "Status"
        and status.get("reason") == "NotFound"
        and isinstance(details, dict)
        and details.get("name") == name
        and details.get("kind") == descriptor.name
        and details.get("group", "") == descriptor.group
    )


class ResourceOperations:
    def __init__(
        self,
        client: KubernetesClient,
        api_version: str,
        kind: str,
        *,
        namespace: str | _Unset = UNSET,
    ):
        self._client = client
        self.api_version = required_string(api_version, "api_version")
        self.kind = required_string(kind, "kind")
        if namespace is not UNSET:
            required_string(namespace, "namespace")
        self._namespace = namespace

    def _resolve(self, verb):
        dynamic = self._client._dynamic_client
        group, separator, version = self.api_version.partition("/")
        if not separator:
            group, version = "", group
        try:
            matches = dynamic.resources.search(
                prefix="apis" if group else "api",
                group=group,
                api_version=version,
                kind=self.kind,
            )
        except ResourceNotFoundError as cause:
            raise ResourceNotServedError(
                f"Resource not served: {self.api_version}/{self.kind}"
            ) from cause
        # Search must not choose a preferred version or a ResourceList.
        matches = [
            r
            for r in matches
            if (
                r.group_version == self.api_version
                and r.kind == self.kind
                and not isinstance(r, ResourceList)
            )
        ]
        if not matches:
            raise ResourceNotServedError(
                f"Resource not served: {self.api_version}/{self.kind}"
            )
        if len(matches) != 1:
            raise AmbiguousResourceError(
                f"Multiple resources: {self.api_version}/{self.kind}"
            )
        descriptor = matches[0]
        if verb not in descriptor.verbs:
            raise UnsupportedOperationError(
                f"{verb} is not served for {self.kind}"
            )
        return descriptor

    def _select_namespace(self, descriptor, body=None, all_namespaces=False):
        if not isinstance(all_namespaces, bool):
            raise ValueError("all_namespaces must be a boolean")
        metadata = (body or {}).get("metadata", {})
        supplied = "namespace" in metadata
        body_namespace = metadata.get("namespace")
        if not descriptor.namespaced:
            if self._namespace is not UNSET or supplied:
                raise ValueError("Cluster resources cannot have a namespace")
            if all_namespaces:
                raise ValueError(
                    "all_namespaces requires a namespaced resource"
                )
            return None
        if all_namespaces:
            if self._namespace is not UNSET:
                raise ValueError(
                    "all_namespaces conflicts with bound namespace"
                )
            return None
        if supplied:
            required_string(body_namespace, "metadata.namespace")
        if self._namespace is not UNSET:
            if supplied and body_namespace != self._namespace:
                raise ValueError(
                    "Body namespace conflicts with bound namespace"
                )
            return self._namespace
        return body_namespace if supplied else self._client.default_namespace

    def _body(self, body, *, full=False):
        if isinstance(body, dict):
            result = copy.deepcopy(body)
        else:
            result = self._client.api_client.sanitize_for_serialization(body)
            if not isinstance(result, dict):
                raise ValueError("Body must be a manifest or an SDK model")
        for field, expected in (
            ("apiVersion", self.api_version),
            ("kind", self.kind),
        ):
            if field in result and result[field] != expected:
                raise ValueError(
                    f"Body {field} conflicts with resource binding"
                )
            if full:
                result.setdefault(field, expected)
        if "metadata" not in result:
            result["metadata"] = {}
        metadata = result["metadata"]
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        for field in ("name", "generateName", "namespace"):
            if field in metadata:
                required_string(metadata[field], f"metadata.{field}")
        return result

    def _write_body(self, descriptor, body, *, full=False):
        result = self._body(body, full=full)
        namespace = self._select_namespace(descriptor, result)
        if descriptor.namespaced:
            result["metadata"].setdefault("namespace", namespace)
        return result, namespace

    @staticmethod
    def _validation(field_validation, options):
        if field_validation not in ("Ignore", "Warn", "Strict"):
            raise ValueError("field_validation must be Ignore, Warn or Strict")
        options["query_params"] = [("fieldValidation", field_validation)]
        return options

    def _request(
        self,
        descriptor,
        method,
        *,
        name=None,
        namespace=None,
        body=None,
        **options,
    ):
        self._client._ensure_open()
        if name is not None:
            required_string(name, "name")
        # Resource.path does not escape name or namespace.
        path = descriptor.path(
            name=quote(name, safe="") if name is not None else None,
            namespace=quote(namespace, safe="") if namespace else None,
        )
        try:
            value = self._client._dynamic_client.request(
                method,
                path,
                body=body,
                serializer=lambda _, response: response,
                **options,
            )
        except ApiException as cause:
            raise ApiRequestError(cause) from cause
        if not isinstance(value, dict):
            raise ResponseFormatError("Resource response must be an object")
        return value

    def get(self, name: str) -> dict[str, Any]:
        required_string(name, "name")
        descriptor = self._resolve("get")
        return self._request(
            descriptor,
            "get",
            name=name,
            namespace=self._select_namespace(descriptor),
        )

    def exists(self, name: str) -> bool:
        required_string(name, "name")
        descriptor = self._resolve("get")
        try:
            self._request(
                descriptor,
                "get",
                name=name,
                namespace=self._select_namespace(descriptor),
            )
            return True
        except ApiRequestError as error:
            if _object_missing(error, descriptor, name):
                return False
            raise

    def list(
        self,
        *,
        all_namespaces: bool = False,
        label_selector: str | None = None,
        field_selector: str | None = None,
        limit: int | None = None,
        continue_token: str | None = None,
        resource_version: str | None = None,
        resource_version_match: str | None = None,
    ) -> dict[str, Any]:
        descriptor = self._resolve("list")
        namespace = self._select_namespace(
            descriptor, all_namespaces=all_namespaces
        )
        options: dict[str, Any] = dict(
            label_selector=label_selector,
            field_selector=field_selector,
            limit=limit,
            _continue=continue_token,
            resource_version=resource_version,
        )
        if resource_version_match is not None:
            if resource_version_match not in ("Exact", "NotOlderThan"):
                raise ValueError(
                    "resource_version_match must be Exact or NotOlderThan"
                )
            options["query_params"] = [
                ("resourceVersionMatch", resource_version_match)
            ]
        value = self._request(
            descriptor, "get", namespace=namespace, **options
        )
        if not isinstance(value.get("items"), list) or not isinstance(
            value.get("metadata"), dict
        ):
            raise ResponseFormatError(
                "List response requires items and metadata"
            )
        return value

    def iter_items(self, **options: Any) -> Iterator[dict[str, Any]]:
        seen = set()
        snapshot: str | _Unset = UNSET
        while True:
            page = self.list(**options)
            version = page["metadata"].get("resourceVersion")
            if not isinstance(version, str) or not version:
                raise PaginationError("List snapshot requires resourceVersion")
            if snapshot is UNSET:
                snapshot = version
            elif version != snapshot:
                raise PaginationError("List snapshot resourceVersion changed")
            token = page["metadata"].get("continue", "")
            if not isinstance(token, str):
                raise PaginationError("Continuation token must be a string")
            if token and token in seen:
                raise PaginationError("Continuation token repeated")
            yield from page["items"]
            if not token:
                return
            seen.add(token)
            options = dict(options, continue_token=token)
            options.pop("resource_version", None)
            options.pop("resource_version_match", None)

    def create(
        self,
        body: Any,
        *,
        field_validation: str = "Strict",
        dry_run: str | None = None,
    ) -> dict[str, Any]:
        descriptor = self._resolve("create")
        value, namespace = self._write_body(descriptor, body, full=True)
        if not (
            value["metadata"].get("name")
            or value["metadata"].get("generateName")
        ):
            raise ValueError("create requires name or generateName")
        return self._request(
            descriptor,
            "post",
            namespace=namespace,
            body=value,
            **self._validation(field_validation, {"dry_run": dry_run}),
        )

    def patch(
        self,
        name: str,
        body: Any,
        *,
        patch_type: str = "merge",
        field_validation: str = "Strict",
        dry_run: str | None = None,
    ) -> dict[str, Any]:
        required_string(name, "name")
        descriptor = self._resolve("patch")
        if patch_type == "json":
            if not isinstance(body, list):
                raise ValueError("JSON Patch body must be an array")
            value = copy.deepcopy(body)
            namespace = self._select_namespace(descriptor)
            content_type = "application/json-patch+json"
        elif patch_type == "merge":
            value, namespace = self._write_body(descriptor, body)
            if (
                "name" in value["metadata"]
                and value["metadata"]["name"] != name
            ):
                raise ValueError("Body name conflicts with request name")
            content_type = "application/merge-patch+json"
        else:
            raise ValueError("patch_type must be merge or json")
        return self._request(
            descriptor,
            "patch",
            name=name,
            namespace=namespace,
            body=value,
            content_type=content_type,
            **self._validation(field_validation, {"dry_run": dry_run}),
        )

    def replace(
        self,
        body: Any,
        *,
        field_validation: str = "Strict",
        dry_run: str | None = None,
    ) -> dict[str, Any]:
        descriptor = self._resolve("update")
        value, namespace = self._write_body(descriptor, body, full=True)
        name = required_string(value["metadata"].get("name"), "metadata.name")
        required_string(
            value["metadata"].get("resourceVersion"),
            "metadata.resourceVersion",
        )
        return self._request(
            descriptor,
            "put",
            name=name,
            namespace=namespace,
            body=value,
            **self._validation(field_validation, {"dry_run": dry_run}),
        )

    def apply(
        self,
        body: Any,
        *,
        field_manager: str | None = None,
        force: bool = False,
        field_validation: str = "Strict",
        dry_run: str | None = None,
    ) -> dict[str, Any]:
        descriptor = self._resolve("patch")
        value, namespace = self._write_body(descriptor, body, full=True)
        name = required_string(value["metadata"].get("name"), "metadata.name")
        if (
            self.api_version == "v1"
            and self.kind == "Secret"
            and "stringData" in value
        ):
            raise ValueError("Secret apply requires data; use a Secret helper")
        manager = (
            self._client.field_manager
            if field_manager is None
            else (required_string(field_manager, "field_manager"))
        )
        if not isinstance(force, bool):
            raise ValueError("force must be a boolean")
        self._client._ensure_open()
        options = self._validation(field_validation, {"dry_run": dry_run})
        try:
            result = self._client._dynamic_client.server_side_apply(
                descriptor,
                body=value,
                name=quote(name, safe=""),
                namespace=quote(namespace, safe="") if namespace else None,
                field_manager=manager,
                force_conflicts=force,
                serializer=lambda _, response: response,
                **options,
            )
        except ApiException as cause:
            raise ApiRequestError(cause) from cause
        if not isinstance(result, dict):
            raise ResponseFormatError("Resource response must be an object")
        return result

    def delete(
        self,
        name: str,
        *,
        ignore_not_found: bool = False,
        expected_uid: str | None = None,
        resource_version: str | None = None,
        propagation_policy: str | None = None,
        grace_period_seconds: int | None = None,
    ) -> DeleteResult:
        required_string(name, "name")
        if not isinstance(ignore_not_found, bool):
            raise ValueError("ignore_not_found must be a boolean")
        descriptor = self._resolve("delete")
        if expected_uid is not None:
            required_string(expected_uid, "expected_uid")
        if resource_version is not None:
            required_string(resource_version, "resource_version")
        if propagation_policy not in (
            None,
            "Foreground",
            "Background",
            "Orphan",
        ):
            raise ValueError("Invalid propagation_policy")
        if grace_period_seconds is not None and (
            isinstance(grace_period_seconds, bool)
            or not isinstance(grace_period_seconds, int)
            or grace_period_seconds < 0
        ):
            raise ValueError(
                "grace_period_seconds must be a non-negative integer"
            )
        preconditions = None
        if expected_uid is not None or resource_version is not None:
            preconditions = V1Preconditions(
                uid=expected_uid, resource_version=resource_version
            )
        body = self._client.api_client.sanitize_for_serialization(
            V1DeleteOptions(
                preconditions=preconditions,
                propagation_policy=propagation_policy,
                grace_period_seconds=grace_period_seconds,
            )
        )
        try:
            response = self._request(
                descriptor,
                "delete",
                name=name,
                namespace=self._select_namespace(descriptor),
                body=body,
            )
            return DeleteResult("requested", response)
        except ApiRequestError as error:
            if ignore_not_found and _object_missing(error, descriptor, name):
                return DeleteResult("already_absent", None)
            raise

    def watch(
        self,
        *,
        name: str | None = None,
        all_namespaces: bool = False,
        label_selector: str | None = None,
        field_selector: str | None = None,
        resource_version: str | None = None,
        timeout_seconds: int = 300,
        allow_watch_bookmarks: bool = True,
    ) -> ResourceWatch:
        from .watch import ResourceWatch

        return ResourceWatch(
            self,
            name=name,
            all_namespaces=all_namespaces,
            label_selector=label_selector,
            field_selector=field_selector,
            resource_version=resource_version,
            timeout_seconds=timeout_seconds,
            allow_watch_bookmarks=allow_watch_bookmarks,
        )

    def wait_ready(
        self,
        name: str,
        *,
        expected_uid: str | None = None,
        target_generation: int | None = None,
        timeout_seconds: float = 120,
        poll_interval: float = 1.0,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        from .watch import wait_ready

        return wait_ready(
            self,
            name,
            expected_uid=expected_uid,
            target_generation=target_generation,
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
            cancel_event=cancel_event,
        )

    def wait_deleted(
        self,
        name: str,
        *,
        expected_uid: str,
        timeout_seconds: float = 120,
        poll_interval: float = 1.0,
        cancel_event: Event | None = None,
    ) -> None:
        from .watch import wait_deleted

        return wait_deleted(
            self,
            name,
            expected_uid=expected_uid,
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
            cancel_event=cancel_event,
        )
