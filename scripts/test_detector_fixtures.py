"""Deterministic detector fixture tests for TF4AIO-40.

Run:
  python scripts/test_detector_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from detector_probe import build_payload, classify_prometheus_response, PROMETHEUS_DEFAULT_URL


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "aio01" / "evidence" / "detector-output-schema-v1.json"
FIXTURE_DIR = ROOT / "scripts" / "fixtures" / "detector"


class DetectorFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(cls.schema)

    def assert_payload_valid(self, payload: dict) -> None:
        errors = sorted(self.validator.iter_errors(payload), key=lambda err: list(err.path))
        if errors:
            messages = [f"{'.'.join(str(p) for p in err.path) or '<root>'}: {err.message}" for err in errors]
            self.fail("Schema validation failed:\n" + "\n".join(messages))

    def test_prometheus_up_success(self) -> None:
        response = (FIXTURE_DIR / "prometheus_up_success.json").read_text(encoding="utf-8")
        classification = classify_prometheus_response(response)
        payload = build_payload(
            classification,
            timestamp="2026-07-16T07:30:00Z",
            detection_id="prometheus-up-probe-v1-2026-07-16T07:30:00Z",
            service="prometheus",
            environment="techx-observability",
            prometheus_url=PROMETHEUS_DEFAULT_URL,
        )
        self.assertEqual(classification.outcome, "prometheus_probe_ok")
        self.assertEqual(classification.severity, "info")
        self.assert_payload_valid(payload)

    def test_prometheus_success_empty_result(self) -> None:
        response = (FIXTURE_DIR / "prometheus_success_empty.json").read_text(encoding="utf-8")
        classification = classify_prometheus_response(response)
        payload = build_payload(
            classification,
            timestamp="2026-07-16T07:31:00Z",
            detection_id="prometheus-up-probe-v1-2026-07-16T07:31:00Z",
            service="prometheus",
            environment="techx-observability",
            prometheus_url=PROMETHEUS_DEFAULT_URL,
        )
        self.assertEqual(classification.outcome, "prometheus_probe_empty")
        self.assertEqual(classification.severity, "warning")
        self.assert_payload_valid(payload)

    def test_prometheus_http_or_error_response(self) -> None:
        response = (FIXTURE_DIR / "prometheus_http_error.txt").read_text(encoding="utf-8")
        classification = classify_prometheus_response(response)
        payload = build_payload(
            classification,
            timestamp="2026-07-16T07:32:00Z",
            detection_id="prometheus-up-probe-v1-2026-07-16T07:32:00Z",
            service="prometheus",
            environment="techx-observability",
            prometheus_url=PROMETHEUS_DEFAULT_URL,
        )
        self.assertEqual(classification.outcome, "prometheus_probe_error")
        self.assertEqual(classification.severity, "critical")
        self.assert_payload_valid(payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)