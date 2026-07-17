from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in os.getenv(name, default).split(",") if x.strip())


@dataclass(frozen=True)
class Settings:
    prometheus_url: str = os.getenv("PROMETHEUS_URL", "http://prometheus.techx-observability.svc.cluster.local:9090")
    opensearch_url: str = os.getenv("OPENSEARCH_URL", "http://opensearch-cluster-master.techx-observability.svc.cluster.local:9200")
    opensearch_index: str = os.getenv("OPENSEARCH_INDEX", "otel-logs-*")
    jaeger_url: str = os.getenv("JAEGER_URL", "http://jaeger.techx-observability.svc.cluster.local:16686/jaeger/ui")
    grafana_url: str = os.getenv("GRAFANA_URL", "http://grafana.techx-observability.svc.cluster.local/grafana")
    opensearch_datasource_uid: str = os.getenv("OPENSEARCH_DATASOURCE_UID", "webstore-logs")
    environment: str = os.getenv("AIOPS_ENVIRONMENT", "production")
    tenant_id: str = os.getenv("AIOPS_TENANT_ID", "default")
    poll_seconds: int = int(os.getenv("AIOPS_POLL_SECONDS", "45"))
    lookback_minutes: int = int(os.getenv("AIOPS_LOOKBACK_MINUTES", "30"))
    sustained_polls: int = int(os.getenv("AIOPS_SUSTAINED_POLLS", "2"))
    recovery_polls: int = int(os.getenv("AIOPS_RECOVERY_POLLS", "2"))
    cooldown_seconds: int = int(os.getenv("AIOPS_COOLDOWN_SECONDS", "600"))
    minimum_request_count: int = int(os.getenv("AIOPS_MINIMUM_REQUEST_COUNT", "20"))
    llm_minimum_call_count: int = int(os.getenv("AIOPS_LLM_MINIMUM_CALL_COUNT", "5"))
    # These are safety floors, not the primary anomaly gate. Each service is
    # compared with its own robust rolling baseline by Detector.
    latency_threshold_ms: float = float(os.getenv("AIOPS_LATENCY_THRESHOLD_MS", "1000"))
    error_rate_threshold: float = float(os.getenv("AIOPS_ERROR_RATE_THRESHOLD", "0.05"))
    llm_error_threshold: float = float(os.getenv("AIOPS_LLM_ERROR_THRESHOLD", "0.05"))
    llm_signal_owner: str = os.getenv("AIOPS_LLM_SIGNAL_OWNER", "product-reviews")
    remediation_mode: str = os.getenv("REMEDIATION_MODE", "dry-run")
    approval_token: str = os.getenv("AIOPS_APPROVAL_TOKEN", "")
    approval_ttl_seconds: int = int(os.getenv("AIOPS_APPROVAL_TTL_SECONDS", "900"))
    deployment_recency_hours: int = int(os.getenv("AIOPS_DEPLOYMENT_RECENCY_HOURS", "24"))
    namespace: str = os.getenv("AIOPS_TARGET_NAMESPACE", "techx-corp")
    allowed_deployments: tuple[str, ...] = field(default_factory=lambda: _csv("AIOPS_ALLOWED_DEPLOYMENTS", "llm,product-reviews"))
    services: tuple[str, ...] = field(default_factory=lambda: _csv("AIOPS_MONITORED_SERVICES", "llm,product-reviews,frontend,checkout"))
    llm_services: tuple[str, ...] = field(default_factory=lambda: _csv("AIOPS_LLM_SERVICES", "llm,product-reviews"))
