from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in os.getenv(name, default).split(",") if x.strip())


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


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
    # Bound both connect and read time for each Kubernetes Deployment lookup.
    # Availability is fail-safe unknown on timeout, never inferred as down.
    availability_api_timeout_seconds: float = float(
        os.getenv("AIOPS_AVAILABILITY_API_TIMEOUT_SECONDS", "3")
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
    remediation_confidence_threshold: float = float(
        os.getenv("AIOPS_REMEDIATION_CONFIDENCE_THRESHOLD", "0.75")
    )
    verification_error_rate_threshold: float = float(
        os.getenv("AIOPS_VERIFICATION_ERROR_RATE_THRESHOLD", "0.01")
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
    verification_interval_seconds: float = float(
        os.getenv("AIOPS_VERIFICATION_INTERVAL_SECONDS", "20")
    )
    remediation_lock_ttl_seconds: int = int(
        os.getenv("AIOPS_REMEDIATION_LOCK_TTL_SECONDS", "900")
    )
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
    # Expected callers are used only to report unavailable coverage. Actual
    # incident ownership is discovered from the service_name metric label.
    llm_services: tuple[str, ...] = field(
        default_factory=lambda: _csv("AIOPS_LLM_SERVICES", "product-reviews")
    )
    llm_log_services: tuple[str, ...] = field(
        default_factory=lambda: _csv("AIOPS_LLM_LOG_SERVICES", "llm,product-reviews")
    )
