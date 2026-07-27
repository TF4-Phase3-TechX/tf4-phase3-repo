from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in os.getenv(name, default).split(",") if x.strip())


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _float_map(name: str, default: str) -> dict[str, float]:
    result: dict[str, float] = {}
    raw = os.getenv(name, default)
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        key, separator, value = item.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"{name} entries must use service=value: {item!r}")
        parsed = float(value)
        if not 0 < parsed < 1:
            raise ValueError(f"{name} SLO targets must be between 0 and 1: {item!r}")
        result[key.strip()] = parsed
    return result


def _string_map(name: str, default: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    raw = os.getenv(name, default)
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        key, separator, value = item.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"{name} entries must use service=value: {item!r}")
        result[key.strip()] = value.strip()
    return result


def prometheus_duration_seconds(duration: str) -> int:
    """Convert a positive Prometheus duration (for example 2m, 90s) to seconds."""

    match = re.fullmatch(r"([1-9]\d*)(ms|s|m|h|d|w|y)", duration)
    if not match:
        raise ValueError(f"invalid Prometheus duration: {duration!r}")
    amount = int(match.group(1))
    unit = match.group(2)
    multipliers = {
        "ms": 0.001,
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
        "y": 31536000,
    }
    seconds = amount * multipliers[unit]
    if seconds < 1:
        raise ValueError(f"duration must be at least one second: {duration!r}")
    return int(seconds)


