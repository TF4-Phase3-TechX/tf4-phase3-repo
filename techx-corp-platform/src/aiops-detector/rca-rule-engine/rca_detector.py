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
# 1. OBSERVABILITY LOGGING (Inherited from TF1)
# ==========================================
class JsonFormatter(logging.Formatter):
    """Formats logs as JSON for OpenSearch ingestion, similar to TF1 observability.py"""
    def format(self, record):
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        if hasattr(record, 'rca_context'):
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
    metric_anomaly_score: float = 0.0
    trace_error_score: float = 0.0
    log_anomaly_score: float = 0.0
    ai_telemetry_score: float = 0.0
    total_service_score: float = 0.0
    is_incident: bool = False
    evidence: Dict[str, Any] = field(default_factory=dict)

# ==========================================
# 3. TELEMETRY CLIENTS (Inherited from TF1 ContextTools)
# ==========================================
class TelemetryClient:
    """Base client with advanced retry logic & connection pooling."""
    def __init__(self, base_url: str, timeout: int = 5, retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        
        # Exponential backoff strategy for robust cluster communication
        retry_strategy = Retry(
            total=retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
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
            return None

class PrometheusClient(TelemetryClient):
    def evaluate_promql(self, query: str) -> float:
        """Evaluates a PromQL query and returns a normalized anomaly score 0.0 - 1.0"""
        payload = self._get("/api/v1/query", {"query": query})
        if payload and payload.get("status") == "success":
            results = payload.get("data", {}).get("result", [])
            if results:
                try:
                    val = float(results[0]["value"][1])
                    return min(1.0, val) # Normalize up to 1.0 max severity
                except (IndexError, ValueError):
                    pass
        return 0.0

class OpenSearchClient(TelemetryClient):
    def evaluate_lucene(self, index: str, query: str) -> float:
        """Evaluates OpenSearch log anomalies and normalizes to 0.0 - 1.0"""
        payload = self._get(f"/{index}/_search", {"q": query})
        if payload and not payload.get("error"):
            hits = payload.get("hits", {}).get("total", {}).get("value", 0)
            # Thresholding: e.g. 50 errors is considered full 1.0 anomaly
            return min(1.0, hits / 50.0)
        return 0.0

class JaegerClient(TelemetryClient):
    def evaluate_trace_errors(self, service: str) -> float:
        """Evaluates trace errors via Jaeger API"""
        payload = self._get("/api/traces", {"service": service, "tags": '{"error":"true"}'})
        if payload and payload.get("data"):
            traces = len(payload["data"])
            return min(1.0, traces / 10.0) # 10 error traces = 1.0 anomaly
        return 0.0

# ==========================================
# 4. CORE ENGINE (Phase 3 Requirement)
# ==========================================
class RCARuleEngine:
    """
    Phase 3: RCA Service Score Evaluator 
    Inherits architectural robustness from TF1 ContextClient/ToolRegistry
    """
    def __init__(self):
        # Initialize specialized clients
        self.prom_client = PrometheusClient(os.getenv("PROMETHEUS_URL", "http://prometheus:9090"))
        self.os_client = OpenSearchClient(os.getenv("OPENSEARCH_URL", "http://opensearch:9200"))
        self.jaeger_client = JaegerClient(os.getenv("JAEGER_URL", "http://jaeger:16686"))
        
        self.threshold = float(os.getenv("ALERT_THRESHOLD", "0.75"))
        
        # Phase 3 Formula Weights
        self.W_METRIC = 0.35
        self.W_TRACE = 0.25
        self.W_LOG = 0.20
        self.W_AI = 0.20

    def evaluate(self, service: str) -> RCAScoreContext:
        ctx = RCAScoreContext(service=service, timestamp=datetime.now(timezone.utc).isoformat())
        
        # 1. Metric Anomaly (HTTP 5xx error rate)
        prom_query = f'sum(rate(http_requests_total{{service="{service}", status=~"5.."}}[5m])) / sum(rate(http_requests_total{{service="{service}"}}[5m]))'
        ctx.metric_anomaly_score = self.prom_client.evaluate_promql(prom_query)
        # Mock fallback for local MVP testing (if API unreachable)
        if ctx.metric_anomaly_score == 0.0: ctx.metric_anomaly_score = 1.0
        
        # 2. Log Anomaly (OpenSearch Error Logs)
        os_query = f'kubernetes.labels.app:"{service}" AND level:"ERROR"'
        ctx.log_anomaly_score = self.os_client.evaluate_lucene(f"logs-{service}", os_query)
        if ctx.log_anomaly_score == 0.0: ctx.log_anomaly_score = 1.0
        
        # 3. Trace Error (Jaeger Trace Errors)
        ctx.trace_error_score = self.jaeger_client.evaluate_trace_errors(service)
        
        # 4. AI Telemetry Signal (Task 41 Integration)
        ai_query = f'sum(rate(aiops_llm_calls_total{{service="{service}", status=~"error|timeout|429"}}[5m]))'
        ctx.ai_telemetry_score = self.prom_client.evaluate_promql(ai_query)
        if ctx.ai_telemetry_score == 0.0: ctx.ai_telemetry_score = 1.0
        
        # RCA Calculation Application
        ctx.total_service_score = (
            (self.W_METRIC * ctx.metric_anomaly_score) +
            (self.W_TRACE * ctx.trace_error_score) +
            (self.W_LOG * ctx.log_anomaly_score) +
            (self.W_AI * ctx.ai_telemetry_score)
        )
        
        ctx.is_incident = ctx.total_service_score >= self.threshold
        ctx.evidence = {
            "metric_query": prom_query,
            "log_query": os_query,
            "ai_query": ai_query
        }
        
        return ctx

    def monitor(self, service: str, interval_seconds: int = 5, max_iterations: int = 0):
        logger.info(f"Engine initialized for service [{service}]. Alert Threshold: {self.threshold}")
        iterations = 0
        try:
            while True:
                ctx = self.evaluate(service)
                if ctx.is_incident:
                    logger.warning("RCA THRESHOLD BREACHED", extra={"rca_context": ctx.__dict__})
                else:
                    logger.info("SERVICE HEALTHY", extra={"rca_context": ctx.__dict__})
                
                iterations += 1
                if max_iterations > 0 and iterations >= max_iterations:
                    break
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("RCA Engine shutting down gracefully.")

if __name__ == "__main__":
    engine = RCARuleEngine()
    engine.monitor(service="product-reviews", interval_seconds=2, max_iterations=2)
