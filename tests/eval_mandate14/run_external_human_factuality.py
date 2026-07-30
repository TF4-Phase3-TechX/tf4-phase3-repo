#!/usr/bin/env python3
"""Calibrate the deployed semantic path on 100 SummEval expert labels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from run_eval import build_report as build_runtime_report
from run_external_human_nli import (
    CONTRADICTION_CONTROLS,
    DEFAULT_LABELS,
    REPO_ROOT,
    _cohen_kappa,
    _fetch_pairs,
    _load_labels,
    _sentences,
    _sha256,
)
from semantic_faithfulness import (
    HHEMJudge,
    MODEL_BRANCH,
    MODEL_ID,
    MODEL_MAX_LENGTH,
    MODEL_REVISION,
    MODEL_THRESHOLD,
    SEMANTIC_RETRIEVAL_TOP_K,
    build_semantic_pair,
)

MIN_AGREEMENT = 0.70
MIN_COHEN_KAPPA = 0.40
DEFAULT_REPORT = Path(__file__).with_name(
    "external-human-factuality-report-v2.json"
)


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_source(path: Path) -> str:
    """Hash UTF-8 source with canonical LF line endings."""
    source = path.read_text(encoding="utf-8")
    canonical = source.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _metrics(
    results: list[dict[str, Any]],
    prediction_field: str,
) -> dict[str, Any]:
    tp = sum(
        item["human_pass"] is True
        and item[prediction_field] is True
        for item in results
    )
    tn = sum(
        item["human_pass"] is False
        and item[prediction_field] is False
        for item in results
    )
    fp = sum(
        item["human_pass"] is False
        and item[prediction_field] is True
        for item in results
    )
    fn = sum(
        item["human_pass"] is True
        and item[prediction_field] is False
        for item in results
    )
    agreement = (tp + tn) / len(results)
    return {
        "labeled_cases": len(results),
        "agreement": agreement,
        "cohen_kappa": _cohen_kappa(tp, tn, fp, fn),
        "confusion_matrix": {
            "true_positive": tp,
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
        },
    }


def _runtime_case(item: dict[str, Any]) -> dict[str, Any]:
    """Adapt one external row to the same observation contract as runtime."""
    source_id = f"review:{item['document_id']}"
    claims = [
        {
            "text": sentence,
            "claim_type": "opinion",
            "source_ids": [source_id],
        }
        for sentence in _sentences(item["hypothesis"])
    ]
    return {
        "schema_version": "mandate14-case-v2",
        "case_id": item["case_id"],
        "surface": "review_summary",
        "variant": "external_calibration",
        "category": "grounded",
        "human_pass": item["human_pass"],
        "sources": [{
            "source_id": source_id,
            "source_type": "review",
            "text": item["premise"],
        }],
        "expected": {
            "outcome": "answer",
            "answerable": True,
            "valid_task": True,
            "facts": [],
        },
        "observed": {
            "outcome": "answered",
            "response_text": item["hypothesis"],
            "claims": claims,
            "blocked": False,
            "latency_ms": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "model_requests": 0,
            "estimated_cost_usd": 0,
        },
    }


def _scored_units(
    records: list[dict[str, Any]],
    premise: str,
) -> list[dict[str, Any]]:
    units = []
    for record in records:
        evidence, hypothesis = build_semantic_pair(
            premise,
            str(record["text"]),
        )
        units.append({
            "text_sha256": _sha256(str(record["text"])),
            "evidence_sha256": _sha256(evidence),
            "hypothesis_sha256": _sha256(hypothesis),
            "factual_consistency_score": record[
                "semantic_factuality_score"
            ],
            "factual_consistency_pass": bool(record["supported"]),
        })
    return units


def build_report(labels_path: Path, batch_size: int) -> dict[str, Any]:
    labels = _load_labels(labels_path)
    pairs = _fetch_pairs(labels)
    cases = [_runtime_case(item) for item in pairs]
    judge = HHEMJudge()
    runtime_report = build_runtime_report(
        cases,
        labels_path.read_bytes(),
        semantic_judge=judge,
    )
    semantic = runtime_report["aggregate"][
        "semantic_faithfulness_judge"
    ]

    results: list[dict[str, Any]] = []
    for item, scored in zip(
        pairs,
        runtime_report["per_case"],
        strict=True,
    ):
        structured = [
            claim
            for claim in scored["grounding"]["claims"]
            if claim["semantic_applicable"]
        ]
        response = scored["grounding"]["response_assertions"]
        structured_pass = bool(structured) and all(
            claim["supported"] for claim in structured
        )
        response_pass = bool(response) and all(
            assertion["supported"] for assertion in response
        )
        results.append({
            "case_id": item["case_id"],
            "document_id": item["document_id"],
            "summary_index": item["summary_index"],
            "source_sha256": _sha256(item["premise"]),
            "summary_sha256": _sha256(item["hypothesis"]),
            "human_pass": item["human_pass"],
            "expert_consistency_score": item[
                "expert_consistency_score"
            ],
            "structured_claim_pass": structured_pass,
            "response_assertion_pass": response_pass,
            "structured_claims": _scored_units(
                structured,
                item["premise"],
            ),
            "response_assertions": _scored_units(
                response,
                item["premise"],
            ),
        })

    structured_metrics = _metrics(results, "structured_claim_pass")
    response_metrics = _metrics(results, "response_assertion_pass")
    control_pairs = [
        build_semantic_pair(item["premise"], item["hypothesis"])
        for item in CONTRADICTION_CONTROLS
    ]
    control_scores, control_truncations = judge.score_pairs(
        control_pairs,
        batch_size=batch_size,
    )
    controls = [
        {
            "case_id": item["case_id"],
            "premise_sha256": _sha256(item["premise"]),
            "hypothesis_sha256": _sha256(item["hypothesis"]),
            "factual_consistency_score": round(score, 6),
            "negative_control_pass": score < MODEL_THRESHOLD,
        }
        for item, score in zip(
            CONTRADICTION_CONTROLS,
            control_scores,
            strict=True,
        )
    ]
    controls_pass = all(
        item["negative_control_pass"] for item in controls
    )
    truncation_count = (
        semantic["input_truncated_count"] + control_truncations
    )
    quality_gate_pass = (
        structured_metrics["agreement"] >= MIN_AGREEMENT
        and structured_metrics["cohen_kappa"] >= MIN_COHEN_KAPPA
        and response_metrics["agreement"] >= MIN_AGREEMENT
        and response_metrics["cohen_kappa"] >= MIN_COHEN_KAPPA
        and controls_pass
        and truncation_count == 0
    )

    try:
        label_manifest = labels_path.resolve().relative_to(
            REPO_ROOT
        ).as_posix()
    except ValueError:
        label_manifest = labels_path.name
    positive_documents = {
        item["document_id"] for item in results if item["human_pass"]
    }
    negative_documents = {
        item["document_id"] for item in results if not item["human_pass"]
    }
    script_dir = Path(__file__).resolve().parent

    return {
        "schema_version": "m14-external-human-factuality-report-v3",
        "dataset": {
            "id": labels[0]["dataset_id"],
            "revision": labels[0]["dataset_revision"],
            "split": labels[0]["dataset_split"],
            "label_manifest": label_manifest,
            "label_manifest_sha256": _sha256_path(labels_path),
            "labeled_summary_rows": len(results),
            "unique_documents": len(
                {item["document_id"] for item in results}
            ),
            "documents_in_both_classes": len(
                positive_documents & negative_documents
            ),
            "sample_unit": "summary_rows_clustered_by_document",
            "human_pass": sum(item["human_pass"] for item in results),
            "human_fail": sum(not item["human_pass"] for item in results),
        },
        "model": {
            "id": MODEL_ID,
            "branch": MODEL_BRANCH,
            "revision": MODEL_REVISION,
            "architecture": "DeBERTa_factual_consistency_cross_encoder",
            "max_length": MODEL_MAX_LENGTH,
            "threshold": MODEL_THRESHOLD,
            "threshold_source": "published_model_card_default",
            "pair_builder": (
                "shared_build_semantic_pair_top_"
                f"{SEMANTIC_RETRIEVAL_TOP_K}_source_sentences"
            ),
            "runtime_path": (
                "run_eval.build_report->"
                "semantic_faithfulness.apply_semantic_faithfulness"
            ),
            "decision_rule": (
                "case_pass_if_every_scored_unit_gte_0.5"
            ),
        },
        "code_binding": {
            "hash_encoding": "utf8_lf_canonical_v1",
            "semantic_scorer_sha256": sha256_source(
                script_dir / "semantic_faithfulness.py"
            ),
            "calibration_runner_sha256": sha256_source(Path(__file__)),
        },
        "acceptance_gate": {
            "minimum_agreement_per_path": MIN_AGREEMENT,
            "minimum_cohen_kappa_per_path": MIN_COHEN_KAPPA,
            "require_all_contradiction_controls": True,
            "require_zero_input_truncation": True,
            "pass": quality_gate_pass,
        },
        "aggregate": {
            "structured_claim_path": structured_metrics,
            "response_assertion_path": response_metrics,
            "input_truncated_count": truncation_count,
            "contradiction_negative_controls": len(controls),
            "contradiction_negative_controls_passed": sum(
                item["negative_control_pass"] for item in controls
            ),
            "contradiction_gate_pass": controls_pass,
        },
        "cases": results,
        "contradiction_controls": controls,
        "claim_boundary": (
            "External English news-domain offline calibration against "
            "100 published SummEval expert-labeled summary rows clustered "
            "within 65 documents. Both deployed structured-claim and "
            "user-visible response-assertion paths are measured. "
            "Deterministic citation, numeric, safety, agency, and hard-bar "
            "checks remain independent. This does not prove TF4 production "
            "quality, document-independent confidence, or hidden-set "
            "acceptance."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    report = build_report(args.labels, args.batch_size)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    aggregate = report["aggregate"]
    structured = aggregate["structured_claim_path"]
    response = aggregate["response_assertion_path"]
    print(
        f"Wrote {args.output}: "
        f"structured={structured['agreement']:.4f}/"
        f"{structured['cohen_kappa']:.4f}, "
        f"response={response['agreement']:.4f}/"
        f"{response['cohen_kappa']:.4f}, "
        f"contradiction_controls="
        f"{aggregate['contradiction_negative_controls_passed']}/"
        f"{aggregate['contradiction_negative_controls']}, "
        f"quality_gate={report['acceptance_gate']['pass']}"
    )
    return 0 if report["acceptance_gate"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
