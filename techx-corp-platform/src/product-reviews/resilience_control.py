"""Bounded, application-owned Mandate 25 fault and status control."""

from __future__ import annotations

import hmac
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import grpc


CONTROL_SERVICE = "tf4.mandate25.ResilienceControl"
ALLOWED_FAULTS = frozenset(
    {"off", "timeout", "throttling", "provider_5xx", "malformed_output"}
)


@dataclass(frozen=True)
class FaultSnapshot:
    mode: str
    seconds_remaining: float


class FaultController:
    """Keep a process-local fault with a mandatory bounded expiry."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_ttl_seconds: int = 120,
    ):
        self._clock = clock
        self._max_ttl_seconds = max_ttl_seconds
        self._mode = "off"
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def set(self, mode: str, ttl_seconds: int) -> FaultSnapshot:
        if mode not in ALLOWED_FAULTS:
            raise ValueError("unsupported fault mode")
        if mode == "off":
            ttl_seconds = 0
        elif not 1 <= ttl_seconds <= self._max_ttl_seconds:
            raise ValueError(
                f"ttl_seconds must be between 1 and {self._max_ttl_seconds}"
            )
        with self._lock:
            self._mode = mode
            self._expires_at = (
                self._clock() + ttl_seconds if mode != "off" else 0.0
            )
            return self._snapshot_locked()

    def snapshot(self) -> FaultSnapshot:
        with self._lock:
            return self._snapshot_locked()

    def current_mode(self) -> str:
        return self.snapshot().mode

    def _snapshot_locked(self) -> FaultSnapshot:
        now = self._clock()
        if self._mode != "off" and now >= self._expires_at:
            self._mode = "off"
            self._expires_at = 0.0
        remaining = max(0.0, self._expires_at - now)
        return FaultSnapshot(self._mode, round(remaining, 3))


def _decode_json(payload: bytes) -> dict[str, Any]:
    value = json.loads(payload.decode("utf-8") or "{}")
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    return value


def _encode_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


class ResilienceControlHandler(grpc.GenericRpcHandler):
    """Expose a token-protected setter and content-free status readback."""

    def __init__(
        self,
        controller: FaultController,
        status_source: Callable[[], dict[str, Any]],
    ):
        self._controller = controller
        self._status_source = status_source

    def service(self, handler_call_details):
        prefix = f"/{CONTROL_SERVICE}/"
        if not handler_call_details.method.startswith(prefix):
            return None
        method_name = handler_call_details.method[len(prefix) :]
        if method_name == "SetFault":
            return grpc.unary_unary_rpc_method_handler(
                self._set_fault,
                request_deserializer=_decode_json,
                response_serializer=_encode_json,
            )
        if method_name == "GetStatus":
            return grpc.unary_unary_rpc_method_handler(
                self._get_status,
                request_deserializer=_decode_json,
                response_serializer=_encode_json,
            )
        return None

    def _set_fault(self, request: dict[str, Any], context):
        expected = os.environ.get("MANDATE25_FAULT_TOKEN", "")
        supplied = dict(context.invocation_metadata()).get(
            "x-mandate25-token", ""
        )
        if not expected or not hmac.compare_digest(expected, supplied):
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "fault control disabled")
        try:
            mode = str(request.get("mode", ""))
            ttl_seconds = int(request.get("ttl_seconds", 0))
            snapshot = self._controller.set(mode, ttl_seconds)
        except (TypeError, ValueError) as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        return {
            "mode": snapshot.mode,
            "seconds_remaining": snapshot.seconds_remaining,
        }

    def _get_status(self, _request: dict[str, Any], _context):
        snapshot = self._controller.snapshot()
        return {
            "fault": {
                "mode": snapshot.mode,
                "seconds_remaining": snapshot.seconds_remaining,
            },
            "resilience": self._status_source(),
        }