@dataclass(frozen=True)
class Settings:
    prometheus_url: str = os.getenv(
        "PROMETHEUS_URL", "http://prometheus.techx-observability.svc.cluster.local:9090"
    )
    opensearch_url: str = os.getenv(
        "OPENSEARCH_URL",
        "http://opensearch-cluster-master.techx-observability.svc.cluster.local:9200",
    )
    opensearch_index: str = os.getenv("OPENSEARCH_INDEX", "otel-logs-*")
    jaeger_url: str = os.getenv(
        "JAEGER_URL",
        "http://jaeger.techx-observability.svc.cluster.local:16686/jaeger/ui",
    )
    # Trace enrichment is deliberately narrower than the detector's metric
    # lookback. Jaeger returns complete trace payloads, so a 30-minute/20-trace
    # query can exceed the client timeout during a load incident.
    jaeger_trace_lookback: str = os.getenv("AIOPS_JAEGER_TRACE_LOOKBACK", "5m")
    jaeger_trace_limit: int = int(os.getenv("AIOPS_JAEGER_TRACE_LIMIT", "5"))
    grafana_url: str = os.getenv(
        "GRAFANA_URL", "http://grafana.techx-observability.svc.cluster.local/grafana"
    )
    opensearch_datasource_uid: str = os.getenv(
        "OPENSEARCH_DATASOURCE_UID", "webstore-logs"
    )
    environment: str = os.getenv("AIOPS_ENVIRONMENT", "production")
    tenant_id: str = os.getenv("AIOPS_TENANT_ID", "default")
    poll_seconds: int = int(os.getenv("AIOPS_POLL_SECONDS", "45"))
    lookback_minutes: int = int(os.getenv("AIOPS_LOOKBACK_MINUTES", "30"))
    sustained_polls: int = int(os.getenv("AIOPS_SUSTAINED_POLLS", "1"))
    # One worker poll contains several Prometheus scrape samples.  Confirm an
    # acute breach inside that range window so the detector can page within one
    # poll without treating a single isolated sample as an incident.
    acute_confirmation_window: int = int(
        os.getenv("AIOPS_ACUTE_CONFIRMATION_WINDOW", "3")
    )
    acute_min_breach_points: int = int(
        os.getenv("AIOPS_ACUTE_MIN_BREACH_POINTS", "2")
    )
    recovery_polls: int = int(os.getenv("AIOPS_RECOVERY_POLLS", "2"))
    availability_sustained_polls: int = int(
        os.getenv("AIOPS_AVAILABILITY_SUSTAINED_POLLS", "2")
    )
    busy_request_rate_threshold: float = float(
        os.getenv("AIOPS_BUSY_REQUEST_RATE_THRESHOLD", "5")
    )
    availability_down_confidence: float = float(
        os.getenv("AIOPS_AVAILABILITY_DOWN_CONFIDENCE", "0.95")
    )
    availability_degraded_confidence: float = float(
        os.getenv("AIOPS_AVAILABILITY_DEGRADED_CONFIDENCE", "0.80")
    )
    cooldown_seconds: int = int(os.getenv("AIOPS_COOLDOWN_SECONDS", "600"))
    minimum_request_count: int = int(os.getenv("AIOPS_MINIMUM_REQUEST_COUNT", "20"))
    llm_minimum_call_count: int = int(os.getenv("AIOPS_LLM_MINIMUM_CALL_COUNT", "5"))
    # These are safety floors, not the primary anomaly gate. Each service is
    # compared with its own robust rolling baseline by Detector.
    latency_threshold_ms: float = float(os.getenv("AIOPS_LATENCY_THRESHOLD_MS", "1000"))
    error_rate_threshold: float = float(os.getenv("AIOPS_ERROR_RATE_THRESHOLD", "0.05"))
    llm_error_threshold: float = float(os.getenv("AIOPS_LLM_ERROR_THRESHOLD", "0.05"))
    # Only services with an approved user-visible availability/success SLO are
    # listed. Unlisted services retain the explicit fixed-threshold fallback.
    service_slo_targets: dict[str, float] = field(
        default_factory=lambda: _float_map(
            "AIOPS_SERVICE_SLO_TARGETS",
            "frontend=0.995,cart=0.995,checkout=0.99",
        )
    )
    burn_rate_short_window_minutes: int = int(
        os.getenv("AIOPS_BURN_RATE_SHORT_WINDOW_MINUTES", "5")
    )
    burn_rate_long_window_minutes: int = int(
        os.getenv("AIOPS_BURN_RATE_LONG_WINDOW_MINUTES", "30")
    )
    burn_rate_warning_threshold: float = float(
        os.getenv("AIOPS_BURN_RATE_WARNING_THRESHOLD", "2")
    )
    burn_rate_critical_threshold: float = float(
        os.getenv("AIOPS_BURN_RATE_CRITICAL_THRESHOLD", "10")
    )
    # Detector seeds are configurable because they must be recalibrated from
    # labelled normal and incident windows. Defaults are conservative 7a
    # starting values, not claims of production-optimal tuning.
    baseline_mad_multiplier: float = float(
        os.getenv("AIOPS_BASELINE_MAD_MULTIPLIER", "6")
    )
    baseline_relative_band: float = float(
        os.getenv("AIOPS_BASELINE_RELATIVE_BAND", "0.5")
    )
    zscore_threshold: float = float(os.getenv("AIOPS_ZSCORE_THRESHOLD", "3"))
    zscore_noise_floor: float = float(os.getenv("AIOPS_ZSCORE_NOISE_FLOOR", "0.05"))
    ratio_threshold: float = float(os.getenv("AIOPS_RATIO_THRESHOLD", "1.5"))
    ewma_alpha: float = float(os.getenv("AIOPS_EWMA_ALPHA", "0.35"))
    ewma_spread_multiplier: float = float(
        os.getenv("AIOPS_EWMA_SPREAD_MULTIPLIER", "3")
    )
    ewma_relative_floor: float = float(os.getenv("AIOPS_EWMA_RELATIVE_FLOOR", "0.25"))
    ewma_threshold: float = float(os.getenv("AIOPS_EWMA_THRESHOLD", "1"))
    trend_window: int = int(os.getenv("AIOPS_TREND_WINDOW", "6"))
    trend_min_relative_change: float = float(
        os.getenv("AIOPS_TREND_MIN_RELATIVE_CHANGE", "0.25")
    )
    trend_min_current_ratio: float = float(
        os.getenv("AIOPS_TREND_MIN_CURRENT_RATIO", "1.2")
    )
    trend_min_consistency: float = float(
        os.getenv("AIOPS_TREND_MIN_CONSISTENCY", "0.75")
    )
    # A trend far below the service SLO is useful audit evidence but should not
    # page by itself. This guard separates real degradation from normal ramp-up.
    trend_min_floor_ratio: float = float(
        os.getenv("AIOPS_TREND_MIN_FLOOR_RATIO", "0.7")
    )
    isolation_contamination: float = float(
        os.getenv("AIOPS_ISOLATION_CONTAMINATION", "0.15")
    )
    # Confidence is an explainable operator-prioritisation score, not a
    # calibrated probability. Every contribution remains configurable for the
    # labelled production replay required by Mandate 7b.
    latency_confidence_base: float = float(
        os.getenv("AIOPS_LATENCY_CONFIDENCE_BASE", "0.45")
    )
    error_confidence_base: float = float(
        os.getenv("AIOPS_ERROR_CONFIDENCE_BASE", "0.50")
    )
    llm_confidence_base: float = float(os.getenv("AIOPS_LLM_CONFIDENCE_BASE", "0.45"))
    torai_confidence_weight: float = float(
        os.getenv("AIOPS_TORAI_CONFIDENCE_WEIGHT", "0.40")
    )
    zscore_confidence_weight: float = float(
        os.getenv("AIOPS_ZSCORE_CONFIDENCE_WEIGHT", "0.10")
    )
    ewma_confidence_weight: float = float(
        os.getenv("AIOPS_EWMA_CONFIDENCE_WEIGHT", "0.15")
    )
    isolation_confidence_weight: float = float(
        os.getenv("AIOPS_ISOLATION_CONFIDENCE_WEIGHT", "0.05")
    )
    trend_confidence_weight: float = float(
        os.getenv("AIOPS_TREND_CONFIDENCE_WEIGHT", "0.10")
    )
    maximum_confidence: float = float(os.getenv("AIOPS_MAXIMUM_CONFIDENCE", "0.95"))
    torai_metric_weight: float = float(os.getenv("AIOPS_TORAI_METRIC_WEIGHT", "0.35"))
    torai_trace_weight: float = float(os.getenv("AIOPS_TORAI_TRACE_WEIGHT", "0.25"))
    torai_log_weight: float = float(os.getenv("AIOPS_TORAI_LOG_WEIGHT", "0.20"))
    torai_deploy_weight: float = float(os.getenv("AIOPS_TORAI_DEPLOY_WEIGHT", "0.10"))
    torai_ai_weight: float = float(os.getenv("AIOPS_TORAI_AI_WEIGHT", "0.10"))
    torai_metric_relative_span: float = float(
        os.getenv("AIOPS_TORAI_METRIC_RELATIVE_SPAN", "0.50")
    )
    torai_log_count_saturation: float = float(
        os.getenv("AIOPS_TORAI_LOG_COUNT_SATURATION", "3")
    )
    latency_high_multiplier: float = float(
        os.getenv("AIOPS_LATENCY_HIGH_MULTIPLIER", "2")
    )
    error_high_multiplier: float = float(os.getenv("AIOPS_ERROR_HIGH_MULTIPLIER", "2"))
    llm_high_error_rate: float = float(os.getenv("AIOPS_LLM_HIGH_ERROR_RATE", "0.25"))
    # Runtime controlled drills observed true high-severity acute latency
    # incidents at 0.742-0.743. With slow_drift=0, the configured confidence
    # terms have a theoretical ceiling of 0.75 and the normalized isolation
    # score remains below 1, so a 0.75 gate is structurally unreachable.
    # Severity, allowlist, runbook and evidence gates remain independent.
    remediation_confidence_threshold: float = float(
        os.getenv("AIOPS_REMEDIATION_CONFIDENCE_THRESHOLD", "0.74")
    )
    verification_error_rate_threshold: float = float(
        os.getenv("AIOPS_VERIFICATION_ERROR_RATE_THRESHOLD", "0.01")
    )
    # Post-action SLO samples with fewer requests than this floor fail closed.
    verification_minimum_request_count: int = int(
        os.getenv("AIOPS_VERIFICATION_MINIMUM_REQUEST_COUNT", "5")
    )
    # CDO-pinned known-good Deployment revision numbers
    # (deployment.kubernetes.io/revision). Required for every live mutation
    # target; dry-run may still inspect owned[1] without treating it as proven.
    known_good_revisions: dict[str, str] = field(
        default_factory=lambda: _string_map("AIOPS_KNOWN_GOOD_REVISIONS", "")
    )
    remediation_mode: str = os.getenv("REMEDIATION_MODE", "dry-run")
    autonomous_remediation_enabled: bool = _bool(
        "AIOPS_AUTONOMOUS_REMEDIATION_ENABLED"
    )
    remediation_policy_version: str = os.getenv(
        "AIOPS_REMEDIATION_POLICY_VERSION", "m22-v1"
    )
    autonomous_runbooks: tuple[str, ...] = field(
        default_factory=lambda: _csv(
            "AIOPS_AUTONOMOUS_RUNBOOKS", "deployment-latency-rollback"
        )
    )
    verification_polls: int = int(os.getenv("AIOPS_VERIFICATION_POLLS", "3"))
    rollback_verification_polls: int = int(
        os.getenv("AIOPS_ROLLBACK_VERIFICATION_POLLS", "3")
    )
    # Require the last N polls to be healthy so one stale first sample (live
    # drill pattern) does not veto an otherwise recovered window.
    verification_consecutive_healthy_polls: int = int(
        os.getenv("AIOPS_VERIFICATION_CONSECUTIVE_HEALTHY_POLLS", "2")
    )
    # Detection deliberately uses a stable 5m rate window. Post-action
    # verification must exclude the pre-action incident, so it uses a short
    # window after an explicit settle delay while retaining the same SLO.
    # Default settle is strictly greater than the default 2m window so the
    # first verification poll's range no longer fully overlaps the action.
    verification_metric_window: str = os.getenv(
        "AIOPS_VERIFICATION_METRIC_WINDOW", "2m"
    )
    verification_settle_seconds: float = float(
        os.getenv("AIOPS_VERIFICATION_SETTLE_SECONDS", "150")
    )
    verification_interval_seconds: float = float(
        os.getenv("AIOPS_VERIFICATION_INTERVAL_SECONDS", "20")
    )
    remediation_lock_ttl_seconds: int = int(
        os.getenv("AIOPS_REMEDIATION_LOCK_TTL_SECONDS", "900")
    )
    # Durable remediation saga (TF4AIO-89). memory = process-local tests;
    # file = JSON under AIOPS_SAGA_PATH on an operator-provided durable volume.
    saga_backend: str = os.getenv("AIOPS_SAGA_BACKEND", "memory")
    saga_path: str = os.getenv("AIOPS_SAGA_PATH", "")
    saga_retention_hours: int = int(os.getenv("AIOPS_SAGA_RETENTION_HOURS", "72"))
    argo_window_enabled: bool = _bool("AIOPS_ARGO_WINDOW_ENABLED", "true")
    approval_token: str = os.getenv("AIOPS_APPROVAL_TOKEN", "")
    approval_ttl_seconds: int = int(os.getenv("AIOPS_APPROVAL_TTL_SECONDS", "900"))
    deployment_recency_hours: int = int(
        os.getenv("AIOPS_DEPLOYMENT_RECENCY_HOURS", "24")
    )
    namespace: str = os.getenv("AIOPS_TARGET_NAMESPACE", "techx-corp")
    allowed_deployments: tuple[str, ...] = field(
        default_factory=lambda: _csv("AIOPS_ALLOWED_DEPLOYMENTS", "llm,product-reviews")
    )
    services: tuple[str, ...] = field(
        default_factory=lambda: _csv(
            "AIOPS_MONITORED_SERVICES", "llm,product-reviews,frontend,checkout"
        )
    )
    # Only services that export the generic server-span metrics belong in this
    # set. Availability monitoring still covers every monitored service, while
    # service-specific signals (for example LLM call errors) use their own
    # instrumentation and ownership discovery.
    generic_signal_services: tuple[str, ...] = field(
        default_factory=lambda: _csv(
            "AIOPS_GENERIC_SIGNAL_SERVICES",
            "product-reviews,frontend,cart,checkout",
        )
    )
    # Expected callers are used only to report unavailable coverage. Actual
    # incident ownership is discovered from the service_name metric label.
    llm_services: tuple[str, ...] = field(
        default_factory=lambda: _csv("AIOPS_LLM_SERVICES", "product-reviews")
    )
    llm_log_services: tuple[str, ...] = field(
        default_factory=lambda: _csv("AIOPS_LLM_LOG_SERVICES", "llm,product-reviews")
    )
    # Mandate-26 cross-service RCA (informational; never retargets remediation).
    rca_enabled: bool = field(
        default_factory=lambda: _bool("AIOPS_RCA_ENABLED", "true")
    )
    rca_model_version: str = os.getenv("AIOPS_RCA_MODEL_VERSION", "m26-v1")
    rca_analysis_window_seconds: float = float(
        os.getenv("AIOPS_RCA_ANALYSIS_WINDOW_SECONDS", "180")
    )
    rca_temporal_tolerance_seconds: float = float(
        os.getenv("AIOPS_RCA_TEMPORAL_TOLERANCE_SECONDS", "45")
    )
    rca_timeout_seconds: float = float(os.getenv("AIOPS_RCA_TIMEOUT_SECONDS", "2"))
    rca_max_services: int = int(os.getenv("AIOPS_RCA_MAX_SERVICES", "32"))
    rca_max_traces: int = int(os.getenv("AIOPS_RCA_MAX_TRACES", "50"))
    rca_max_spans: int = int(os.getenv("AIOPS_RCA_MAX_SPANS", "5000"))
    rca_trace_weight: float = float(os.getenv("AIOPS_RCA_TRACE_WEIGHT", "0.35"))
    rca_topology_weight: float = float(os.getenv("AIOPS_RCA_TOPOLOGY_WEIGHT", "0.30"))
    rca_temporal_weight: float = float(os.getenv("AIOPS_RCA_TEMPORAL_WEIGHT", "0.20"))
    rca_anomaly_weight: float = float(os.getenv("AIOPS_RCA_ANOMALY_WEIGHT", "0.15"))
    rca_contradiction_penalty: float = float(
        os.getenv("AIOPS_RCA_CONTRADICTION_PENALTY", "0.20")
    )
    rca_parallel_anomaly_penalty: float = float(
        os.getenv("AIOPS_RCA_PARALLEL_ANOMALY_PENALTY", "0.25")
    )

    def __post_init__(self) -> None:
        if self.jaeger_trace_limit <= 0:
            raise ValueError("Jaeger trace limit must be positive")
        if not re.fullmatch(
            r"[1-9]\d*(?:ms|s|m|h|d|w|y)", self.verification_metric_window
        ):
            raise ValueError(
                "verification metric window must be one positive Prometheus duration"
            )
        if self.verification_settle_seconds < 0:
            raise ValueError("verification settle seconds cannot be negative")
        # Offline/replay may set settle=0. Live/drill configs must keep the
        # settle delay at least as long as the metric window so the first poll
        # is not entirely pre-action traffic.
        if self.verification_settle_seconds > 0:
            window_seconds = prometheus_duration_seconds(
                self.verification_metric_window
            )
            if self.verification_settle_seconds < window_seconds:
                raise ValueError(
                    "verification settle seconds must be >= verification metric "
                    "window so the first post-action poll is not fully pre-action"
                )
        if self.verification_consecutive_healthy_polls < 1:
            raise ValueError(
                "verification consecutive healthy polls must be at least 1"
            )
        if self.verification_minimum_request_count < 0:
            raise ValueError(
                "verification minimum request count cannot be negative"
            )
        if self.saga_retention_hours <= 0:
            raise ValueError("saga retention hours must be positive")
        if self.saga_backend.strip().lower() in {"file", "fs", "json"}:
            if not self.saga_path.strip():
                raise ValueError(
                    "AIOPS_SAGA_PATH is required when AIOPS_SAGA_BACKEND is file"
                )
        if self.saga_backend.strip().lower() == "configmap":
            raise ValueError("configmap saga backend is not implemented")
        if (
            self.remediation_mode == "live"
            and self.autonomous_remediation_enabled
            and self.saga_backend.strip().lower()
            in {"", "memory", "mem", "none", "off"}
        ):
            raise ValueError(
                "live autonomous remediation requires a durable saga backend"
            )
        if self.burn_rate_short_window_minutes <= 0:
            raise ValueError("burn-rate short window must be positive")
        if (
            self.burn_rate_long_window_minutes
            <= self.burn_rate_short_window_minutes
        ):
            raise ValueError("burn-rate long window must be greater than short window")
        if self.burn_rate_warning_threshold <= 0:
            raise ValueError("burn-rate warning threshold must be positive")
        if (
            self.burn_rate_critical_threshold
            < self.burn_rate_warning_threshold
        ):
            raise ValueError(
                "burn-rate critical threshold must be >= warning threshold"
            )
        # Mandate-26 RCA config validation (fail closed at startup).
        rca_weights = (
            self.rca_trace_weight,
            self.rca_topology_weight,
            self.rca_temporal_weight,
            self.rca_anomaly_weight,
        )
        if any(w < 0 or w != w or w == float("inf") for w in rca_weights):
            raise ValueError("RCA feature weights must be finite and nonnegative")
        if sum(rca_weights) <= 0:
            raise ValueError("RCA total feature weight must be positive")
        for name, value in (
            ("AIOPS_RCA_CONTRADICTION_PENALTY", self.rca_contradiction_penalty),
            ("AIOPS_RCA_PARALLEL_ANOMALY_PENALTY", self.rca_parallel_anomaly_penalty),
        ):
            if value < 0 or value > 1 or value != value:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.rca_timeout_seconds <= 0:
            raise ValueError("AIOPS_RCA_TIMEOUT_SECONDS must be positive")
        if self.rca_analysis_window_seconds <= 0:
            raise ValueError("AIOPS_RCA_ANALYSIS_WINDOW_SECONDS must be positive")
        if self.rca_temporal_tolerance_seconds < 0:
            raise ValueError("AIOPS_RCA_TEMPORAL_TOLERANCE_SECONDS cannot be negative")
        if self.rca_analysis_window_seconds < self.rca_temporal_tolerance_seconds:
            raise ValueError(
                "AIOPS_RCA_ANALYSIS_WINDOW_SECONDS must be >= "
                "AIOPS_RCA_TEMPORAL_TOLERANCE_SECONDS"
            )
        if self.rca_max_services <= 0 or self.rca_max_traces <= 0 or self.rca_max_spans <= 0:
            raise ValueError("RCA resource limits must be positive")
