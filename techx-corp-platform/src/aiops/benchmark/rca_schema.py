"""Schema validation for Mandate-26 RCA external scenarios."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


SCHEMA_NAME = "techx.aiops.rca"
SCHEMA_VERSION = 1
ALLOWED_MODES = {"attribution_snapshot", "end_to_end_series"}
ALLOWED_TRACE_FORMATS = {
    "jaeger-v1",
    "jaeger",
    "jaeger_v1",
    "normalized",
    "normalized-spans",
    "spans",
}


class RCASchemaError(ValueError):
    pass


def _parse_ts(value: Any, *, field: str, case_id: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # unix seconds
        return datetime.fromtimestamp(float(value), tz=__import__("datetime").timezone.utc)
    if not isinstance(value, str):
        raise RCASchemaError(f"case {case_id!r}: {field} must be ISO-8601 string or unix seconds")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RCASchemaError(f"case {case_id!r}: invalid {field}: {value!r}") from exc
    if dt.tzinfo is None:
        from datetime import timezone

        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def validate_case(raw: dict[str, Any], *, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RCASchemaError(f"case #{index}: must be a JSON object")

    schema_name = raw.get("schema_name", SCHEMA_NAME)
    if schema_name != SCHEMA_NAME:
        raise RCASchemaError(
            f"case #{index}: schema_name must be {SCHEMA_NAME!r}, got {schema_name!r}"
        )
    version = raw.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise RCASchemaError(
            f"case #{index}: schema_version must be {SCHEMA_VERSION}, got {version!r}"
        )

    case_id = raw.get("id")
    if not case_id or not isinstance(case_id, str):
        raise RCASchemaError(f"case #{index}: id is required and must be a string")

    mode = raw.get("mode", "attribution_snapshot")
    if mode not in ALLOWED_MODES:
        raise RCASchemaError(f"case {case_id!r}: unsupported mode {mode!r}")

    observations = raw.get("observations")
    if observations is None:
        observations = []
    if not isinstance(observations, list):
        raise RCASchemaError(f"case {case_id!r}: observations must be a list")

    seen_services: set[str] = set()
    for i, obs in enumerate(observations):
        if not isinstance(obs, dict):
            raise RCASchemaError(f"case {case_id!r}: observations[{i}] must be an object")
        service = obs.get("service")
        if not service or not isinstance(service, str):
            raise RCASchemaError(f"case {case_id!r}: observations[{i}].service is required")
        if service in seen_services:
            raise RCASchemaError(f"case {case_id!r}: duplicate observation service {service!r}")
        seen_services.add(service)
        signals = obs.get("signals")
        if not isinstance(signals, list) or not signals:
            raise RCASchemaError(
                f"case {case_id!r}: observations[{i}].signals must be a non-empty list"
            )
        seen_signals: set[str] = set()
        for j, sig in enumerate(signals):
            if not isinstance(sig, dict):
                raise RCASchemaError(
                    f"case {case_id!r}: observations[{i}].signals[{j}] must be an object"
                )
            name = sig.get("signal")
            if not name or not isinstance(name, str):
                raise RCASchemaError(
                    f"case {case_id!r}: observations[{i}].signals[{j}].signal is required"
                )
            if name in seen_signals:
                raise RCASchemaError(
                    f"case {case_id!r}: duplicate signal {name!r} for service {service!r}"
                )
            seen_signals.add(name)
            conf = sig.get("confidence", 0.0)
            if not isinstance(conf, (int, float)) or isinstance(conf, bool):
                raise RCASchemaError(
                    f"case {case_id!r}: confidence must be numeric for {service}/{name}"
                )
            if math.isnan(float(conf)) or math.isinf(float(conf)):
                raise RCASchemaError(
                    f"case {case_id!r}: confidence must be finite for {service}/{name}"
                )
            for ts_field in ("observed_at", "first_breached_at", "first_anomalous_at"):
                if ts_field in sig:
                    _parse_ts(sig.get(ts_field), field=ts_field, case_id=case_id)
        for ts_field in ("first_breached_at", "first_anomalous_at"):
            if ts_field in obs:
                _parse_ts(obs.get(ts_field), field=ts_field, case_id=case_id)

    traces = raw.get("traces")
    if traces is not None:
        if not isinstance(traces, dict):
            raise RCASchemaError(f"case {case_id!r}: traces must be an object")
        if traces.get("unavailable") is not True and traces.get("status") != "unavailable":
            fmt = str(traces.get("format") or "jaeger-v1").lower()
            if fmt not in ALLOWED_TRACE_FORMATS:
                raise RCASchemaError(f"case {case_id!r}: unsupported trace format {fmt!r}")
            data = traces.get("data")
            if data is None:
                data = []
            if not isinstance(data, list):
                raise RCASchemaError(f"case {case_id!r}: traces.data must be a list")

    topology = raw.get("topology")
    if topology is not None:
        if not isinstance(topology, dict):
            raise RCASchemaError(f"case {case_id!r}: topology must be an object")
        direction = topology.get("edge_direction", "caller_to_callee")
        if direction not in {"caller_to_callee", "caller->callee"}:
            raise RCASchemaError(
                f"case {case_id!r}: topology.edge_direction must be caller_to_callee"
            )
        edges = topology.get("edges") or []
        if not isinstance(edges, list):
            raise RCASchemaError(f"case {case_id!r}: topology.edges must be a list")
        for i, edge in enumerate(edges):
            if isinstance(edge, (list, tuple)) and len(edge) == 2:
                caller, callee = edge
            elif isinstance(edge, dict):
                caller = edge.get("caller") or edge.get("from")
                callee = edge.get("callee") or edge.get("to")
            else:
                raise RCASchemaError(f"case {case_id!r}: topology.edges[{i}] invalid")
            if not caller or not callee:
                raise RCASchemaError(f"case {case_id!r}: topology.edges[{i}] missing endpoints")
            if caller == callee:
                raise RCASchemaError(f"case {case_id!r}: self-edge not allowed: {caller}")

    aliases = raw.get("service_aliases") or {}
    if not isinstance(aliases, dict):
        raise RCASchemaError(f"case {case_id!r}: service_aliases must be an object")

    labels = raw.get("labels")
    if labels is not None and not isinstance(labels, dict):
        raise RCASchemaError(f"case {case_id!r}: labels must be an object when present")

    if mode == "attribution_snapshot" and not observations and not (
        isinstance(traces, dict) and (traces.get("data") or traces.get("unavailable"))
    ):
        raise RCASchemaError(
            f"case {case_id!r}: attribution_snapshot requires observations and/or traces"
        )

    return raw


def split_engine_and_labels(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Strict label isolation: engine_input never contains labels."""

    labels = case.get("labels")
    engine_input = {
        "id": case.get("id"),
        "description": case.get("description"),
        "mode": case.get("mode", "attribution_snapshot"),
        "observations": case.get("observations") or [],
        "traces": case.get("traces"),
        "topology": case.get("topology"),
        "service_aliases": case.get("service_aliases") or {},
        "unavailable_signals": case.get("unavailable_signals") or [],
    }
    eval_labels = dict(labels) if isinstance(labels, dict) else None
    return engine_input, eval_labels
