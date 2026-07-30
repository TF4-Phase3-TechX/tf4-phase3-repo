"""Fail-closed verification for the committed external-human calibration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fetch_summeval_human_labels import DATASET_REVISION
from run_external_human_factuality import (
    DEFAULT_REPORT,
    MIN_AGREEMENT,
    MIN_COHEN_KAPPA,
    sha256_source,
)
from run_external_human_nli import DEFAULT_LABELS
from semantic_faithfulness import (
    MODEL_BRANCH,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_THRESHOLD,
)

SCRIPT_DIR = Path(__file__).resolve().parent


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"external calibration gate failed: {message}")


def verify_external_quality_gate(
    report_path: Path = DEFAULT_REPORT,
    labels_path: Path = DEFAULT_LABELS,
) -> dict[str, Any]:
    """Verify freshness, provenance, and every external quality threshold."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    dataset = report["dataset"]
    model = report["model"]
    binding = report["code_binding"]
    aggregate = report["aggregate"]

    _require(
        report["schema_version"]
        == "m14-external-human-factuality-report-v3",
        "unexpected report schema",
    )
    _require(
        dataset["revision"] == DATASET_REVISION,
        "dataset revision is not pinned",
    )
    _require(
        dataset["label_manifest_sha256"] == _sha256_path(labels_path),
        "label manifest hash is stale",
    )
    _require(
        dataset["labeled_summary_rows"] == 100,
        "expected 100 expert-labeled summary rows",
    )
    _require(
        (model["id"], model["branch"], model["revision"], model["threshold"])
        == (MODEL_ID, MODEL_BRANCH, MODEL_REVISION, MODEL_THRESHOLD),
        "model artifact or decision threshold changed",
    )
    _require(
        binding["hash_encoding"] == "utf8_lf_canonical_v1",
        "unexpected source hash encoding",
    )
    _require(
        binding["semantic_scorer_sha256"]
        == sha256_source(SCRIPT_DIR / "semantic_faithfulness.py"),
        "semantic scorer/preprocessor hash is stale",
    )
    _require(
        binding["calibration_runner_sha256"]
        == sha256_source(
            SCRIPT_DIR / "run_external_human_factuality.py"
        ),
        "calibration runtime adapter hash is stale",
    )

    for path_name in (
        "structured_claim_path",
        "response_assertion_path",
    ):
        metrics = aggregate[path_name]
        _require(
            metrics["labeled_cases"] == 100,
            f"{path_name} did not score all labels",
        )
        _require(
            metrics["agreement"] >= MIN_AGREEMENT,
            f"{path_name} agreement below {MIN_AGREEMENT}",
        )
        _require(
            metrics["cohen_kappa"] >= MIN_COHEN_KAPPA,
            f"{path_name} kappa below {MIN_COHEN_KAPPA}",
        )
    _require(
        aggregate["contradiction_negative_controls_passed"]
        == aggregate["contradiction_negative_controls"]
        and aggregate["contradiction_negative_controls"] > 0,
        "contradiction controls did not all pass",
    )
    _require(
        aggregate["input_truncated_count"] == 0,
        "calibration input truncation detected",
    )
    _require(
        report["acceptance_gate"]["pass"] is True,
        "recorded acceptance gate is not green",
    )

    return {
        "schema_version": report["schema_version"],
        "report_sha256": _sha256_path(report_path),
        "label_manifest_sha256": _sha256_path(labels_path),
        "dataset_revision": dataset["revision"],
        "model": {
            "id": model["id"],
            "branch": model["branch"],
            "revision": model["revision"],
            "threshold": model["threshold"],
        },
        "code_binding": binding,
        "structured_claim_path": aggregate["structured_claim_path"],
        "response_assertion_path": aggregate[
            "response_assertion_path"
        ],
        "input_truncated_count": aggregate["input_truncated_count"],
        "contradiction_negative_controls_passed": aggregate[
            "contradiction_negative_controls_passed"
        ],
        "contradiction_negative_controls": aggregate[
            "contradiction_negative_controls"
        ],
        "pass": True,
    }
