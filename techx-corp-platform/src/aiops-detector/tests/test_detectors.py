"""
Unit tests for AIOps detector suite (Task 38, 41, 43).
Uses unittest.mock to simulate Prometheus and OpenSearch backends.

Run: python -m pytest tests/ -v
"""
import json
import unittest
from unittest.mock import MagicMock, patch

import importlib.util
import os
import sys

# Dynamically load modules from hyphenated directories
base_dir = os.path.dirname(os.path.dirname(__file__))

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

llm_timeout_detector = load_module("llm_timeout_detector", os.path.join(base_dir, "w2-prototype", "llm_timeout_detector.py"))
rca_detector = load_module("rca_detector", os.path.join(base_dir, "rca-rule-engine", "rca_detector.py"))
incident_summary = load_module("incident_summary", os.path.join(base_dir, "w2-prototype", "incident_summary.py"))

LLMTimeoutDetector = llm_timeout_detector.LLMTimeoutDetector
RCARuleEngine = rca_detector.RCARuleEngine
IncidentSummaryGenerator = incident_summary.IncidentSummaryGenerator

# ===========================================================
# Helper: build a minimal mock requests.Response
# ===========================================================
def _make_response(json_body: dict, status_code: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_body
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ===========================================================
# Task 41 — LLMTimeoutDetector
# ===========================================================
class TestLLMTimeoutDetector(unittest.TestCase):

    def _detector(self):
        return LLMTimeoutDetector(
            prometheus_url="http://fake-prom:9090",
            opensearch_url="http://fake-os:9200",
        )

    def _prom_hit(self):
        return {"status": "success", "data": {"result": [{"value": [0, "1"]}]}}

    def _prom_empty(self):
        return {"status": "success", "data": {"result": []}}

    def _os_hit(self, n=5):
        return {"hits": {"hits": [{}] * n}}

    def _os_empty(self):
        return {"hits": {"hits": []}}

    @patch("requests.get")
    def test_severity_high_when_both_signals(self, mock_get):
        mock_get.side_effect = [_make_response(self._prom_hit()), _make_response(self._os_hit())]
        result = self._detector().detect("product-reviews", "production", "default")
        self.assertEqual(result["severity"], "high")

    @patch("requests.get")
    def test_severity_medium_metric_only(self, mock_get):
        mock_get.side_effect = [_make_response(self._prom_hit()), _make_response(self._os_empty())]
        result = self._detector().detect("product-reviews", "production", "default")
        self.assertEqual(result["severity"], "medium")

    @patch("requests.get")
    def test_severity_none_when_both_healthy_zero(self, mock_get):
        mock_get.side_effect = [_make_response(self._prom_empty()), _make_response(self._os_empty())]
        result = self._detector().detect("product-reviews", "production", "default")
        self.assertEqual(result["severity"], "none")

    @patch("requests.get")
    def test_severity_unknown_when_prom_unavailable(self, mock_get):
        mock_get.side_effect = [Exception("Connection refused"), _make_response(self._os_hit())]
        result = self._detector().detect("product-reviews", "production", "default")
        self.assertEqual(result["severity"], "unknown")

    @patch("requests.get")
    def test_evidence_preserves_all_scope_labels(self, mock_get):
        mock_get.side_effect = [_make_response(self._prom_empty()), _make_response(self._os_empty())]
        result = self._detector().detect("svc-a", "staging", "tenant-42")
        self.assertEqual(result["service"], "svc-a")
        self.assertEqual(result["environment"], "staging")
        self.assertEqual(result["tenant_id"], "tenant-42")

    @patch("requests.get")
    def test_uses_app_llm_metric_family(self, mock_get):
        mock_get.side_effect = [_make_response(self._prom_empty()), _make_response(self._os_empty())]
        result = self._detector().detect("product-reviews", "production", "default")
        self.assertIn("app_llm_errors_total", result["evidence"]["metric_query"])
        self.assertNotIn("app_llm_requests_total", result["evidence"]["metric_query"])
        self.assertEqual(result["evidence"]["log_index"], "otel-logs-*")

    @patch("requests.get")
    def test_log_query_scope_includes_environment(self, mock_get):
        mock_get.side_effect = [_make_response(self._prom_empty()), _make_response(self._os_empty())]
        result = self._detector().detect("product-reviews", "staging", "default")
        self.assertIn("staging", result["evidence"]["log_query"])


# ===========================================================
# Task 38 — RCARuleEngine
# ===========================================================
class TestRCARuleEngine(unittest.TestCase):

    def _engine(self):
        engine = RCARuleEngine()
        engine.prom_client = MagicMock()
        engine.os_client = MagicMock()
        engine.jaeger_client = MagicMock()
        return engine

    def test_no_incident_when_all_scores_zero(self):
        engine = self._engine()
        engine.prom_client.evaluate_promql.return_value = 0.0
        engine.os_client.evaluate_lucene.return_value = 0.0
        engine.jaeger_client.evaluate_trace_errors.return_value = 0.0
        ctx = engine.evaluate("product-reviews")
        self.assertFalse(ctx.is_incident)
        self.assertAlmostEqual(ctx.total_service_score, 0.0)

    def test_incident_when_all_scores_high(self):
        engine = self._engine()
        engine.prom_client.evaluate_promql.return_value = 1.0
        engine.os_client.evaluate_lucene.return_value = 1.0
        engine.jaeger_client.evaluate_trace_errors.return_value = 1.0
        ctx = engine.evaluate("product-reviews")
        self.assertTrue(ctx.is_incident)
        self.assertAlmostEqual(ctx.total_service_score, 1.0)

    def test_source_unavailable_does_not_force_incident(self):
        engine = self._engine()
        engine.prom_client.evaluate_promql.return_value = None
        engine.os_client.evaluate_lucene.return_value = None
        engine.jaeger_client.evaluate_trace_errors.return_value = None
        ctx = engine.evaluate("product-reviews")
        self.assertFalse(ctx.is_incident)
        self.assertEqual(ctx.confidence, "unknown")

    def test_partial_confidence_when_some_sources_down(self):
        engine = self._engine()
        engine.prom_client.evaluate_promql.side_effect = [1.0, None]
        engine.os_client.evaluate_lucene.return_value = 1.0
        engine.jaeger_client.evaluate_trace_errors.return_value = None
        ctx = engine.evaluate("product-reviews")
        self.assertEqual(ctx.confidence, "partial")
        self.assertEqual(ctx.sources_unavailable, 2)
        self.assertGreater(ctx.total_service_score, 0.0)

    def test_uses_app_llm_metric_not_aiops(self):
        engine = self._engine()
        engine.prom_client.evaluate_promql.return_value = 0.0
        engine.os_client.evaluate_lucene.return_value = 0.0
        engine.jaeger_client.evaluate_trace_errors.return_value = 0.0
        engine.evaluate("product-reviews")
        calls = [str(c) for c in engine.prom_client.evaluate_promql.call_args_list]
        self.assertIn("app_llm_errors_total", " ".join(calls))
        self.assertIn("traces_span_metrics_calls_total", " ".join(calls))


# ===========================================================
# Task 43 — IncidentSummaryGenerator
# ===========================================================
class TestIncidentSummaryGenerator(unittest.TestCase):

    def _base_rca_output(self, **overrides):
        base = {
            "service": "product-reviews",
            "environment": "production",
            "tenant_id": "default",
            "timestamp": "2026-07-15T09:00:00Z",
            "severity": "high",
            "metric_anomaly_score": 1.0,
            "trace_error_score": 0.0,
            "log_anomaly_score": 0.8,
            "ai_telemetry_score": 1.0,
            "total_service_score": 0.92,
            "confidence": "high",
            "is_incident": True,
            "evidence": {
                "metric_query": 'sum(...)',
                "log_query": 'resource.service.name:"product-reviews"',
                "ai_query": 'sum(rate(app_llm_errors_total...))',
                "sources_unavailable": 0,
            },
        }
        base.update(overrides)
        return base

    def test_summary_preserves_environment_and_tenant(self):
        gen = IncidentSummaryGenerator()
        output = gen.generate_summary(self._base_rca_output())
        self.assertIn("production", output)
        self.assertIn("default", output)

    def test_summary_uses_detector_query_not_hardcoded(self):
        custom_query = 'sum(rate(app_llm_errors_total[5m]))'
        data = self._base_rca_output()
        data["evidence"]["ai_query"] = custom_query
        gen = IncidentSummaryGenerator()
        output = gen.generate_summary(data)
        self.assertIn(custom_query, output)

    def test_grafana_url_is_url_encoded(self):
        gen = IncidentSummaryGenerator(grafana_base_url="http://grafana.internal")
        output = gen.generate_summary(self._base_rca_output())
        grafana_line = next(line for line in output.splitlines() if "grafana.internal/explore" in line)
        self.assertNotIn('{"query":', grafana_line)

    def test_handles_none_scores_gracefully(self):
        data = self._base_rca_output()
        data["trace_error_score"] = None
        data["evidence"]["sources_unavailable"] = 1
        gen = IncidentSummaryGenerator()
        output = gen.generate_summary(data)
        self.assertIn("N/A", output)

    def test_handles_no_evidence_case(self):
        data = self._base_rca_output(severity="none", total_service_score=0.0)
        gen = IncidentSummaryGenerator()
        output = gen.generate_summary(data)
        self.assertIn("NONE", output)

if __name__ == "__main__":
    unittest.main()
