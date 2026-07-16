import os
import json
import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# 1. OBSERVABILITY LOGGING
# ==========================================
class JsonFormatter(logging.Formatter):
    """Formats logs as JSON for OpenSearch ingestion."""
    def format(self, record):
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "rca_context"):
            log_record["rca_context"] = record.rca_context
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


logger = logging.getLogger("RCARuleEngine")
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)


# ==========================================
# 2. DATA MODELS
# ==========================================
@dataclass
class RCAScoreContext:
    service: str
    timestamp: str
    # Score components: float = signal value, None = source unavailable
    metric_anomaly_score: Optional[float] = None
    trace_error_score: Optional[float] = None
    log_anomaly_score: Optional[float] = None
    ai_telemetry_score: Optional[float] = None
    # Derived fields
    total_service_score: float = 0.0
    sources_available: int = 0
    sources_unavailable: int = 0
    is_incident: bool = False
    confidence: str = "unknown"  # "high" | "partial" | "unknown"
    evidence: Dict[str, Any] = field(default_factory=dict)


# ==========================================
# 3. TELEMETRY CLIENTS
# ==========================================
class TelemetryClient:
    """Base client with retry logic. Returns None on source failure (not 0.0)."""

    def __init__(self, base_url: str, timeout: int = 5, retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        retry_strategy = Retry(
            total=retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _get(self, path: str, params: dict = None) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP Request failed for {url}: {str(e)}")
            return None  # Explicit None = source unavailable


class PrometheusClient(TelemetryClient):
    def evaluate_promql(self, query: str) -> Optional[float]:
        """
        Returns:
          float 0.0–1.0  : normalized score from live data
          None           : source unavailable / query error
        """
        payload = self._get("/api/v1/query", {"query": query})
        if payload is None:
            return None  # source unavailable
        if payload.get("status") != "success":
            return None
        results = payload.get("data", {}).get("result", [])
        if not results:
            return 0.0  # source healthy, no anomaly
        try:
            val = float(results[0]["value"][1])
            return min(1.0, val)
        except (IndexError, ValueError, KeyError):
            return 0.0


class OpenSearchClient(TelemetryClient):
    def evaluate_lucene(self, index: str, query: str) -> Optional[float]:
        """
        Returns:
          float 0.0–1.0  : normalized from hit count
          None           : source unavailable / query error
        """
        payload = self._get(f"/{index}/_search", {"q": query})
        if payload is None:
            return None  # source unavailable
        if payload.get("error"):
            return None
        hits = payload.get("hits", {}).get("total", {}).get("value", 0)
        return min(1.0, hits / 50.0)


class JaegerClient(TelemetryClient):
    def evaluate_trace_errors(self, service: str) -> Optional[float]:
        """
        Returns:
          float 0.0–1.0  : normalized from error trace count
          None           : source unavailable / query error
        """
        payload = self._get(
            "/api/traces", {"service": service, "tags": '{"error":"true"}'}
        )
        if payload is None:
            return None  # source unavailable
        traces = len(payload.get("data", []))
        return min(1.0, traces / 10.0)


# ==========================================
# 4. CORE ENGINE
# ==========================================
class RCARuleEngine:
    """
    Phase 3: RCA Service Score Evaluator.
    Distinguishes telemetry-source failure (None) from healthy zero (0.0).
    Only available sources contribute to the score calculation.
    """

    # Phase 3 formula weights
    W_METRIC = 0.35
    W_TRACE = 0.25
    W_LOG = 0.20
    W_AI = 0.20

    def __init__(self):
        self.prom_client = PrometheusClient(
            os.getenv("PROMETHEUS_URL", "http://prometheus.techx-observability.svc.cluster.local:9090")
        )
        self.os_client = OpenSearchClient(
            os.getenv("OPENSEARCH_URL", "http://opensearch.techx-observability.svc.cluster.local:9200")
        )
        self.jaeger_client = JaegerClient(
            os.getenv("JAEGER_URL", "http://jaeger:16686")
        )
        self.threshold = float(os.getenv("ALERT_THRESHOLD", "0.75"))

    def evaluate(self, service: str) -> RCAScoreContext:
        ctx = RCAScoreContext(
            service=service,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Define queries (using actual app_llm_* metric family)
        http_err_query = (
            f'sum(rate(traces_span_metrics_calls_total{{service_name="{service}", '
            f'status_code="STATUS_CODE_ERROR"}}[5m])) / '
            f'sum(rate(traces_span_metrics_calls_total{{service_name="{service}"}}[5m]))'
        )
        log_query = (
            f'resource.service.name:"{service}" AND severity.text:"ERROR"'
        )
        ai_query = 'sum(rate(app_llm_errors_total[5m]))'

        # 1. Metric Anomaly (HTTP 5xx)
        ctx.metric_anomaly_score = self.prom_client.evaluate_promql(http_err_query)

        # 2. Log Anomaly
        ctx.log_anomaly_score = self.os_client.evaluate_lucene("otel-logs-*", log_query)

        # 3. Trace Errors
        ctx.trace_error_score = self.jaeger_client.evaluate_trace_errors(service)

        # 4. AI Telemetry (app_llm_* — Task 41 integration)
        ctx.ai_telemetry_score = self.prom_client.evaluate_promql(ai_query)

        # Calculate score only from AVAILABLE sources (do not penalise for outages)
        components = [
            (self.W_METRIC, ctx.metric_anomaly_score),
            (self.W_TRACE, ctx.trace_error_score),
            (self.W_LOG, ctx.log_anomaly_score),
            (self.W_AI, ctx.ai_telemetry_score),
        ]

        available = [(w, s) for w, s in components if s is not None]
        unavailable = [(w, s) for w, s in components if s is None]

        ctx.sources_available = len(available)
        ctx.sources_unavailable = len(unavailable)

        if not available:
            # All sources down — cannot make a call
            ctx.total_service_score = 0.0
            ctx.confidence = "unknown"
            ctx.is_incident = False
        else:
            # Re-normalise weights so they sum to 1.0 across available sources
            total_weight = sum(w for w, _ in available)
            ctx.total_service_score = sum(
                (w / total_weight) * s for w, s in available
            )
            ctx.confidence = "high" if ctx.sources_unavailable == 0 else "partial"
            ctx.is_incident = ctx.total_service_score >= self.threshold

        ctx.evidence = {
            "metric_query": http_err_query,
            "log_query": log_query,
            "ai_query": ai_query,
            "sources_unavailable": ctx.sources_unavailable,
        }

        return ctx

    def monitor(
        self, service: str, interval_seconds: int = 15, max_iterations: int = 0
    ):
        logger.info(
            f"Engine started for [{service}]. Threshold: {self.threshold}"
        )
        iterations = 0
        try:
            while True:
                ctx = self.evaluate(service)
                log_extra = {"rca_context": ctx.__dict__}

                if ctx.confidence == "unknown":
                    logger.warning("ALL SOURCES UNAVAILABLE — skipping evaluation", extra=log_extra)
                elif ctx.is_incident:
                    logger.warning("RCA THRESHOLD BREACHED", extra=log_extra)
                else:
                    logger.info("SERVICE HEALTHY", extra=log_extra)

                iterations += 1
                if max_iterations > 0 and iterations >= max_iterations:
                    break
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("RCA Engine shutting down gracefully.")


if __name__ == "__main__":
    engine = RCARuleEngine()
    engine.monitor(service="product-reviews", interval_seconds=2, max_iterations=1)
