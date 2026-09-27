"""Isolated authentication, discovery and connection ownership."""

from __future__ import annotations

import copy
import math
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kubernetes import config
from kubernetes.client import ApiClient, Configuration
from urllib3 import PoolManager, ProxyManager

from .errors import ClientClosedError, ConfigurationError

if TYPE_CHECKING:
    from .resources import ResourceOperations


class _Unset:
    pass


UNSET = _Unset()


def required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def positive_seconds(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be positive and finite")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be positive and finite")
    return float(value)


class KubernetesClient:
    """Use the factories to select credentials without global defaults."""

    def __init__(
        self,
        api_client,
        *,
        owns_api_client=False,
        default_namespace="default",
        field_manager="kubernetes-client",
        request_timeout=(5.0, 30.0),
    ):
        self.default_namespace = required_string(
            default_namespace, "default_namespace"
        )
        self.field_manager = required_string(field_manager, "field_manager")
        if not isinstance(request_timeout, tuple) or len(request_timeout) != 2:
            raise ConfigurationError(
                "request_timeout requires (connect, read)"
            )
        self.request_timeout = tuple(
            positive_seconds(v, "request_timeout") for v in request_timeout
        )
        self._check_transport(api_client)
        self._api_client = api_client
        self._owns_api_client = owns_api_client
        self._dynamic: Any = None
        self._cache = None
        self._streams: set[Any] = set()
        self._closed = False

    @staticmethod
    def _check_transport(api_client):
        if not isinstance(api_client, ApiClient):
            raise ConfigurationError("An official ApiClient is required")
        pool = api_client.rest_client.pool_manager
        pool_type = type(pool)
        official = pool_type in (PoolManager, ProxyManager) or (
            pool_type.__module__ == "urllib3.contrib.socks"
            and pool_type.__name__ == "SOCKSProxyManager"
        )
        if not official:
            raise ConfigurationError(
                "An official urllib3 transport is required"
            )

        def disabled(retries):
            return (
                retries is False
                or (isinstance(retries, int) and retries == 0)
                or getattr(retries, "total", None) == 0
            )

        if not disabled(pool.connection_pool_kw.get("retries")):
            raise ConfigurationError(
                "Create ApiClient with Configuration.retries=0"
            )
        # Existing connections can retain a policy from before a caller edit.
        for key in pool.pools.keys():
            connection_pool = pool.pools.get(key)
            if connection_pool is not None and not disabled(
                connection_pool.retries
            ):
                raise ConfigurationError(
                    "An existing connection pool has retries"
                )

    @classmethod
    def from_configuration(
        cls, configuration: Configuration, **options: Any
    ) -> KubernetesClient:
        isolated = copy.deepcopy(configuration)
        isolated.retries = 0
        api_client = ApiClient(isolated)
        try:
            return cls(api_client, owns_api_client=True, **options)
        except Exception:
            cls._close_api_client(api_client)
            raise

    @classmethod
    def from_api_client(
        cls, api_client: ApiClient, **options: Any
    ) -> KubernetesClient:
        return cls(api_client, owns_api_client=False, **options)

    @classmethod
    def from_kubeconfig(
        cls,
        config_file: str | Path | None = None,
        *,
        context: str | None = None,
        persist_config: bool = False,
        **options: Any,
    ) -> KubernetesClient:
        isolated = Configuration()
        config.load_kube_config(
            config_file=config_file,
            context=context,
            client_configuration=isolated,
            persist_config=persist_config,
        )
        return cls.from_configuration(isolated, **options)

    @classmethod
    def from_kubeconfig_dict(
        cls,
        config_dict: dict[str, Any],
        *,
        context: str | None = None,
        persist_config: bool = False,
        **options: Any,
    ) -> KubernetesClient:
        isolated = Configuration()
        config.load_kube_config_from_dict(
            copy.deepcopy(config_dict),
            context=context,
            client_configuration=isolated,
            persist_config=persist_config,
        )
        return cls.from_configuration(isolated, **options)

    @classmethod
    def from_incluster(cls, **options: Any) -> KubernetesClient:
        isolated = Configuration()
        config.load_incluster_config(client_configuration=isolated)
        return cls.from_configuration(isolated, **options)

    def _ensure_open(self):
        if self._closed:
            raise ClientClosedError("KubernetesClient is closed")
        self._check_transport(self._api_client)

    @property
    def api_client(self) -> ApiClient:
        self._ensure_open()
        return self._api_client

    @property
    def _dynamic_client(self):
        self._ensure_open()
        if self._dynamic is None:
            from .resources import _DiscoveryClient

            cache = tempfile.TemporaryDirectory(prefix="kubernetes-client-")
            try:
                dynamic = _DiscoveryClient(
                    self._api_client,
                    cache_file=str(Path(cache.name) / "discovery.json"),
                    request_timeout=self.request_timeout,
                )
            except Exception:
                cache.cleanup()
                raise
            self._cache = cache
            self._dynamic = dynamic
        return self._dynamic

    def refresh_discovery(self) -> None:
        self._dynamic_client.resources.invalidate_cache()

    def resource(
        self, api_version: str, kind: str, *, namespace: str | _Unset = UNSET
    ) -> ResourceOperations:
        from .resources import ResourceOperations

        self._ensure_open()
        return ResourceOperations(self, api_version, kind, namespace=namespace)

    @property
    def pods(self) -> ResourceOperations:
        return self.resource("v1", "Pod")

    @property
    def namespaces(self) -> ResourceOperations:
        return self.resource("v1", "Namespace")

    @property
    def secrets(self) -> ResourceOperations:
        return self.resource("v1", "Secret")

    @property
    def service_accounts(self) -> ResourceOperations:
        return self.resource("v1", "ServiceAccount")

    @property
    def deployments(self) -> ResourceOperations:
        return self.resource("apps/v1", "Deployment")

    @property
    def services(self) -> ResourceOperations:
        return self.resource("v1", "Service")

    @property
    def config_maps(self) -> ResourceOperations:
        return self.resource("v1", "ConfigMap")

    @property
    def jobs(self) -> ResourceOperations:
        return self.resource("batch/v1", "Job")

    @property
    def cron_jobs(self) -> ResourceOperations:
        return self.resource("batch/v1", "CronJob")

    @staticmethod
    def _close_api_client(api_client):
        try:
            api_client.close()
        finally:
            # SDK 36 close only joins its asynchronous thread pool.
            if not callable(getattr(api_client.rest_client, "close", None)):
                api_client.rest_client.pool_manager.clear()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            for stream in tuple(self._streams):
                stream.close()
        finally:
            try:
                if self._owns_api_client:
                    self._close_api_client(self._api_client)
            finally:
                if self._cache is not None:
                    self._cache.cleanup()

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
