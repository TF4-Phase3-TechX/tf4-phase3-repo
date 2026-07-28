import json
from pathlib import Path

import pytest

from benchmark.rca_replay import load_jsonl, main, run_case
from benchmark.rca_schema import RCASchemaError, split_engine_and_labels, validate_case
from app.rca_engine import RCAEngine


REPO_ROOT = Path(__file__).resolve().parents[4]
SCENARIOS = REPO_ROOT / "docs" / "aio1" / "mandate-26" / "rca-labeled-scenarios-v1.jsonl"


def test_schema_validation_and_label_isolation():
    cases = load_jsonl(SCENARIOS)
    case = validate_case(cases[0], index=1)
    engine_input, labels = split_engine_and_labels(case)
    assert "labels" not in engine_input
    assert labels is not None
    assert "expected_root_service" in labels
    # Engine payload must not carry evaluation fields
    dumped = json.dumps(engine_input)
    assert "expected_root_service" not in dumped
    assert "correlated_noise_services" not in dumped


def test_labels_never_passed_to_engine(monkeypatch):
    cases = load_jsonl(SCENARIOS)
    case = validate_case(cases[0], index=1)
    captured = []

    original = RCAEngine.analyze

    def wrapped(self, engine_input):
        # engine_input is RCAEngineInput dataclass, not labels
        assert not hasattr(engine_input, "labels")
        payload = {
            "observations": [o.service for o in engine_input.observations],
        }
        captured.append(payload)
        return original(self, engine_input)

    monkeypatch.setattr(RCAEngine, "analyze", wrapped)
    result = run_case(case, RCAEngine())
    assert result["passed"] is True
    assert captured


def test_committed_suite_passes(tmp_path):
    out = tmp_path / "report.json"
    code = main(
        [
            str(SCENARIOS),
            "--output",
            str(out),
            "--force",
        ]
    )
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["schema_name"] == "techx.aiops.rca.report"
    assert report["aggregate"]["labeled_failed"] == 0
    assert report["aggregate"]["root_at_1"] == 1.0
    assert report["input_sha256"]
    assert report["git_revision"]


def test_unlabeled_case_does_not_fail(tmp_path):
    path = tmp_path / "unlabeled.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_name": "techx.aiops.rca",
                "schema_version": 1,
                "id": "unlabeled-1",
                "mode": "attribution_snapshot",
                "observations": [
                    {
                        "service": "payment",
                        "signals": [
                            {
                                "signal": "error",
                                "anomalous": True,
                                "confidence": 0.9,
                                "observed_at": "2026-07-20T10:00:00Z",
                                "first_anomalous_at": "2026-07-20T10:00:00Z",
                            }
                        ],
                    },
                    {
                        "service": "checkout",
                        "signals": [
                            {
                                "signal": "error",
                                "anomalous": True,
                                "confidence": 0.8,
                                "observed_at": "2026-07-20T10:00:10Z",
                                "first_anomalous_at": "2026-07-20T10:00:10Z",
                            }
                        ],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    code = main([str(path), "--output", str(out), "--force"])
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["cases"][0]["suspected_root_service"] == "payment"
    assert report["cases"][0]["evaluation"] is None


def test_bad_schema_exit_2(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"schema_name":"wrong","id":"x"}\n', encoding="utf-8")
    out = tmp_path / "out.json"
    code = main([str(path), "--output", str(out), "--force"])
    assert code == 2


def test_schema_rejects_timestamp_order_and_out_of_range_confidence():
    case = {
        "schema_name": "techx.aiops.rca",
        "schema_version": 1,
        "id": "bad-order",
        "mode": "attribution_snapshot",
        "observations": [
            {
                "service": "checkout",
                "signals": [
                    {
                        "signal": "error",
                        "anomalous": True,
                        "confidence": 1.1,
                        "observed_at": "2026-07-20T10:00:00Z",
                        "first_anomalous_at": "2026-07-20T10:00:01Z",
                    }
                ],
            }
        ],
    }
    with pytest.raises(RCASchemaError):
        validate_case(case, index=1)


def test_schema_rejects_duplicate_services_after_canonicalization():
    case = {
        "schema_name": "techx.aiops.rca",
        "schema_version": 1,
        "id": "duplicate-alias",
        "mode": "attribution_snapshot",
        "observations": [
            {
                "service": service,
                "signals": [
                    {
                        "signal": "error",
                        "anomalous": True,
                        "confidence": 0.9,
                        "observed_at": "2026-07-20T10:00:00Z",
                    }
                ],
            }
            for service in ("frontend-web", "frontend")
        ],
    }
    with pytest.raises(RCASchemaError, match="duplicate observation service"):
        validate_case(case, index=1)


def test_end_to_end_series_schema_requires_aligned_timestamped_points():
    case = {
        "schema_name": "techx.aiops.rca",
        "schema_version": 1,
        "id": "e2e",
        "mode": "end_to_end_series",
        "observations": [
            {
                "service": service,
                "signals": [
                    {
                        "signal": "latency",
                        "incident_start_index": 1,
                        "series": [
                            {"timestamp": "2026-07-20T10:00:00Z", "value": 10},
                            {"timestamp": second, "value": 1000},
                        ],
                    }
                ],
            }
            for service, second in (
                ("checkout", "2026-07-20T10:00:45Z"),
                ("frontend", "2026-07-20T10:01:30Z"),
            )
        ],
    }
    with pytest.raises(RCASchemaError, match="timestamp-aligned"):
        validate_case(case, index=1)


def test_expected_root_label_is_normalized_only_in_evaluator():
    case = {
        "schema_name": "techx.aiops.rca",
        "schema_version": 1,
        "id": "alias-label",
        "mode": "attribution_snapshot",
        "service_aliases": {"billing-api": "payment"},
        "observations": [
            {
                "service": "billing-api",
                "signals": [
                    {
                        "signal": "error",
                        "anomalous": True,
                        "confidence": 0.9,
                        "observed_at": "2026-07-20T10:00:00Z",
                    }
                ],
            },
            {
                "service": "checkout",
                "signals": [
                    {
                        "signal": "error",
                        "anomalous": True,
                        "confidence": 0.8,
                        "observed_at": "2026-07-20T10:00:10Z",
                    }
                ],
            },
        ],
        "labels": {"expected_root_service": "billing-api"},
    }
    validated = validate_case(case, index=1)
    engine_input, labels = split_engine_and_labels(validated)
    assert "expected_root_service" not in json.dumps(engine_input)
    assert labels["expected_root_service"] == "billing-api"
    result = run_case(validated, RCAEngine())
    assert result["evaluation"]["expected_root_service"] == "payment"
    assert result["evaluation"]["root_at_1"] is True
