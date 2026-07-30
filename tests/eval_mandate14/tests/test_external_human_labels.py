from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from external_quality_gate import verify_external_quality_gate

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "external-human-labels-summeval-v1.jsonl"
REPORT = ROOT / "external-human-nli-report-v1.json"
FACTUALITY_REPORT = ROOT / "external-human-factuality-report-v2.json"
REVISION = "bfc121155064afa2d81b5505682ffc0d96f4334c"


def load_labels() -> list[dict]:
    return [
        json.loads(line)
        for line in LABELS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_external_human_labels_are_balanced_pinned_and_text_free():
    labels = load_labels()

    assert len(labels) == 100
    assert len({row["case_id"] for row in labels}) == 100
    assert sum(row["human_pass"] is True for row in labels) == 50
    assert sum(row["human_pass"] is False for row in labels) == 50
    assert {row["dataset_revision"] for row in labels} == {REVISION}
    assert all(len(row["source_sha256"]) == 64 for row in labels)
    assert all(len(row["summary_sha256"]) == 64 for row in labels)
    assert all("source" not in row and "summary" not in row for row in labels)
    assert len({row["document_id"] for row in labels}) == 65
    positive = {
        row["document_id"] for row in labels if row["human_pass"]
    }
    negative = {
        row["document_id"] for row in labels if not row["human_pass"]
    }
    assert len(positive & negative) == 35


def test_external_nli_report_is_bound_to_labels_and_keeps_failed_agreement():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    expected_hash = hashlib.sha256(LABELS.read_bytes()).hexdigest()

    assert report["dataset"]["label_manifest"] == (
        "tests/eval_mandate14/external-human-labels-summeval-v1.jsonl"
    )
    assert report["dataset"]["label_manifest_sha256"] == expected_hash
    assert report["dataset"]["labeled_cases"] == 100
    assert report["dataset"]["human_pass"] == 50
    assert report["dataset"]["human_fail"] == 50
    assert report["aggregate"]["agreement"] == 0.5
    assert report["aggregate"]["cohen_kappa"] == 0.0
    assert report["aggregate"]["contradiction_negative_controls"] == 3
    assert report["aggregate"]["contradiction_negative_controls_passed"] == 3
    assert report["aggregate"]["contradiction_gate_pass"] is True


def test_external_factuality_report_passes_recorded_quality_gate():
    report = json.loads(FACTUALITY_REPORT.read_text(encoding="utf-8"))
    expected_hash = hashlib.sha256(LABELS.read_bytes()).hexdigest()

    assert report["dataset"]["label_manifest_sha256"] == expected_hash
    assert report["model"]["id"] == (
        "vectara/hallucination_evaluation_model"
    )
    assert report["model"]["revision"] == (
        "58383384656cbaec2949a75a41f20e891e90a73b"
    )
    assert report["model"]["threshold"] == 0.5
    assert report["schema_version"] == (
        "m14-external-human-factuality-report-v3"
    )
    assert report["dataset"]["labeled_summary_rows"] == 100
    assert report["dataset"]["unique_documents"] == 65
    assert report["dataset"]["documents_in_both_classes"] == 35
    for path_name in (
        "structured_claim_path",
        "response_assertion_path",
    ):
        metrics = report["aggregate"][path_name]
        assert metrics["agreement"] >= 0.70
        assert metrics["cohen_kappa"] >= 0.40
    assert report["aggregate"]["input_truncated_count"] == 0
    assert report["aggregate"][
        "contradiction_negative_controls_passed"
    ] == 3
    assert report["acceptance_gate"]["pass"] is True
    assert verify_external_quality_gate()["pass"] is True


def test_external_gate_rejects_stale_semantic_scorer_hash(tmp_path):
    report = json.loads(FACTUALITY_REPORT.read_text(encoding="utf-8"))
    report["code_binding"]["semantic_scorer_sha256"] = "0" * 64
    tampered = tmp_path / "tampered-report.json"
    tampered.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="semantic scorer"):
        verify_external_quality_gate(tampered)
