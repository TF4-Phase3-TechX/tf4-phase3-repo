"""Deterministic cross-service root-cause attribution engine (Mandate 26)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from .dependency_graph import DependencyGraph, TECHX_CALL_GRAPH
from .rca_models import (
    RCACandidate,
    RCAEvidenceFact,
    RCAObservation,
    RCAResult,
    RCASignalContribution,
    SignalObservation,
)
from .service_identity import normalize_service_name
from .trace_graph import (
    TraceParseResult,
    analyze_trace_origins,
    parse_jaeger_traces,
    parse_normalized_spans,
)


MODEL_VERSION_DEFAULT = "m26-v1"


@dataclass(frozen=True)
class RCAEngineConfig:
    model_version: str = MODEL_VERSION_DEFAULT
    trace_weight: float = 0.35
    topology_weight: float = 0.30
    temporal_weight: float = 0.20
    anomaly_weight: float = 0.15
    contradiction_penalty: float = 0.20
    parallel_anomaly_penalty: float = 0.25
    temporal_tolerance_seconds: float = 45.0
    max_services: int = 32
    max_traces: int = 50
    max_spans: int = 5000
    min_score_margin_for_attribution: float = 0.02

    def validate(self) -> None:
        weights = (
            self.trace_weight,
            self.topology_weight,
            self.temporal_weight,
            self.anomaly_weight,
        )
        if any(not math.isfinite(w) or w < 0 for w in weights):
            raise ValueError("RCA feature weights must be finite and nonnegative")
        if sum(weights) <= 0:
            raise ValueError("RCA total feature weight must be positive")
        for name, value in (
            ("contradiction_penalty", self.contradiction_penalty),
            ("parallel_anomaly_penalty", self.parallel_anomaly_penalty),
        ):
            if not math.isfinite(value) or value < 0 or value > 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if (
            not math.isfinite(self.temporal_tolerance_seconds)
            or self.temporal_tolerance_seconds < 0
        ):
            raise ValueError("temporal tolerance must be finite and nonnegative")
        if (
            not math.isfinite(self.min_score_margin_for_attribution)
            or not 0 <= self.min_score_margin_for_attribution <= 1
        ):
            raise ValueError("minimum attribution margin must be in [0, 1]")
        limits = (self.max_services, self.max_traces, self.max_spans)
        if any(
            not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0
            for limit in limits
        ):
            raise ValueError("RCA resource limits must be positive")


@dataclass
class RCAEngineInput:
    observations: list[RCAObservation]
    traces: TraceParseResult | None = None
    graph: DependencyGraph | None = None
    analysis_at: datetime | None = None
    # Explicit signal unavailability (e.g. jaeger down)
    unavailable_signals: list[str] | None = None
    topology_provenance: list[str] | None = None


class RCAEngine:
    def __init__(self, config: RCAEngineConfig | None = None):
        self.config = config or RCAEngineConfig()
        self.config.validate()

    def analyze(self, engine_input: RCAEngineInput) -> RCAResult:
        """Score candidates. Must never receive evaluation labels."""

        started = datetime.now(timezone.utc)
        cfg = self.config
        observations = list(engine_input.observations or [])
        # Cap services deterministically while retaining current anomalies before
        # recovered/non-anomalous episode context.
        observations = sorted(
            observations,
            key=lambda o: (
                0 if o.is_anomalous else 1,
                0 if o.first_anomalous_at is not None else 1,
                o.service,
            ),
        )[: cfg.max_services]
        by_service = {o.service: o for o in observations}

        graph = engine_input.graph or DependencyGraph.from_static(TECHX_CALL_GRAPH)
        provenance = list(engine_input.topology_provenance or graph.provenance_log)
        unavailable = list(engine_input.unavailable_signals or [])

        parse = engine_input.traces
        if parse is None:
            parse = TraceParseResult()
            if "trace" not in unavailable:
                # empty traces means no data, not necessarily unavailable
                pass

        # Incorporate dynamic edges from traces without mutating caller's graph permanently
        working_graph = graph.copy()
        for caller, callee, prov in parse.edges:
            working_graph.add_edge(caller, callee, provenance=prov, confidence=0.8)
            if prov not in provenance:
                provenance.append(prov)

        # Candidate universe
        anomalous_services = {o.service for o in observations if o.is_anomalous}
        # Episode observations may represent a service that recovered before its
        # callers became anomalous. Its recorded anomaly onset keeps it eligible.
        episode_services = {
            o.service
            for o in observations
            if o.is_anomalous or o.first_anomalous_at is not None
        }
        trace_services = {s.service for s in parse.spans if s.error}
        affected = set(anomalous_services)
        # Expand with graph dependencies that could explain the affected cluster
        candidate_set: set[str] = (
            set(anomalous_services) | set(episode_services) | set(trace_services)
        )
        for service in list(affected):
            candidate_set |= set(working_graph.reachable_callees(service))
            candidate_set |= set(working_graph.callers(service))
            # direct callees of affected
            candidate_set |= set(working_graph.callees(service))

        # Always include services that appear on failed trace paths even if not anomalous
        candidate_set |= {s.service for s in parse.spans}
        candidate_set = {s for s in candidate_set if s and s != "unknown"}
        if len(candidate_set) > cfg.max_services:
            # Prefer anomalous + trace error services
            priority = sorted(anomalous_services | episode_services | trace_services)
            rest = sorted(candidate_set - set(priority))
            candidate_set = set((priority + rest)[: cfg.max_services])

        if not candidate_set and not anomalous_services:
            ended = datetime.now(timezone.utc)
            return RCAResult(
                model_version=cfg.model_version,
                attribution_status="insufficient_evidence",
                suspected_root_service=None,
                confidence=0.0,
                score_margin=None,
                explanation="No anomalous observations or trace error spans were available.",
                candidates=[],
                unavailable_signals=unavailable,
                topology_provenance=provenance,
                analysis_started_at=started,
                analysis_ended_at=ended,
                processing_ms=(ended - started).total_seconds() * 1000.0,
                trace_count=len(parse.trace_ids),
                span_count=len(parse.spans),
            )

        # Components among anomalous services plus trace-supported boundaries.
        # Including trace services connects sibling victims through a trace-only
        # root while keeping unrelated observed anomalies separate.
        if len(anomalous_services) >= 2:
            component_nodes = anomalous_services | trace_services
            raw_components = working_graph.connected_components(component_nodes)
            undirected_components = [
                frozenset(set(component) & anomalous_services)
                for component in raw_components
                if set(component) & anomalous_services
            ]
            multi_cluster = len(undirected_components) >= 2
        else:
            undirected_components = [
                frozenset(anomalous_services)
            ] if anomalous_services else []
            multi_cluster = False

        trace_available = "trace" not in unavailable and bool(parse.spans)
        origins = (
            analyze_trace_origins(
                parse,
                clock_skew_tolerance_us=int(
                    cfg.temporal_tolerance_seconds * 1_000_000
                ),
            )
            if parse.spans
            else {}
        )
        if "trace" in unavailable:
            origins = {}
            trace_available = False

        # Primary affected set for coverage: anomalous services
        affected_list = sorted(anomalous_services) if anomalous_services else sorted(candidate_set)

        candidates: list[RCACandidate] = []
        for service in sorted(candidate_set):
            candidates.append(
                self._score_candidate(
                    service=service,
                    by_service=by_service,
                    affected=affected_list,
                    graph=working_graph,
                    origins=origins,
                    trace_available=trace_available,
                    traces_explicitly_unavailable="trace" in unavailable,
                    anomalous_services=anomalous_services,
                )
            )

        # Deterministic sort
        candidates.sort(key=lambda c: (-c.score, c.service))
        for rank, cand in enumerate(candidates, start=1):
            cand.rank = rank

        score_margin = None
        if len(candidates) >= 2:
            score_margin = round(candidates[0].score - candidates[1].score, 6)
        elif len(candidates) == 1:
            score_margin = round(candidates[0].score, 6)

        # Classification pass
        if candidates:
            top = candidates[0]
            cascade = set(top.explained_affected_services) | {top.service}
            # Primary undirected component among cascade members (for multi-root cases)
            primary_component: set[str] = set(cascade)
            if anomalous_services:
                comps = working_graph.connected_components(anomalous_services)
                for comp in comps:
                    if top.service in comp:
                        primary_component = set(comp) | cascade
                        break

            for cand in candidates:
                if cand.rank == 1:
                    cand.classification = "suspected_root"
                    continue

                in_cascade = cand.service in cascade
                # Parallel noise: anomalous, not part of the top root's explained cascade,
                # and does not itself explain the cascade root via a call path that would
                # make it a superior upstream cause of the same victims.
                if (
                    trace_available
                    and cand.service in anomalous_services
                    and not in_cascade
                ):
                    explains_cascade_core = bool(
                        set(cand.explained_affected_services) & (cascade - {cand.service})
                    )
                    # Sibling / disconnected noise: may share a common caller but is not
                    # on the failure path selected by the top candidate.
                    # cand is upstream of root if root calls into cand... failure at cand
                    # hurts root when root->cand. For payment root, ad is NOT upstream.
                    is_upstream_cause = working_graph.has_call_path(
                        top.service, cand.service
                    ) and cand.service in anomalous_services
                    if not explains_cascade_core or (
                        not is_upstream_cause
                        and len(set(cand.explained_affected_services) & cascade) <= 1
                    ):
                        # Prefer parallel label when cand does not cover the multi-victim cascade
                        cascade_victims = cascade - {top.service}
                        covered_victims = set(cand.explained_affected_services) & cascade_victims
                        if len(covered_victims) < max(1, len(cascade_victims)):
                            if not is_upstream_cause:
                                cand.classification = "unexplained_parallel_anomaly"
                                continue

                # Downstream symptom: in cascade, not root, local anomaly or not
                if in_cascade and cand.service != top.service:
                    contrib = cand.contributions.get("trace_origin_support")
                    victim_like = (
                        contrib is not None
                        and contrib.raw_value is not None
                        and contrib.raw_value < 0.45
                    )
                    if cand.service in top.explained_affected_services or working_graph.has_call_path(
                        cand.service, top.service
                    ):
                        if victim_like or cand.service in anomalous_services:
                            cand.classification = "explained_downstream_symptom"
                            continue

                if cand.score < 0.15 and not cand.evidence:
                    cand.classification = "insufficient_evidence"
                else:
                    cand.classification = "root_candidate"

        # Attribution decision
        attribution_status: str
        suspected: str | None
        confidence: float
        explanation: str

        if multi_cluster and len(anomalous_services) >= 2:
            multi_service_components = [c for c in undirected_components if len(c) >= 2]
            single_components = [c for c in undirected_components if len(c) == 1]
            # Trace-supported single cascade + optional singleton noise may still attribute.
            # Without trace support, two+ undirected components abstain rather than invent
            # a global root (see multiple-independent-clusters fixture).
            top_trace = (
                candidates[0].contributions.get("trace_origin_support")
                if candidates
                else None
            )
            top_explains_cascade = bool(
                candidates
                and len(
                    set(candidates[0].explained_affected_services)
                    & anomalous_services
                )
                >= 2
            )
            can_attribute_cascade = (
                trace_available
                and len(multi_service_components) <= 1
                and candidates
                and candidates[0].classification != "unexplained_parallel_anomaly"
                and top_explains_cascade
                and top_trace is not None
                and top_trace.raw_value is not None
                and top_trace.raw_value > 0
            )
            if can_attribute_cascade and (
                score_margin is None
                or score_margin >= cfg.min_score_margin_for_attribution
            ):
                top = candidates[0]
                noise = [
                    c
                    for c in candidates
                    if c.classification == "unexplained_parallel_anomaly"
                ]
                attribution_status = "attributed"
                suspected = top.service
                top.classification = "suspected_root"
                confidence = min(0.95, max(0.0, top.score))
                noise_names = ", ".join(c.service for c in noise) or "none"
                explanation = (
                    f"Suspected root `{suspected}` ranks first with score "
                    f"{top.score:.3f} (margin={score_margin}). "
                    f"Explains affected services {top.explained_affected_services}. "
                    f"Parallel anomalies not selected as root: {noise_names}. "
                    f"{self._evidence_summary(top)}"
                )
            else:
                attribution_status = "multiple_independent_clusters"
                suspected = None
                confidence = 0.0
                explanation = (
                    "Multiple independent anomalous clusters without a single "
                    "supported cascade root across clusters."
                )
                for cand in candidates:
                    if cand.classification in {
                        "suspected_root",
                        "unexplained_parallel_anomaly",
                    }:
                        cand.classification = "root_candidate"
        elif (
            not candidates
            or candidates[0].score < 0.12
            or (
                len(candidates) > 1
                and score_margin is not None
                and score_margin < cfg.min_score_margin_for_attribution
            )
        ):
            attribution_status = "insufficient_evidence"
            suspected = None
            confidence = 0.0
            explanation = (
                "Insufficient evidence to attribute a root service safely. "
                f"Top score margin={score_margin}; unavailable signals: "
                f"{unavailable or 'none'}."
            )
            for cand in candidates:
                if cand.classification == "suspected_root":
                    cand.classification = "insufficient_evidence"
        else:
            attribution_status = "attributed"
            suspected = candidates[0].service
            candidates[0].classification = "suspected_root"
            confidence = min(0.95, max(0.0, candidates[0].score))
            explanation = self._build_explanation(candidates[0], score_margin)

        # Re-rank numbers already set; ensure only one suspected_root
        for cand in candidates:
            if cand.service == suspected:
                cand.classification = "suspected_root"
            elif cand.classification == "suspected_root":
                cand.classification = "root_candidate"

        ended = datetime.now(timezone.utc)
        return RCAResult(
            model_version=cfg.model_version,
            attribution_status=attribution_status,  # type: ignore[arg-type]
            suspected_root_service=suspected,
            confidence=round(confidence, 6),
            score_margin=score_margin,
            explanation=explanation,
            candidates=candidates,
            unavailable_signals=unavailable,
            topology_provenance=provenance,
            analysis_started_at=started,
            analysis_ended_at=ended,
            processing_ms=round((ended - started).total_seconds() * 1000.0, 3),
            trace_count=len(parse.trace_ids),
            span_count=len(parse.spans),
        )

    def _score_candidate(
        self,
        *,
        service: str,
        by_service: Mapping[str, RCAObservation],
        affected: Sequence[str],
        graph: DependencyGraph,
        origins: Mapping[str, Any],
        trace_available: bool,
        traces_explicitly_unavailable: bool,
        anomalous_services: set[str],
    ) -> RCACandidate:
        cfg = self.config
        obs = by_service.get(service)
        evidence_facts: list[RCAEvidenceFact] = []
        contradictions: list[str] = []

        # --- trace_origin_support ---
        origin = origins.get(service)
        if traces_explicitly_unavailable:
            trace_contrib = RCASignalContribution(
                available=False,
                raw_value=None,
                weight=cfg.trace_weight,
                weighted_value=None,
                reason="trace telemetry unavailable",
            )
        elif not trace_available and not origins:
            trace_contrib = RCASignalContribution(
                available=False,
                raw_value=None,
                weight=cfg.trace_weight,
                weighted_value=None,
                reason="no spans in analysis window",
            )
        elif origin is None:
            # Service not in traces — neutral low raw if others have traces
            raw = 0.0
            reason = "service absent from error spans"
            if origins:
                # Slight penalty not applied here; raw 0 with available true means no support
                pass
            trace_contrib = RCASignalContribution(
                available=True,
                raw_value=raw,
                weight=cfg.trace_weight,
                weighted_value=None,  # filled later
                reason=reason,
            )
        else:
            raw = float(origin.root_like_score)
            # Penalize victim-like inside feature raw value
            raw = max(0.0, raw - 0.5 * float(origin.victim_like_score))
            reason = (
                f"root_like={origin.root_like_score:.3f} "
                f"victim_like={origin.victim_like_score:.3f} "
                f"server_errors={origin.server_error_count} "
                f"client_errors={origin.client_error_count}"
            )
            if origin.victim_like_score > origin.root_like_score and origin.victim_like_score > 0.2:
                contradictions.append(
                    f"trace shows dependency-victim pattern for {service}"
                )
            for fact in origin.facts[:5]:
                evidence_facts.append(
                    RCAEvidenceFact(
                        source="trace",
                        fact=fact,
                        support=raw,
                        available=True,
                        trace_id=origin.trace_ids[0] if origin.trace_ids else None,
                        span_ids=list(origin.span_ids)[:8],
                    )
                )
            trace_contrib = RCASignalContribution(
                available=True,
                raw_value=round(raw, 6),
                weight=cfg.trace_weight,
                weighted_value=None,
                reason=reason,
            )

        # --- causal_coverage ---
        explained = graph.affected_callers_explained_by(service, affected)
        # Also count services that call this candidate (victims) + self
        explained_list = sorted(explained)
        if affected:
            # coverage = fraction of affected that are self or can reach candidate as callee
            # i.e. candidate is ancestor (callee side) of affected callers
            coverage_raw = len(explained) / max(len(affected), 1)
        else:
            coverage_raw = 0.0
        # Topology is candidate-specific: a global static graph must not turn an
        # unseen, unconnected service's missing topology into a healthy zero.
        topology_available = bool(
            service in graph.services()
            and (graph.callers(service) or graph.callees(service))
        )
        if topology_available:
            topo_contrib = RCASignalContribution(
                available=True,
                raw_value=round(min(1.0, coverage_raw), 6),
                weight=cfg.topology_weight,
                weighted_value=None,
                reason=f"explains {len(explained_list)}/{len(affected)} affected via call paths",
            )
            if explained_list:
                evidence_facts.append(
                    RCAEvidenceFact(
                        source="topology",
                        fact=(
                            f"{service} can explain affected callers "
                            f"{explained_list} (caller->callee graph)"
                        ),
                        support=coverage_raw,
                        available=True,
                        provenance="static+dynamic",
                    )
                )
        else:
            topo_contrib = RCASignalContribution(
                available=False,
                raw_value=None,
                weight=cfg.topology_weight,
                weighted_value=None,
                reason="topology unavailable",
            )

        # --- temporal_consistency ---
        onset = obs.onset() if obs else None
        temporal_raw: float | None
        if onset is None:
            temporal_contrib = RCASignalContribution(
                available=False,
                raw_value=None,
                weight=cfg.temporal_weight,
                weighted_value=None,
                reason="missing onset timestamp",
            )
            temporal_raw = None
        else:
            # Pairwise: candidate onset should be <= explained services + tolerance
            tol = cfg.temporal_tolerance_seconds
            comparisons = 0
            consistent = 0
            for other_name in explained_list:
                if other_name == service:
                    continue
                other = by_service.get(other_name)
                other_onset = other.onset() if other else None
                if other_onset is None:
                    continue
                comparisons += 1
                delta = (other_onset - onset).total_seconds()
                if delta >= -tol:
                    consistent += 1
                else:
                    contradictions.append(
                        f"onset of {service} is later than {other_name} by {-delta:.1f}s"
                    )
            if comparisons == 0:
                temporal_raw = None
                reason = "insufficient pairwise onset pairs"
            else:
                temporal_raw = consistent / comparisons
                reason = f"temporal consistency {consistent}/{comparisons} within {tol}s"
            if temporal_raw is None:
                temporal_contrib = RCASignalContribution(
                    available=False,
                    raw_value=None,
                    weight=cfg.temporal_weight,
                    weighted_value=None,
                    reason=reason,
                )
            else:
                temporal_contrib = RCASignalContribution(
                    available=True,
                    raw_value=round(temporal_raw, 6),
                    weight=cfg.temporal_weight,
                    weighted_value=None,
                    reason=reason,
                )
                evidence_facts.append(
                    RCAEvidenceFact(
                        source="temporal",
                        fact=reason,
                        support=float(temporal_raw),
                        available=True,
                        observed_at=onset,
                    )
                )

        # --- local_anomaly_support ---
        if obs is None:
            anomaly_contrib = RCASignalContribution(
                available=False,
                raw_value=None,
                weight=cfg.anomaly_weight,
                weighted_value=None,
                reason="no local detector observation",
            )
        else:
            # Bounded aggregation: max confidence among anomalous signals
            anomalous_signals = [s for s in obs.signals if s.anomalous]
            if anomalous_signals:
                conf = max(s.confidence for s in anomalous_signals)
                # coverage: unavailable signals don't count as healthy
                if any(s.coverage_status == "unavailable" for s in obs.signals):
                    # still use conf but note it
                    reason = f"max anomalous confidence={conf:.3f} (some signals unavailable)"
                else:
                    reason = f"max anomalous confidence={conf:.3f} across {len(anomalous_signals)} signal(s)"
                anomaly_raw = max(0.0, min(1.0, conf))
            else:
                anomaly_raw = 0.0
                reason = "no local anomalous signal"
            anomaly_contrib = RCASignalContribution(
                available=True,
                raw_value=round(anomaly_raw, 6),
                weight=cfg.anomaly_weight,
                weighted_value=None,
                reason=reason,
            )
            if anomalous_signals:
                evidence_facts.append(
                    RCAEvidenceFact(
                        source="anomaly",
                        fact=reason,
                        support=anomaly_raw,
                        available=True,
                    )
                )

        contributions = {
            "trace_origin_support": trace_contrib,
            "causal_coverage": topo_contrib,
            "temporal_consistency": temporal_contrib,
            "local_anomaly_support": anomaly_contrib,
        }

        # Availability-aware normalization
        available_weights = 0.0
        weighted_sum = 0.0
        for name, contrib in contributions.items():
            if contrib.available and contrib.raw_value is not None:
                w = contrib.weight
                available_weights += w
                wv = w * float(contrib.raw_value)
                weighted_sum += wv
                contrib.weighted_value = round(wv, 6)
            else:
                contrib.weighted_value = None

        if available_weights > 0:
            base_score = round(weighted_sum / available_weights, 6)
        else:
            base_score = 0.0

        # Penalties
        penalty = 0.0
        penalties: dict[str, float] = {}
        if any("dependency-victim" in c for c in contradictions):
            penalty += cfg.contradiction_penalty
            penalties["dependency_victim"] = cfg.contradiction_penalty
        if any("later than" in c for c in contradictions):
            temporal_penalty = min(cfg.contradiction_penalty, 0.1)
            penalty += temporal_penalty
            penalties["temporal_contradiction"] = temporal_penalty

        # Parallel anomaly penalty applied later in classification; light topology disconnect
        disconnected = False
        if trace_available and service in anomalous_services and affected:
            if not any(
                service == a
                or graph.has_call_path(service, a)
                or graph.has_call_path(a, service)
                for a in affected
                if a != service
            ) and len(affected) > 1:
                disconnected = True
                penalty += cfg.parallel_anomaly_penalty
                penalties["parallel_anomaly"] = cfg.parallel_anomaly_penalty
                contradictions.append(
                    f"{service} is disconnected from primary affected cluster"
                )

        score = max(0.0, min(1.0, base_score - penalty))
        score = round(score, 6)

        # Verify contribution accounting: store base for debugging in reason is enough
        classification = "root_candidate"
        return RCACandidate(
            service=service,
            score=score,
            rank=0,
            classification=classification,
            contributions=contributions,
            base_score=round(base_score, 6),
            penalties={name: round(value, 6) for name, value in penalties.items()},
            explained_affected_services=explained_list,
            contradictions=contradictions,
            evidence=evidence_facts,
        )

    def _build_explanation(
        self, top: RCACandidate, score_margin: float | None
    ) -> str:
        margin = f"{score_margin:.3f}" if score_margin is not None else "n/a"
        return (
            f"Suspected root `{top.service}` ranks first with score {top.score:.3f} "
            f"(margin={margin}). Explains affected services "
            f"{top.explained_affected_services}. {self._evidence_summary(top)}"
        )

    @staticmethod
    def _evidence_summary(top: RCACandidate) -> str:
        facts = [e.fact for e in top.evidence[:4]]
        if not facts:
            return "Limited structured evidence facts."
        return "Evidence: " + "; ".join(facts)


def observations_from_decisions(
    decisions: Iterable[Any],
    *,
    aliases: Mapping[str, str] | None = None,
    observed_at: datetime | None = None,
) -> list[RCAObservation]:
    """Aggregate detector Decision objects by canonical service."""

    now = observed_at or datetime.now(timezone.utc)
    buckets: dict[str, RCAObservation] = {}
    for decision in decisions:
        if decision is None:
            continue
        raw_service = getattr(decision, "service", None) or ""
        identity = normalize_service_name(raw_service, aliases=aliases)
        service = identity.canonical_service
        signal = getattr(decision, "incident_type", "unknown")
        obs_signal = SignalObservation(
            signal=str(signal),
            anomalous=bool(getattr(decision, "anomalous", False)),
            breached=bool(getattr(decision, "breached", False)),
            coverage_status=getattr(decision, "coverage_status", "available") or "available",
            confidence=float(getattr(decision, "confidence", 0.0) or 0.0),
            severity=str(getattr(decision, "severity", "medium") or "medium"),
            observed_at=now,
            first_breached_at=now if getattr(decision, "breached", False) else None,
            first_anomalous_at=now if getattr(decision, "anomalous", False) else None,
            evidence=list(getattr(decision, "evidence", []) or []),
        )
        if service not in buckets:
            buckets[service] = RCAObservation(
                service=service,
                original_service_names=[identity.original_service],
                signals=[obs_signal],
                first_breached_at=obs_signal.first_breached_at,
                first_anomalous_at=obs_signal.first_anomalous_at,
            )
        else:
            bucket = buckets[service]
            if identity.original_service not in bucket.original_service_names:
                bucket.original_service_names.append(identity.original_service)
            bucket.signals.append(obs_signal)
            if obs_signal.first_breached_at and (
                bucket.first_breached_at is None
                or obs_signal.first_breached_at < bucket.first_breached_at
            ):
                bucket.first_breached_at = obs_signal.first_breached_at
            if obs_signal.first_anomalous_at and (
                bucket.first_anomalous_at is None
                or obs_signal.first_anomalous_at < bucket.first_anomalous_at
            ):
                bucket.first_anomalous_at = obs_signal.first_anomalous_at
    return sorted(buckets.values(), key=lambda o: o.service)


def parse_traces_payload(
    traces_block: Mapping[str, Any] | None,
    *,
    aliases: Mapping[str, str] | None = None,
    max_traces: int = 50,
    max_spans: int = 5000,
) -> tuple[TraceParseResult | None, list[str]]:
    """Parse replay `traces` object. Returns (parse, unavailable_signals)."""

    if traces_block is None:
        return TraceParseResult(), []
    if traces_block.get("unavailable") is True or traces_block.get("status") == "unavailable":
        return TraceParseResult(), ["trace"]
    fmt = str(traces_block.get("format") or "jaeger-v1").lower()
    data = traces_block.get("data") or traces_block.get("traces") or []
    if not isinstance(data, list):
        raise ValueError("traces.data must be a list")
    if fmt in {"jaeger-v1", "jaeger", "jaeger_v1"}:
        return (
            parse_jaeger_traces(
                data, aliases=aliases, max_traces=max_traces, max_spans=max_spans
            ),
            [],
        )
    if fmt in {"normalized", "normalized-spans", "spans"}:
        return (
            parse_normalized_spans(
                data,
                aliases=aliases,
                max_traces=max_traces,
                max_spans=max_spans,
            ),
            [],
        )
    raise ValueError(f"unsupported trace format: {fmt}")
