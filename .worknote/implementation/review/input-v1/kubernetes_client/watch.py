"""Finite watch streams and UID-bound GET polling."""

import json
import time
from threading import Event

from kubernetes.client.exceptions import ApiException
from kubernetes.watch import Watch

from .client import positive_seconds, required_string
from .errors import (
    ApiRequestError, ResourceChangedError, ResourceNotReadyError,
    ResourceReplacedError, ResponseFormatError, UnsupportedOperationError,
    WaitCancelledError, WaitTimeoutError,
)
from .resources import _object_missing


class _StrictWatch(Watch):
    def unmarshal_event(self, data, return_type):
        try:
            event = json.loads(data)
        except (ValueError, UnicodeError) as cause:
            raise ResponseFormatError("Invalid watch JSON") from cause
        if not isinstance(event, dict) or event.get("type") not in (
            "ADDED", "MODIFIED", "DELETED", "BOOKMARK", "ERROR",
        ) or not isinstance(event.get("object"), dict):
            raise ResponseFormatError("Invalid watch event")
        obj = event["object"]
        if event["type"] == "ERROR":
            if not isinstance(obj.get("code"), int):
                raise ResponseFormatError("Watch ERROR requires status code")
            error = ApiException(status=obj["code"], reason=obj.get("reason"))
            error.body = json.dumps(obj)
            raise error
        metadata = obj.get("metadata")
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("resourceVersion"), str
        ) or not metadata["resourceVersion"]:
            raise ResponseFormatError("Watch object requires resourceVersion")
        self.resource_version = metadata["resourceVersion"]
        event["raw_object"] = obj
        return event


