from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


AvailabilityState = Literal["healthy", "idle", "degraded", "down", "unknown"]


@dataclass(frozen=True)
class AvailabilitySnapshot:
    service: str
    state: AvailabilityState
    desired_replicas: int | None
    available_replicas: int | None
    ready_replicas: int | None
    updated_replicas: int | None
    reason: str


class KubernetesAvailabilityClient:
    """Read-only Deployment availability adapter.

    Deployment status already incorporates pod readiness and minimum-ready
    semantics. Keeping this adapter read-only avoids coupling availability
    detection to the separately gated remediation mutation path.
    """

    def __init__(
        self,
        namespace: str,
        *,
        apps_api: Any | None = None,
        request_timeout_seconds: float = 3.0,
    ):
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        self.namespace = namespace
        self._api = apps_api
        self.request_timeout_seconds = request_timeout_seconds

    def _api_client(self) -> Any:
        if self._api is not None:
            return self._api

        from kubernetes import client as kube_client, config as kube_config

        try:
            kube_config.load_incluster_config()
        except kube_config.ConfigException:
            kube_config.load_kube_config()
        self._api = kube_client.AppsV1Api()
        return self._api

    def snapshot(self, service: str) -> AvailabilitySnapshot:
        try:
            # Use the main Deployment resource instead of the /status
            # subresource so the existing read-only `deployments` RBAC rule is
            # sufficient; no additional permission is required.
            deployment = self._api_client().read_namespaced_deployment(
                service,
                self.namespace,
                _request_timeout=(
                    self.request_timeout_seconds,
                    self.request_timeout_seconds,
                ),
            )
            desired = (
                int(deployment.spec.replicas)
                if deployment.spec.replicas is not None
                else 1
            )
            available = int(deployment.status.available_replicas or 0)
            ready = int(deployment.status.ready_replicas or 0)
            updated = int(deployment.status.updated_replicas or 0)

            if desired == 0:
                state: AvailabilityState = "idle"
                reason = "deployment_intentionally_scaled_to_zero"
            elif available == 0 or ready == 0:
                state = "down"
                reason = "no_available_or_ready_replicas"
            elif available < desired or ready < desired:
                state = "degraded"
                reason = "partial_replica_availability"
            else:
                state = "healthy"
                reason = "desired_replicas_ready"

            return AvailabilitySnapshot(
                service=service,
                state=state,
                desired_replicas=desired,
                available_replicas=available,
                ready_replicas=ready,
                updated_replicas=updated,
                reason=reason,
            )
        except Exception as exc:
            return AvailabilitySnapshot(
                service=service,
                state="unknown",
                desired_replicas=None,
                available_replicas=None,
                ready_replicas=None,
                updated_replicas=None,
                reason=f"kubernetes_api_unavailable:{type(exc).__name__}",
            )
