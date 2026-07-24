from types import SimpleNamespace

import pytest

from app.availability import (
    AvailabilitySnapshot,
    KubernetesAvailabilityClient,
)


class FakeAppsApi:
    def __init__(
        self,
        *,
        desired=1,
        available=1,
        ready=1,
        updated=1,
        error=None,
    ):
        self.desired = desired
        self.available = available
        self.ready = ready
        self.updated = updated
        self.error = error
        self.request_timeout = None

    def read_namespaced_deployment(
        self, service, namespace, *, _request_timeout=None
    ):
        self.request_timeout = _request_timeout
        if self.error:
            raise self.error
        return SimpleNamespace(
            spec=SimpleNamespace(replicas=self.desired),
            status=SimpleNamespace(
                available_replicas=self.available,
                ready_replicas=self.ready,
                updated_replicas=self.updated,
            ),
        )


def snapshot(**overrides):
    api = FakeAppsApi(**overrides)
    return KubernetesAvailabilityClient("techx-tf4", apps_api=api).snapshot(
        "checkout"
    )


def test_availability_adapter_classifies_healthy_idle_degraded_and_down():
    assert snapshot().state == "healthy"
    assert snapshot(desired=0, available=0, ready=0, updated=0).state == "idle"
    assert snapshot(desired=2, available=1, ready=1, updated=2).state == "degraded"
    assert snapshot(desired=2, available=0, ready=0, updated=2).state == "down"


def test_availability_adapter_fails_unknown_not_down():
    result = snapshot(error=RuntimeError("API unavailable"))

    assert result.state == "unknown"
    assert result.desired_replicas is None
    assert result.reason == "kubernetes_api_unavailable:RuntimeError"


def test_availability_adapter_bounds_connect_and_read_time():
    api = FakeAppsApi()
    client = KubernetesAvailabilityClient(
        "techx-tf4",
        apps_api=api,
        request_timeout_seconds=2.5,
    )

    assert client.snapshot("checkout").state == "healthy"
    assert api.request_timeout == (2.5, 2.5)


def test_availability_adapter_rejects_non_positive_timeout():
    with pytest.raises(
        ValueError, match="request_timeout_seconds must be positive"
    ):
        KubernetesAvailabilityClient(
            "techx-tf4",
            apps_api=FakeAppsApi(),
            request_timeout_seconds=0,
        )


def test_snapshot_fields_are_auditable():
    result = snapshot(desired=3, available=2, ready=2, updated=3)

    assert result == AvailabilitySnapshot(
        service="checkout",
        state="degraded",
        desired_replicas=3,
        available_replicas=2,
        ready_replicas=2,
        updated_replicas=3,
        reason="partial_replica_availability",
    )
