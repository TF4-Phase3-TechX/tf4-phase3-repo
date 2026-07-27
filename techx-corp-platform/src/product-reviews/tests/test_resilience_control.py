from concurrent import futures
import json

import grpc
import pytest

from resilience_control import FaultController, ResilienceControlHandler


class AbortCalled(RuntimeError):
    def __init__(self, code, details):
        super().__init__(details)
        self.code = code


class Context:
    def __init__(self, token=""):
        self._token = token

    def invocation_metadata(self):
        return (("x-mandate25-token", self._token),)

    def abort(self, code, details):
        raise AbortCalled(code, details)


def test_fault_auto_restores_after_bounded_ttl():
    now = [100.0]
    controller = FaultController(clock=lambda: now[0], max_ttl_seconds=10)

    assert controller.set("timeout", 5).mode == "timeout"
    now[0] = 104.0
    assert controller.snapshot().seconds_remaining == 1.0
    now[0] = 105.0
    assert controller.snapshot().mode == "off"


@pytest.mark.parametrize("ttl", [0, 11])
def test_fault_rejects_unbounded_ttl(ttl):
    controller = FaultController(max_ttl_seconds=10)

    with pytest.raises(ValueError, match="ttl_seconds"):
        controller.set("throttling", ttl)


def test_fault_control_fails_closed_without_dedicated_token(monkeypatch):
    monkeypatch.delenv("MANDATE25_FAULT_TOKEN", raising=False)
    handler = ResilienceControlHandler(
        FaultController(),
        status_source=lambda: {"circuit_state": "closed"},
    )

    with pytest.raises(AbortCalled) as exc_info:
        handler._set_fault(
            {"mode": "timeout", "ttl_seconds": 10},
            Context("guessed"),
        )

    assert exc_info.value.code == grpc.StatusCode.PERMISSION_DENIED


def test_fault_control_sets_and_reads_back_only_bounded_state(monkeypatch):
    monkeypatch.setenv("MANDATE25_FAULT_TOKEN", "test-control-token")
    controller = FaultController()
    handler = ResilienceControlHandler(
        controller,
        status_source=lambda: {
            "circuit_state": "closed",
            "last_provider_outcome": "success",
        },
    )

    response = handler._set_fault(
        {"mode": "provider_5xx", "ttl_seconds": 10},
        Context("test-control-token"),
    )
    status = handler._get_status({}, Context())

    assert response["mode"] == "provider_5xx"
    assert status["fault"]["mode"] == "provider_5xx"
    assert status["resilience"] == {
        "circuit_state": "closed",
        "last_provider_outcome": "success",
    }


def test_external_grpc_control_has_effective_readback_and_restore(monkeypatch):
    monkeypatch.setenv("MANDATE25_FAULT_TOKEN", "test-control-token")
    controller = FaultController()
    handler = ResilienceControlHandler(
        controller,
        status_source=lambda: {
            "circuit_state": "closed",
            "last_provider_outcome": "never_attempted",
            "last_provider_error": "none",
        },
    )
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    server.add_generic_rpc_handlers((handler,))
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    serialize = lambda value: json.dumps(value).encode("utf-8")
    deserialize = lambda value: json.loads(value.decode("utf-8"))
    set_fault = channel.unary_unary(
        "/tf4.mandate25.ResilienceControl/SetFault",
        request_serializer=serialize,
        response_deserializer=deserialize,
    )
    get_status = channel.unary_unary(
        "/tf4.mandate25.ResilienceControl/GetStatus",
        request_serializer=serialize,
        response_deserializer=deserialize,
    )
    metadata = (("x-mandate25-token", "test-control-token"),)

    try:
        enabled = set_fault(
            {"mode": "timeout", "ttl_seconds": 10},
            metadata=metadata,
        )
        observed = get_status({})
        restored = set_fault(
            {"mode": "off", "ttl_seconds": 0},
            metadata=metadata,
        )
        observed_after_restore = get_status({})
    finally:
        channel.close()
        server.stop(0).wait()

    assert enabled["mode"] == observed["fault"]["mode"] == "timeout"
    assert restored["mode"] == observed_after_restore["fault"]["mode"] == "off"
