"""Jaeger v1 and normalized-span trace parsing for RCA evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Mapping

from .service_identity import normalize_service_name


SpanKind = Literal["server", "client", "internal", "producer", "consumer", "unknown"]


@dataclass(frozen=True)
class NormalizedSpan:
    trace_id: str
    span_id: str
    parent_span_ids: tuple[str, ...]
    service: str
    original_service: str
    operation: str
    kind: SpanKind
    start_us: int
    end_us: int
    error: bool
    peer_service: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class TraceParseResult:
    spans: list[NormalizedSpan] = field(default_factory=list)
    edges: list[tuple[str, str, str]] = field(default_factory=list)
    # (caller, callee, provenance)
    errors: list[str] = field(default_factory=list)
    trace_ids: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TraceOriginEvidence:
    """Per-service aggregated root-like / victim-like evidence from traces."""

    service: str
    root_like_score: float = 0.0
    victim_like_score: float = 0.0
    error_span_count: int = 0
    client_error_count: int = 0
    server_error_count: int = 0
    explained_by_callee_errors: int = 0
    deepest_failure_boundary_count: int = 0
    facts: list[str] = field(default_factory=list)
    span_ids: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    available: bool = True


def _tag_map(tags: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(tags, dict):
        for key, value in tags.items():
            result[str(key)] = str(value)
        return result
    if isinstance(tags, list):
        for item in tags:
            if not isinstance(item, Mapping):
                continue
            key = item.get("key")
            if key is None:
                continue
            if "value" in item:
                result[str(key)] = str(item["value"])
            elif "vStr" in item:
                result[str(key)] = str(item["vStr"])
            elif "vBool" in item:
                result[str(key)] = str(item["vBool"]).lower()
            elif "vLong" in item:
                result[str(key)] = str(item["vLong"])
            elif "vDouble" in item:
                result[str(key)] = str(item["vDouble"])
    return result


def _is_error(tags: Mapping[str, str], status_code: Any = None) -> bool:
    for key in ("error", "otel.status_code", "http.status_code", "rpc.grpc.status_code"):
        value = tags.get(key)
        if value is None:
            continue
        lower = value.lower()
        if key == "error" and lower in {"true", "1", "yes"}:
            return True
        if key == "otel.status_code" and lower in {"error", "status_code_error", "2"}:
            return True
        if key == "http.status_code":
            try:
                if int(float(value)) >= 500:
                    return True
            except ValueError:
                pass
        if key == "rpc.grpc.status_code":
            # Non-zero gRPC codes other than OK
            if lower not in {"0", "ok"}:
                return True
    if status_code is not None:
        try:
            if int(status_code) >= 500:
                return True
        except (TypeError, ValueError):
            if str(status_code).lower() in {"error", "status_code_error"}:
                return True
    return False


def _span_kind(tags: Mapping[str, str], explicit: Any = None) -> SpanKind:
    raw = str(explicit or tags.get("span.kind") or tags.get("otlp.span.kind") or "").lower()
    mapping = {
        "server": "server",
        "client": "client",
        "internal": "internal",
        "producer": "producer",
        "consumer": "consumer",
        "span_kind_server": "server",
        "span_kind_client": "client",
        "span_kind_internal": "internal",
        "span_kind_producer": "producer",
        "span_kind_consumer": "consumer",
        "2": "server",
        "3": "client",
        "1": "internal",
        "4": "producer",
        "5": "consumer",
    }
    return mapping.get(raw, "unknown")  # type: ignore[return-value]


def _peer_service(tags: Mapping[str, str]) -> str | None:
    for key in (
        "peer.service",
        "net.peer.name",
        "server.address",
        "rpc.service",
        "db.system",
        "messaging.destination",
    ):
        value = tags.get(key)
        if value:
            return value
    return None


def parse_normalized_spans(
    spans: Iterable[Mapping[str, Any]],
    *,
    aliases: Mapping[str, str] | None = None,
) -> TraceParseResult:
    result = TraceParseResult()
    by_id: dict[tuple[str, str], NormalizedSpan] = {}
    for raw in spans:
        if not isinstance(raw, Mapping):
            result.errors.append("non-object span skipped")
            continue
        trace_id = str(raw.get("trace_id") or raw.get("traceID") or raw.get("traceId") or "")
        span_id = str(raw.get("span_id") or raw.get("spanID") or raw.get("spanId") or "")
        if not trace_id or not span_id:
            result.errors.append("span missing trace_id/span_id")
            continue
        service_raw = str(
            raw.get("service")
            or raw.get("service_name")
            or raw.get("serviceName")
            or ""
        )
        identity = normalize_service_name(service_raw, aliases=aliases)
        parents_raw = raw.get("parent_span_ids") or raw.get("parentSpanIds") or []
        if raw.get("parent_span_id") or raw.get("parentSpanId"):
            parents_raw = list(parents_raw) + [
                raw.get("parent_span_id") or raw.get("parentSpanId")
            ]
        parents = tuple(str(p) for p in parents_raw if p)
        start = int(raw.get("start_us") or raw.get("startTime") or raw.get("start_time_us") or 0)
        duration = int(raw.get("duration_us") or raw.get("duration") or 0)
        end = int(raw.get("end_us") or (start + duration if duration else start))
        tags = {str(k): str(v) for k, v in (raw.get("tags") or {}).items()} if isinstance(
            raw.get("tags"), dict
        ) else _tag_map(raw.get("tags"))
        error = bool(raw.get("error")) or _is_error(tags, raw.get("status_code"))
        kind = _span_kind(tags, raw.get("kind") or raw.get("span_kind"))
        peer_raw = raw.get("peer_service") or _peer_service(tags)
        peer = (
            normalize_service_name(str(peer_raw), aliases=aliases).canonical_service
            if peer_raw
            else None
        )
        span = NormalizedSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_ids=parents,
            service=identity.canonical_service,
            original_service=identity.original_service,
            operation=str(raw.get("operation") or raw.get("operationName") or ""),
            kind=kind,
            start_us=start,
            end_us=end,
            error=error,
            peer_service=peer,
            tags=tags,
        )
        key = (trace_id, span_id)
        if key in by_id:
            result.warnings.append(f"duplicate span {trace_id}/{span_id}")
            continue
        by_id[key] = span
        result.spans.append(span)
        result.trace_ids.add(trace_id)

    _derive_edges(result, by_id, aliases)
    return result


def parse_jaeger_traces(
    traces: Iterable[Mapping[str, Any]],
    *,
    aliases: Mapping[str, str] | None = None,
    max_traces: int = 50,
    max_spans: int = 5000,
) -> TraceParseResult:
    result = TraceParseResult()
    seen_trace_ids: set[str] = set()
    span_count = 0
    for idx, trace in enumerate(traces):
        if idx >= max_traces or span_count >= max_spans:
            result.warnings.append("trace/span cap reached")
            break
        if not isinstance(trace, Mapping):
            result.errors.append("non-object trace skipped")
            continue
        trace_id = str(trace.get("traceID") or trace.get("traceId") or "")
        if not trace_id:
            result.errors.append("trace missing traceID")
            continue
        if trace_id in seen_trace_ids:
            result.warnings.append(f"duplicate trace {trace_id}")
            # Still merge spans if new; Jaeger multi-service queries may re-return.
        seen_trace_ids.add(trace_id)
        processes = trace.get("processes") or {}
        process_service: dict[str, str] = {}
        if isinstance(processes, Mapping):
            for pid, proc in processes.items():
                if not isinstance(proc, Mapping):
                    continue
                name = proc.get("serviceName") or proc.get("service_name") or ""
                process_service[str(pid)] = str(name)

        spans = trace.get("spans") or []
        by_id: dict[tuple[str, str], NormalizedSpan] = {}
        for raw in spans:
            if span_count >= max_spans:
                result.warnings.append("span cap reached mid-trace")
                break
            if not isinstance(raw, Mapping):
                continue
            span_id = str(raw.get("spanID") or raw.get("spanId") or "")
            if not span_id:
                continue
            process_id = str(raw.get("processID") or raw.get("processId") or "")
            service_raw = process_service.get(process_id, "")
            if not service_raw:
                # Some exporters put service on tags
                tags_preview = _tag_map(raw.get("tags"))
                service_raw = tags_preview.get("service.name") or tags_preview.get(
                    "resource.service.name", ""
                )
            identity = normalize_service_name(service_raw, aliases=aliases)
            refs = raw.get("references") or []
            parents: list[str] = []
            if isinstance(refs, list):
                for ref in refs:
                    if not isinstance(ref, Mapping):
                        continue
                    ref_type = str(ref.get("refType") or ref.get("ref_type") or "").upper()
                    if ref_type in {"", "CHILD_OF", "FOLLOWS_FROM"}:
                        parent_id = ref.get("spanID") or ref.get("spanId")
                        if parent_id:
                            parents.append(str(parent_id))
            tags = _tag_map(raw.get("tags"))
            start = int(raw.get("startTime") or 0)
            duration = int(raw.get("duration") or 0)
            error = _is_error(tags)
            # Jaeger logs may also mark errors
            for log_entry in raw.get("logs") or []:
                if not isinstance(log_entry, Mapping):
                    continue
                log_tags = _tag_map(log_entry.get("fields") or log_entry.get("tags"))
                if _is_error(log_tags) or log_tags.get("event", "").lower() == "error":
                    error = True
            kind = _span_kind(tags)
            peer_raw = _peer_service(tags)
            peer = (
                normalize_service_name(str(peer_raw), aliases=aliases).canonical_service
                if peer_raw
                else None
            )
            span = NormalizedSpan(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_ids=tuple(parents),
                service=identity.canonical_service,
                original_service=identity.original_service,
                operation=str(raw.get("operationName") or raw.get("operation") or ""),
                kind=kind,
                start_us=start,
                end_us=start + duration,
                error=error,
                peer_service=peer,
                tags=tags,
            )
            key = (trace_id, span_id)
            if key in by_id:
                result.warnings.append(f"duplicate span {trace_id}/{span_id}")
                continue
            by_id[key] = span
            result.spans.append(span)
            result.trace_ids.add(trace_id)
            span_count += 1
        _derive_edges(result, by_id, aliases)
    return result


def _derive_edges(
    result: TraceParseResult,
    by_id: Mapping[tuple[str, str], NormalizedSpan],
    aliases: Mapping[str, str] | None,
) -> None:
    # Parent/child service edges
    id_index = {(s.trace_id, s.span_id): s for s in result.spans}
    id_index.update(by_id)
    for span in by_id.values():
        for parent_id in span.parent_span_ids:
            parent = id_index.get((span.trace_id, parent_id))
            if parent is None:
                result.warnings.append(
                    f"orphan parent reference {span.trace_id}/{parent_id}"
                )
                continue
            if parent.service and span.service and parent.service != span.service:
                # parent is typically the caller for child server spans
                result.edges.append(
                    (parent.service, span.service, f"trace-parent:{span.trace_id}")
                )
        if span.kind == "client" and span.peer_service and span.service:
            peer = normalize_service_name(span.peer_service, aliases=aliases).canonical_service
            if peer and peer != span.service:
                result.edges.append(
                    (span.service, peer, f"trace-client-peer:{span.trace_id}")
                )
        if span.kind == "producer" and span.peer_service and span.service:
            peer = normalize_service_name(span.peer_service, aliases=aliases).canonical_service
            if peer and peer != span.service:
                result.edges.append(
                    (span.service, peer, f"trace-producer:{span.trace_id}")
                )


def analyze_trace_origins(
    parse: TraceParseResult,
    *,
    clock_skew_tolerance_us: int = 45_000_000,
) -> dict[str, TraceOriginEvidence]:
    """Derive root-like vs victim-like scores per service."""

    if not parse.spans:
        return {}

    by_trace: dict[str, list[NormalizedSpan]] = {}
    for span in parse.spans:
        by_trace.setdefault(span.trace_id, []).append(span)

    evidence: dict[str, TraceOriginEvidence] = {}

    def bucket(service: str) -> TraceOriginEvidence:
        if service not in evidence:
            evidence[service] = TraceOriginEvidence(service=service)
        return evidence[service]

    for trace_id, spans in by_trace.items():
        by_id = {s.span_id: s for s in spans}
        error_spans = [s for s in spans if s.error]
        for span in spans:
            ev = bucket(span.service)
            if span.error:
                ev.error_span_count += 1
                if span.span_id not in ev.span_ids:
                    ev.span_ids.append(span.span_id)
                if trace_id not in ev.trace_ids:
                    ev.trace_ids.append(trace_id)
                if span.kind == "server":
                    ev.server_error_count += 1
                elif span.kind == "client":
                    ev.client_error_count += 1

        for span in error_spans:
            ev = bucket(span.service)
            # Victim-like: only client errors while a callee also errored earlier/same.
            if span.kind == "client":
                peer = span.peer_service
                callee_error = False
                if peer:
                    for other in error_spans:
                        if other.service == peer and other.kind in {"server", "unknown", "consumer"}:
                            # callee server error starts no later than client (within skew)
                            if other.start_us <= span.start_us + clock_skew_tolerance_us:
                                callee_error = True
                                break
                # Also check children server spans
                for child in spans:
                    if span.span_id in child.parent_span_ids and child.error:
                        if child.start_us <= span.end_us + clock_skew_tolerance_us:
                            callee_error = True
                            peer = peer or child.service
                            break
                if callee_error:
                    ev.victim_like_score += 1.0
                    ev.explained_by_callee_errors += 1
                    ev.facts.append(
                        f"client error on {span.service} explained by callee "
                        f"{peer} in trace {trace_id}"
                    )
                else:
                    # Client timeout without server span: still candidate but weaker root-like
                    ev.root_like_score += 0.4
                    ev.facts.append(
                        f"client error on {span.service} without matching callee "
                        f"server error in trace {trace_id}"
                    )
            elif span.kind in {"server", "unknown", "consumer", "internal"}:
                # Root-like if no earlier failed callee explains this server error
                explained = False
                for child in spans:
                    if span.span_id in child.parent_span_ids and child.error:
                        if child.service != span.service:
                            explained = True
                            break
                    # peer callees from client children
                if not explained:
                    # also check if this service only has client children errors to others
                    for other in error_spans:
                        if (
                            other.service != span.service
                            and other.kind in {"server", "unknown"}
                            and other.start_us + clock_skew_tolerance_us < span.start_us
                            and any(
                                other.span_id in c.parent_span_ids
                                for c in spans
                                if c.service == span.service
                            )
                        ):
                            explained = True
                            break
                if explained:
                    ev.victim_like_score += 0.5
                    ev.facts.append(
                        f"server error on {span.service} has deeper failed callee "
                        f"in trace {trace_id}"
                    )
                else:
                    ev.root_like_score += 1.0
                    ev.deepest_failure_boundary_count += 1
                    ev.facts.append(
                        f"error boundary at {span.service} with no earlier failed "
                        f"callee in trace {trace_id}"
                    )

        # Deepest failure boundary: error service with no error callees in this trace
        error_services = {s.service for s in error_spans}
        for service in error_services:
            has_error_callee = False
            for span in error_spans:
                if span.service != service:
                    continue
                if span.kind == "client" and span.peer_service in error_services:
                    has_error_callee = True
                    break
                for child in spans:
                    if (
                        span.span_id in child.parent_span_ids
                        and child.error
                        and child.service != service
                        and child.service in error_services
                    ):
                        has_error_callee = True
                        break
            if not has_error_callee:
                bucket(service).deepest_failure_boundary_count += 1
                bucket(service).root_like_score += 0.5

    # Normalize scores into [0, 1]
    for ev in evidence.values():
        raw = ev.root_like_score - 0.75 * ev.victim_like_score
        # soft normalize
        ev.root_like_score = max(0.0, min(1.0, raw / 3.0))
        # keep victim as separate [0,1]
        ev.victim_like_score = max(0.0, min(1.0, ev.victim_like_score / 3.0))
    return evidence


def us_to_datetime(us: int) -> datetime | None:
    if us <= 0:
        return None
    return datetime.fromtimestamp(us / 1_000_000.0, tz=timezone.utc)
