import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_error_detector")

class LLMTimeoutDetector:
    """
    Detector for identifying AI-specific LLM timeouts and errors
    from Prometheus metrics and Loki/OpenSearch logs.
    """
    def __init__(
        self, 
        prometheus_url: Optional[str] = None, 
        loki_url: Optional[str] = None
    ):
        self.prometheus_url = prometheus_url or os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
        self.loki_url = loki_url or os.getenv("LOKI_URL", "http://loki:3100")
        self.timeout_seconds = int(os.getenv("AIOPS_DETECTOR_TIMEOUT", "5"))

    def query_prometheus(self, query: str) -> List[Dict[str, Any]]:
        if not self.prometheus_url:
            return []
        
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
        except Exception as e:
            logger.error(f"Prometheus query failed: {e}")
        return []

    def query_loki(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.loki_url:
            return []
            
        try:
            response = requests.get(
                f"{self.loki_url.rstrip('/')}/loki/api/v1/query_range",
                params={"query": query, "limit": str(limit), "direction": "backward"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") == "success":
                return payload.get("data", {}).get("result", [])
        except Exception as e:
            logger.error(f"Loki query failed: {e}")
        return []

    def detect(self, service: str, environment: str, tenant_id: str, lookback_minutes: int = 15) -> Dict[str, Any]:
        """
        Detect LLM timeout or error scenarios.
        """
        logger.info(f"Running LLM Error Detector for {service} (env: {environment})")
        
        # 1. Check Metrics (e.g., aiops_llm_calls_total with status="error" or "timeout")
        # In a real environment, we'd use a rate query over the lookback window.
        metric_query = (
            f'sum(rate(aiops_llm_calls_total{{'
            f'service="{service}", environment="{environment}", tenant_id="{tenant_id}", status=~"error|timeout|429"'
            f'}}[{lookback_minutes}m])) > 0'
        )
        metric_results = self.query_prometheus(metric_query)
        
        # 2. Check Logs for specific LLM failure keywords
        # Looking for OpenAI, Anthropic, LLM timeouts, Rate limits (429), etc.
        log_query = (
            f'{{service="{service}", environment="{environment}", tenant_id="{tenant_id}"}} '
            '|~ "(?i)(llm|openai|anthropic|bedrock).*?(timeout|429|rate limit|exhausted|failed)"'
        )
        log_results = self.query_loki(log_query)

        # 3. Correlate and build incident
        incident = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rule": "ai_llm_timeout_error",
            "service": service,
            "environment": environment,
            "tenant_id": tenant_id,
            "severity": "high" if (metric_results and log_results) else ("medium" if log_results else "none"),
            "evidence": {
                "metrics_found": len(metric_results),
                "logs_found": len(log_results),
                "metric_details": metric_results,
                "log_details": log_results
            }
        }
        
        return incident

if __name__ == "__main__":
    detector = LLMTimeoutDetector()
    
    # Mock parameters for execution
    service_name = "tf1-ai-triage-engine"
    env = "production"
    tenant = "default"
    
    result = detector.detect(service=service_name, environment=env, tenant_id=tenant)
    print(json.dumps(result, indent=2))
