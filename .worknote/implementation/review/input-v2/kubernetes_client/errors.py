"""Explicit failures for the high-level interface."""


class KubernetesError(Exception):
    """Base error for facade validation and operations."""


class ConfigurationError(KubernetesError, ValueError):
    pass


class ClientClosedError(KubernetesError):
    pass


class ResourceNotServedError(KubernetesError):
    pass


class AmbiguousResourceError(KubernetesError):
    pass


class UnsupportedOperationError(KubernetesError):
    pass


class ApiRequestError(KubernetesError):
    """Retain SDK evidence without including response bodies in messages."""

    def __init__(self, cause):
        self.status = cause.status
        self.reason = cause.reason
        self.headers = cause.headers
        self.body = cause.body
        super().__init__(f"Kubernetes API request failed (HTTP {self.status})")


class DiscoveryRequestError(ApiRequestError):
    pass


class ResponseFormatError(KubernetesError):
    pass


class DiscoveryFormatError(ResponseFormatError):
    pass


class PaginationError(KubernetesError):
    pass


class WaitTimeoutError(KubernetesError, TimeoutError):
    pass


class WaitCancelledError(KubernetesError):
    pass


class ResourceReplacedError(KubernetesError):
    pass


class ResourceChangedError(KubernetesError):
    pass


class ResourceNotReadyError(KubernetesError):
    pass
