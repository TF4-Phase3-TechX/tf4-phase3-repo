import os
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_error_detector")

# Sentinel value to distinguish "source unavailable" from "healthy zero"
_SOURCE_UNAVAILABLE = None


class LLMTimeoutDetector:
    """
    Detector for identifying AI-specific LLM timeouts and errors.
    Uses app_llm_* metric family (actual signals emitted by product-reviews)
    and OpenSearch for log queries.

    Score semantics:
      - count (int)  : healthy zero or real count from live telemetry
      - None         : telemetry source unavailable / query error
    """

    def __init__(
        self,
        prometheus_url: Optional[str] = None,
        opensearch_url: Optional[str] = None,
    ):
        self.prometheus_url = prometheus_url or os.getenv(
            "PROMETHEUS_URL", "http://prometheus.techx-observability.svc.cluster.local:9090"
        )
        self.opensearch_url = opensearch_url or os.getenv(
            "OPENSEARCH_URL", "http://opensearch.techx-observability.svc.cluster.local:9200"
        )
        self.timeout_seconds = int(os.getenv("AIOPS_DETECTOR_TIMEOUT", "5"))

    def query_prometheus(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """
        Returns result list on success, or None when source is unavailable.
        Empty list [] means source responded but matched nothing (healthy zero).
        """
        try:
            response = requests.get(
                f"{self.prometheus_url.rstrip('/')}/api/v1/query",
                params={"query": query},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") == "success":
                return payload.get("data", {}).get("result", [])
            logger.warning(f"Prometheus returned non-success status for query: {query}")
            return _SOURCE_UNAVAILABLE
        except Exception as e:
            logger.error(f"Prometheus unavailable: {e}")
            return _SOURCE_UNAVAILABLE

    def query_opensearch(
        self, index: str, query: str, limit: int = 50
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Returns hit list on success, or None when source is unavailable.
        Empty list [] means source responded but matched nothing (healthy zero).
        """
        try:
            response = requests.get(
                f"{self.opensearch_url.rstrip('/')}/{index}/_search",
                params={"q": query, "size": str(limit)},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                logger.warning(f"OpenSearch returned error for index {index}: {payload['error']}")
                return _SOURCE_UNAVAILABLE
            return payload.get("hits", {}).get("hits", [])
        except Exception as e:
            logger.error(f"OpenSearch unavailable: {e}")
            return _SOURCE_UNAVAILABLE

    def detect(
        self,
        service: str,
        environment: str,
        tenant_id: str,
        lookback_minutes: int = 15,
    ) -> Dict[str, Any]:
        """
        Detect LLM timeout or error scenarios.

        Severity mapping:
          - 'high'        : both metrics AND logs signal an error
          - 'medium'      : only metrics OR only logs signal an error
          - 'none'        : all available sources returned healthy zero
          - 'unknown'     : at least one telemetry source was unavailable
        """
        logger.info(f"Running LLM Error Detector for {service} (env: {environment}, tenant: {tenant_id})")

        # 1. Prometheus — app_llm_* metric family (actual signal emitted by product-reviews)
        # The production product-reviews instrumentation emits
        # app_llm_errors_total. It does not emit app_llm_requests_total or
        # service/environment/tenant labels on this instrument.
        metric_query = f'sum(rate(app_llm_errors_total[{lookback_minutes}m])) > 0'
        metric_results = self.query_prometheus(metric_query)

        # 2. OpenSearch — Lucene query for LLM failure keywords
        log_query = (
            f'resource.service.name:"{service}" '
            f'AND resource.deployment.environment:"{environment}" '
            f'AND (message:*timeout* OR message:*rate_limited* OR message:*429*) '
            f'AND (message:*llm* OR message:*openai* OR message:*bedrock*)'
        )
        log_index = "otel-logs-*"
        log_results = self.query_opensearch(log_index, log_query)

        # 3. Determine severity — clearly separate unavailable from healthy zero
        metric_hit = len(metric_results) > 0 if metric_results is not None else None
        log_hit = len(log_results) > 0 if log_results is not None else None

        if metric_results is None or log_results is None:
            # At least one source is down — we cannot make a confident call
            severity = "unknown"
        elif metric_hit and log_hit:
            severity = "high"
        elif metric_hit or log_hit:
            # metric-only or log-only is still an incident signal (medium)
            severity = "medium"
        else:
            severity = "none"

        incident = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rule": "ai_llm_timeout_error",
            "service": service,
            "environment": environment,
            "tenant_id": tenant_id,
            "severity": severity,
            "evidence": {
                "metric_query": metric_query,
                "log_query": log_query,
                "log_index": log_index,
                "metrics_available": metric_results is not None,
                "logs_available": log_results is not None,
                "metrics_found": len(metric_results) if metric_results is not None else 0,
                "logs_found": len(log_results) if log_results is not None else 0,
                "metric_details": metric_results or [],
                "log_details": log_results or [],
            },
        }

        return incident


if __name__ == "__main__":
    detector = LLMTimeoutDetector()

    service_name = "product-reviews"
    env = "production"
    tenant = "default"

    result = detector.detect(service=service_name, environment=env, tenant_id=tenant)
    print(json.dumps(result, indent=2))
