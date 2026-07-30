"""Schema validation for Mandate-26 RCA external scenarios."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from app.service_identity import normalize_service_name


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
MAX_SERVICES_PER_CASE = 32
MAX_TRACES_PER_CASE = 50
MAX_SPANS_PER_CASE = 5000
MAX_SIGNALS_PER_SERVICE = 32
MAX_POINTS_PER_SERIES = 512
ALLOWED_SERIES_SIGNALS = {"latency", "error_rate", "llm_error"}


class RCASchemaError(ValueError):
    pass


def _parse_ts(value: Any, *, field: str, case_id: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # unix seconds
        numeric = float(value)
        if not math.isfinite(numeric):
            raise RCASchemaError(
                f"case {case_id!r}: {field} unix timestamp must be finite"
            )
        try:
            return datetime.fromtimestamp(
                numeric, tz=__import__("datetime").timezone.utc
            )
        except (OverflowError, OSError, ValueError) as exc:
            raise RCASchemaError(
                f"case {case_id!r}: invalid {field} unix timestamp {value!r}"
            ) from exc
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


def _finite_number(value: Any, *, field: str, case_id: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RCASchemaError(f"case {case_id!r}: {field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise RCASchemaError(f"case {case_id!r}: {field} must be finite")
    return number


def validate_case(raw: dict[str, Any], *, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RCASchemaError(f"case #{index}: must be a JSON object")

    schema_name = raw.get("schema_name")
    if schema_name != SCHEMA_NAME:
        raise RCASchemaError(
            f"case #{index}: schema_name must be {SCHEMA_NAME!r}, got {schema_name!r}"
        )
    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise RCASchemaError(
            f"case #{index}: schema_version must be {SCHEMA_VERSION}, got {version!r}"
        )

    case_id = raw.get("id")
    if (
        not case_id
        or not isinstance(case_id, str)
        or not case_id.strip()
        or len(case_id) > 256
    ):
        raise RCASchemaError(f"case #{index}: id is required and must be a string")

    mode = raw.get("mode", "attribution_snapshot")
    if mode not in ALLOWED_MODES:
        raise RCASchemaError(f"case {case_id!r}: unsupported mode {mode!r}")

    observations = raw.get("observations")
    if observations is None:
        observations = []
    if not isinstance(observations, list):
        raise RCASchemaError(f"case {case_id!r}: observations must be a list")
    if len(observations) > MAX_SERVICES_PER_CASE:
        raise RCASchemaError(
            f"case {case_id!r}: too many observations "
            f"({len(observations)} > {MAX_SERVICES_PER_CASE})"
        )

    aliases = raw.get("service_aliases") or {}
    if not isinstance(aliases, dict):
        raise RCASchemaError(f"case {case_id!r}: service_aliases must be an object")
    for alias, target in aliases.items():
        if (
            not isinstance(alias, str)
            or not alias.strip()
            or len(alias) > 256
            or not isinstance(target, str)
            or not target.strip()
            or len(target) > 256
        ):
            raise RCASchemaError(
                f"case {case_id!r}: service_aliases keys and values must be non-empty strings"
            )

    seen_services: set[str] = set()
    aligned_series_timestamps: tuple[datetime, ...] | None = None
    for i, obs in enumerate(observations):
        if not isinstance(obs, dict):
            raise RCASchemaError(f"case {case_id!r}: observations[{i}] must be an object")
        service = obs.get("service")
        if not service or not isinstance(service, str) or len(service) > 256:
            raise RCASchemaError(f"case {case_id!r}: observations[{i}].service is required")
        service_key = normalize_service_name(
            service, aliases=aliases
        ).canonical_service
        if service_key in seen_services:
            raise RCASchemaError(f"case {case_id!r}: duplicate observation service {service!r}")
        seen_services.add(service_key)
        signals = obs.get("signals")
        if not isinstance(signals, list) or not signals:
            raise RCASchemaError(
                f"case {case_id!r}: observations[{i}].signals must be a non-empty list"
            )
        if len(signals) > MAX_SIGNALS_PER_SERVICE:
            raise RCASchemaError(
                f"case {case_id!r}: too many signals for {service!r}"
            )
        obs_observed = (
            _parse_ts(obs.get("observed_at"), field="observed_at", case_id=case_id)
            if "observed_at" in obs
            else None
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
            name_key = name.strip().lower()
            if name_key in seen_signals:
                raise RCASchemaError(
                    f"case {case_id!r}: duplicate signal {name!r} for service {service!r}"
                )
            seen_signals.add(name_key)
            if mode == "end_to_end_series":
                if name not in ALLOWED_SERIES_SIGNALS:
                    raise RCASchemaError(
                        f"case {case_id!r}: unsupported end-to-end signal {name!r}"
                    )
                series = sig.get("series")
                if not isinstance(series, list) or len(series) < 2:
                    raise RCASchemaError(
                        f"case {case_id!r}: {service}/{name}.series must contain "
                        "at least two timestamped points"
                    )
                if len(series) > MAX_POINTS_PER_SERIES:
                    raise RCASchemaError(
                        f"case {case_id!r}: {service}/{name}.series exceeds "
                        f"{MAX_POINTS_PER_SERIES} points"
                    )
                incident_start = sig.get("incident_start_index")
                if (
                    not isinstance(incident_start, int)
                    or isinstance(incident_start, bool)
                    or incident_start <= 0
                    or incident_start >= len(series)
                ):
                    raise RCASchemaError(
                        f"case {case_id!r}: {service}/{name}.incident_start_index "
                        "must identify a non-first series point"
                    )
                previous_at: datetime | None = None
                current_timestamps: list[datetime] = []
                for point_index, point in enumerate(series):
                    if not isinstance(point, dict):
                        raise RCASchemaError(
                            f"case {case_id!r}: {service}/{name}.series"
                            f"[{point_index}] must be an object"
                        )
                    point_at = _parse_ts(
                        point.get("timestamp"),
                        field=f"{service}/{name}.series[{point_index}].timestamp",
                        case_id=case_id,
                    )
                    if point_at is None:
                        raise RCASchemaError(
                            f"case {case_id!r}: series timestamp is required"
                        )
                    if previous_at is not None and point_at <= previous_at:
                        raise RCASchemaError(
                            f"case {case_id!r}: series timestamps must be strictly increasing"
                        )
                    previous_at = point_at
                    current_timestamps.append(point_at)
                    value = _finite_number(
                        point.get("value"),
                        field=f"{service}/{name}.series[{point_index}].value",
                        case_id=case_id,
                    )
                    if value < 0 or (
                        name in {"error_rate", "llm_error"} and value > 1
                    ):
                        raise RCASchemaError(
                            f"case {case_id!r}: invalid {name} value {value}"
                        )
                timestamp_tuple = tuple(current_timestamps)
                if aligned_series_timestamps is None:
                    aligned_series_timestamps = timestamp_tuple
                elif timestamp_tuple != aligned_series_timestamps:
                    raise RCASchemaError(
                        f"case {case_id!r}: end-to-end metric series must be timestamp-aligned"
                    )
            conf = _finite_number(
                sig.get("confidence", 0.0),
                field=f"confidence for {service}/{name}",
                case_id=case_id,
            )
            if conf < 0 or conf > 1:
                raise RCASchemaError(
                    f"case {case_id!r}: confidence must be in [0, 1] for {service}/{name}"
                )
            parsed_times: dict[str, datetime | None] = {}
            for ts_field in ("observed_at", "first_breached_at", "first_anomalous_at"):
                if ts_field in sig:
                    parsed_times[ts_field] = _parse_ts(
                        sig.get(ts_field), field=ts_field, case_id=case_id
                    )
            observed = parsed_times.get("observed_at") or obs_observed
            if mode == "attribution_snapshot" and observed is None:
                raise RCASchemaError(
                    f"case {case_id!r}: observed_at is required for {service}/{name}"
                )
            for onset_field in ("first_breached_at", "first_anomalous_at"):
                onset = parsed_times.get(onset_field)
                if onset is not None and observed is not None and onset > observed:
                    raise RCASchemaError(
                        f"case {case_id!r}: {onset_field} must not be after "
                        f"observed_at for {service}/{name}"
                    )
        for ts_field in ("first_breached_at", "first_anomalous_at"):
            if ts_field in obs:
                onset = _parse_ts(obs.get(ts_field), field=ts_field, case_id=case_id)
                if onset is not None and obs_observed is not None and onset > obs_observed:
                    raise RCASchemaError(
                        f"case {case_id!r}: observation {ts_field} must not be "
                        f"after observed_at for {service}"
                    )

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
            if fmt in {"jaeger-v1", "jaeger", "jaeger_v1"}:
                if len(data) > MAX_TRACES_PER_CASE:
                    raise RCASchemaError(
                        f"case {case_id!r}: trace count exceeds {MAX_TRACES_PER_CASE}"
                    )
                total_spans = 0
                for trace_index, trace in enumerate(data):
                    if not isinstance(trace, dict):
                        raise RCASchemaError(
                            f"case {case_id!r}: traces.data[{trace_index}] must be an object"
                        )
                    trace_spans = trace.get("spans") or []
                    if not isinstance(trace_spans, list):
                        raise RCASchemaError(
                            f"case {case_id!r}: trace spans must be a list"
                        )
                    total_spans += len(trace_spans)
                if total_spans > MAX_SPANS_PER_CASE:
                    raise RCASchemaError(
                        f"case {case_id!r}: span count exceeds {MAX_SPANS_PER_CASE}"
                    )
            elif len(data) > MAX_SPANS_PER_CASE:
                raise RCASchemaError(
                    f"case {case_id!r}: span count exceeds {MAX_SPANS_PER_CASE}"
                )

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
            if (
                not isinstance(caller, str)
                or not caller.strip()
                or len(caller) > 256
                or not isinstance(callee, str)
                or not callee.strip()
                or len(callee) > 256
            ):
                raise RCASchemaError(f"case {case_id!r}: topology.edges[{i}] missing endpoints")
            if caller == callee:
                raise RCASchemaError(f"case {case_id!r}: self-edge not allowed: {caller}")
            if isinstance(edge, dict) and "confidence" in edge:
                confidence = _finite_number(
                    edge["confidence"],
                    field=f"topology.edges[{i}].confidence",
                    case_id=case_id,
                )
                if confidence < 0 or confidence > 1:
                    raise RCASchemaError(
                        f"case {case_id!r}: topology confidence must be in [0, 1]"
                    )

    labels = raw.get("labels")
    if labels is not None and not isinstance(labels, dict):
        raise RCASchemaError(f"case {case_id!r}: labels must be an object when present")
    if isinstance(labels, dict):
        expected_root = labels.get("expected_root_service")
        if expected_root is not None and (
            not isinstance(expected_root, str) or not expected_root.strip()
        ):
            raise RCASchemaError(
                f"case {case_id!r}: labels.expected_root_service must be a non-empty string"
            )
        noise = labels.get("correlated_noise_services", [])
        if not isinstance(noise, list) or any(
            not isinstance(service, str) or not service.strip() for service in noise
        ):
            raise RCASchemaError(
                f"case {case_id!r}: labels.correlated_noise_services must be a list of strings"
            )
        canonical_noise = [
            normalize_service_name(service, aliases=aliases).canonical_service
            for service in noise
        ]
        if len(canonical_noise) != len(set(canonical_noise)):
            raise RCASchemaError(
                f"case {case_id!r}: duplicate correlated noise service label"
            )
        if expected_root is not None:
            canonical_root = normalize_service_name(
                expected_root, aliases=aliases
            ).canonical_service
            if canonical_root in canonical_noise:
                raise RCASchemaError(
                    f"case {case_id!r}: expected root cannot also be labeled as noise"
                )
        expected_status = labels.get("expected_attribution_status")
        if expected_status is not None and expected_status not in {
            "attributed",
            "insufficient_evidence",
            "multiple_independent_clusters",
        }:
            raise RCASchemaError(
                f"case {case_id!r}: unsupported expected attribution status "
                f"{expected_status!r}"
            )

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