class ResourceWatch:
    def __init__(self, resource, *, name=None, all_namespaces=False,
                 label_selector=None, field_selector=None, resource_version=None,
                 timeout_seconds=300, allow_watch_bookmarks=True):
        positive_seconds(timeout_seconds, "timeout_seconds")
        if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool):
            raise ValueError("Watch timeout_seconds must be an integer")
        self._resource = resource
        self._descriptor = resource._resolve("watch")
        self._namespace = resource._select_namespace(
            self._descriptor, all_namespaces=all_namespaces
        )
        if name is not None:
            required_string(name, "name")
            selection = f"metadata.name={name}"
            field_selector = f"{field_selector},{selection}" if field_selector else selection
        self._options = dict(
            label_selector=label_selector, field_selector=field_selector,
            resource_version=resource_version, timeout_seconds=timeout_seconds,
            allow_watch_bookmarks=allow_watch_bookmarks,
        )
        self._watch = _StrictWatch()
        self._iterator = None
        self._closed = False
        resource._client._streams.add(self)

    def _fetch(self, **options):
        self._resource._client._ensure_open()
        return self._resource._client._dynamic_client.request(
            "get", self._descriptor.path(namespace=self._namespace),
            serialize=False, **options,
        )

    def _events(self):
        try:
            for event in self._watch.stream(self._fetch, **self._options):
                self._resource._client._ensure_open()
                yield {
                    "type": event["type"], "object": event["object"],
                    "resource_version": self._watch.resource_version,
                }
        except ApiException as cause:
            raise ApiRequestError(cause) from cause
        finally:
            self._finish()

    def __iter__(self):
        if self._closed:
            raise ValueError("Watch stream is closed")
        if self._iterator is None:
            self._iterator = self._events()
        return self._iterator

    def _finish(self):
        self._closed = True
        self._watch.stop()
        self._watch._api_client.close()
        self._resource._client._streams.discard(self)

    def stop(self):
        self.close()

    def close(self):
        if self._closed:
            return
        self._watch.stop()
        response = getattr(self._watch, "_resp", None)
        if response is not None:
            response.close()
            response.release_conn()
        if self._iterator is not None:
            self._iterator.close()
        self._finish()

    def __enter__(self):
        if self._closed:
            raise ValueError("Watch stream is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def _wait(resource, name, *, expected_uid, target_generation,
          timeout_seconds, poll_interval, cancel_event, deleted):
    required_string(name, "name")
    if expected_uid is not None:
        required_string(expected_uid, "expected_uid")
    if target_generation is not None and (
        isinstance(target_generation, bool)
        or not isinstance(target_generation, int) or target_generation < 1
    ):
        raise ValueError("target_generation must be a positive integer")
    timeout = positive_seconds(timeout_seconds, "timeout_seconds")
    interval = positive_seconds(poll_interval, "poll_interval")
    descriptor = resource._resolve("get")
    namespace = resource._select_namespace(descriptor)
    cancellation = cancel_event if cancel_event is not None else Event()
    deadline = time.monotonic() + timeout
    while True:
        if cancellation.is_set():
            raise WaitCancelledError("Resource wait cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WaitTimeoutError("Resource wait timed out")
        request_timeout = tuple(
            min(value, remaining) for value in resource._client.request_timeout
        )
        try:
            value = resource._request(
                descriptor, "get", name=name, namespace=namespace,
                _request_timeout=request_timeout,
            )
        except ApiRequestError as error:
            if not (deleted and _object_missing(error, descriptor, name)):
                raise
            value = None
        if cancellation.is_set():
            raise WaitCancelledError("Resource wait cancelled")
        if time.monotonic() >= deadline:
            raise WaitTimeoutError("Resource wait timed out")
        if value is None:
            return None
        metadata = value.get("metadata")
        if not isinstance(metadata, dict):
            raise ResponseFormatError("Wait response requires metadata")
        uid = required_string(metadata.get("uid"), "response metadata.uid")
        if expected_uid is None:
            expected_uid = uid
        if uid != expected_uid:
            raise ResourceReplacedError("Resource UID changed during wait")
        if not deleted:
            if resource.kind == "Deployment":
                generation = metadata.get("generation")
                if not isinstance(generation, int) or isinstance(generation, bool):
                    raise ResponseFormatError("Deployment requires generation")
                if target_generation is None:
                    target_generation = generation
                if generation != target_generation:
                    raise ResourceChangedError("Deployment generation changed")
            if _ready(resource.kind, value, target_generation):
                return value
        remaining = deadline - time.monotonic()
        cancellation.wait(min(interval, max(remaining, 0)))


def _ready(kind, value, generation):
    metadata = value["metadata"]
    status = value.get("status") or {}
    conditions = status.get("conditions") or []
    if kind == "Pod":
        if status.get("phase") in ("Failed", "Succeeded"):
            raise ResourceNotReadyError("Pod entered a terminal phase")
        return not metadata.get("deletionTimestamp") and any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in conditions
        )
    if any(c.get("type") == "Progressing" and c.get("status") == "False"
           and c.get("reason") == "ProgressDeadlineExceeded" for c in conditions):
        raise ResourceNotReadyError("Deployment exceeded its progress deadline")
    desired = value.get("spec", {}).get("replicas", 1)
    return (
        not metadata.get("deletionTimestamp")
        and status.get("observedGeneration", 0) >= generation
        and status.get("updatedReplicas", 0) == desired
        and status.get("availableReplicas", 0) >= desired
        and status.get("replicas", 0) == desired
    )


def wait_ready(resource, name, *, expected_uid=None, target_generation=None,
               timeout_seconds=120, poll_interval=1.0, cancel_event=None):
    if (resource.api_version, resource.kind) not in (
        ("v1", "Pod"), ("apps/v1", "Deployment"),
    ):
        raise UnsupportedOperationError("wait_ready supports Pod and Deployment")
    if resource.kind == "Pod" and target_generation is not None:
        raise ValueError("Pod readiness cannot observe a target generation")
    return _wait(
        resource, name, expected_uid=expected_uid,
        target_generation=target_generation, timeout_seconds=timeout_seconds,
        poll_interval=poll_interval, cancel_event=cancel_event, deleted=False,
    )


def wait_deleted(resource, name, *, expected_uid, timeout_seconds=120,
                 poll_interval=1.0, cancel_event=None):
    required_string(expected_uid, "expected_uid")
    return _wait(
        resource, name, expected_uid=expected_uid, target_generation=None,
        timeout_seconds=timeout_seconds, poll_interval=poll_interval,
        cancel_event=cancel_event, deleted=True,
    )
