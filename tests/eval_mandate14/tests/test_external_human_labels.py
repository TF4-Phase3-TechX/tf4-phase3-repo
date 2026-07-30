from __future__ import annotations

import hashlib
import json
from pathlib import Path


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
    assert report["aggregate"]["agreement"] == 0.76
    assert report["aggregate"]["cohen_kappa"] == 0.52
    assert report["aggregate"]["confusion_matrix"] == {
        "true_positive": 36,
        "true_negative": 40,
        "false_positive": 10,
        "false_negative": 14,
    }
    assert report["aggregate"]["input_truncated_count"] == 0
    assert report["aggregate"][
        "contradiction_negative_controls_passed"
    ] == 3
    assert report["acceptance_gate"]["pass"] is True
