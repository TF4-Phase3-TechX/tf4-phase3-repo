import sys
from pathlib import Path
import unittest

# Add aiops-detector/w2-prototype to python path dynamically
here = Path(__file__).resolve().parent
detector_dir = here.parents[2] / "src" / "aiops-detector" / "w2-prototype"
sys.path.append(str(detector_dir))

from incident_summary import IncidentSummaryGenerator

class TestIncidentSummaryGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = IncidentSummaryGenerator(
            grafana_base_url="http://grafana.test",
            opensearch_datasource_uid="opensearch-test-uid"
        )

    def test_generate_summary_high_confidence(self):
        input_data = {
            "service": "product-reviews",
            "environment": "production",
            "tenant_id": "test-tenant",
            "timestamp": "2026-07-16T10:00:00Z",
            "metric_anomaly_score": 0.85,
            "trace_error_score": 0.0,
            "log_anomaly_score": 0.1,
            "ai_telemetry_score": 0.9,
            "total_service_score": 0.85,
            "confidence": "high",
            "is_incident": True,
            "severity": "critical",
            "evidence": {
                "metric_query": "metric_test_query",
                "log_query": "log_test_query",
                "ai_query": "ai_test_query",
                "sources_unavailable": 0
            }
        }
        summary = self.generator.generate_summary(input_data)
        self.assertIn("Service:** `product-reviews`", summary)
        self.assertIn("Environment:** `production`", summary)
        self.assertIn("Tenant:** `test-tenant`", summary)
        self.assertIn("Severity:** `CRITICAL`", summary)
        self.assertIn("Confidence:** High — score 0.85, all sources available", summary)
        self.assertIn("metric_test_query", summary)
        self.assertIn("log_test_query", summary)
        self.assertIn("ai_test_query", summary)
        self.assertIn("0.85", summary)
        self.assertIn("http://grafana.test/explore", summary)

    def test_generate_summary_partial_confidence(self):
        input_data = {
            "service": "product-reviews",
            "environment": "production",
            "tenant_id": "test-tenant",
            "timestamp": "2026-07-16T10:00:00Z",
            "metric_anomaly_score": 0.9,
            "trace_error_score": None,
            "log_anomaly_score": 0.5,
            "ai_telemetry_score": None,
            "total_service_score": 0.7,
            "confidence": "partial",
            "is_incident": True,
            "evidence": {
                "metric_query": "metric_test_query",
                "log_query": "log_test_query",
                "ai_query": "N/A",
                "sources_unavailable": 2
            }
        }
        summary = self.generator.generate_summary(input_data)
        self.assertIn("Confidence:** Partial — score 0.70, 2 source(s) unavailable", summary)
        self.assertIn("N/A (source unavailable)", summary)

    def test_generate_summary_unknown_confidence(self):
        input_data = {
            "service": "product-reviews",
            "environment": "production",
            "tenant_id": "test-tenant",
            "total_service_score": 0.0,
            "confidence": "unknown",
            "is_incident": False,
            "evidence": {
                "sources_unavailable": 4
            }
        }
        summary = self.generator.generate_summary(input_data)
        self.assertIn("Confidence:** Unknown — all telemetry sources were unavailable during evaluation", summary)

    def test_generate_summary_missing_fields(self):
        # Test default values for empty input
        input_data = {}
        summary = self.generator.generate_summary(input_data)
        self.assertIn("unknown-service`", summary)
        self.assertIn("unknown-env`", summary)
        self.assertIn("unknown-tenant`", summary)
        self.assertIn("UNKNOWN`", summary)

    def test_generate_summary_invalid_types(self):
        input_data = {
            "metric_anomaly_score": "not-a-float", # Invalid type
            "total_service_score": "invalid-score", # Invalid type
            "evidence": {
                "sources_unavailable": "not-an-int"
            }
        }
        with self.assertRaises((ValueError, TypeError)):
            self.generator.generate_summary(input_data)
