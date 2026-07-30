#!/usr/bin/env python3
"""Run a pinned factual-consistency judge against 100 SummEval expert labels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from semantic_faithfulness import (
    HHEMJudge,
    MODEL_BRANCH,
    MODEL_ID,
    MODEL_MAX_LENGTH,
    MODEL_REVISION,
    MODEL_THRESHOLD,
)

from run_external_human_nli import (
    CONTRADICTION_CONTROLS,
    DEFAULT_LABELS,
    REPO_ROOT,
    _cohen_kappa,
    _fetch_pairs,
    _load_labels,
    _sentences,
    _sha256,
    _tokens,
)


RETRIEVAL_TOP_K = 2
MIN_AGREEMENT = 0.70
MIN_COHEN_KAPPA = 0.40
DEFAULT_REPORT = Path(__file__).with_name(
    "external-human-factuality-report-v2.json"
)


def _retrieve_summary_evidence(source: str, summary: str) -> str:
    """Return a source-ordered union of the top evidence for every claim.

    Lexical overlap is used only to fit relevant evidence into the model
    context. It never decides support; HHEM makes the support decision.
    """
    source_sentences = _sentences(source)
    selected_indexes: set[int] = set()
    for claim in _sentences(summary):
        claim_tokens = _tokens(claim)
        ranked: list[tuple[float, int, int, int]] = []
        for index, sentence in enumerate(source_sentences):
            sentence_tokens = _tokens(sentence)
            overlap = len(claim_tokens & sentence_tokens)
            coverage = overlap / max(len(claim_tokens), 1)
            ranked.append((coverage, overlap, -index, index))
        ranked.sort(reverse=True)
        selected_indexes.update(
            item[3] for item in ranked[:RETRIEVAL_TOP_K]
        )
    return " ".join(
        source_sentences[index] for index in sorted(selected_indexes)
    )


def _score_text_pairs(
    pairs: list[tuple[str, str]],
    *,
    batch_size: int,
    judge: HHEMJudge,
) -> tuple[list[float], int]:
    return judge.score_pairs(pairs, batch_size=batch_size)


def _metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(
        item["human_pass"] is True
        and item["factual_consistency_pass"] is True
        for item in results
    )
    tn = sum(
        item["human_pass"] is False
        and item["factual_consistency_pass"] is False
        for item in results
    )
    fp = sum(
        item["human_pass"] is False
        and item["factual_consistency_pass"] is True
        for item in results
    )
    fn = sum(
        item["human_pass"] is True
        and item["factual_consistency_pass"] is False
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


def build_report(labels_path: Path, batch_size: int) -> dict[str, Any]:
    labels = _load_labels(labels_path)
    pairs = _fetch_pairs(labels)
    judge = HHEMJudge()
    evidence = [
        _retrieve_summary_evidence(item["premise"], item["hypothesis"])
        for item in pairs
    ]
    scores, truncation_count = _score_text_pairs(
        [
            (item_evidence, item["hypothesis"])
            for item, item_evidence in zip(pairs, evidence, strict=True)
        ],
        batch_size=batch_size,
        judge=judge,
    )

    results = []
    for item, item_evidence, score in zip(
        pairs, evidence, scores, strict=True
    ):
        results.append(
            {
                "case_id": item["case_id"],
                "document_id": item["document_id"],
                "summary_index": item["summary_index"],
                "source_sha256": _sha256(item["premise"]),
                "summary_sha256": _sha256(item["hypothesis"]),
                "evidence_sha256": _sha256(item_evidence),
                "human_pass": item["human_pass"],
                "expert_consistency_score": item[
                    "expert_consistency_score"
                ],
                "factual_consistency_score": round(score, 6),
                "factual_consistency_pass": score >= MODEL_THRESHOLD,
            }
        )

    aggregate = _metrics(results)
    control_pairs = [
        (item["premise"], item["hypothesis"])
        for item in CONTRADICTION_CONTROLS
    ]
    control_scores, control_truncations = _score_text_pairs(
        control_pairs,
        batch_size=batch_size,
        judge=judge,
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
            CONTRADICTION_CONTROLS, control_scores, strict=True
        )
    ]
    controls_pass = all(
        item["negative_control_pass"] for item in controls
    )
    quality_gate_pass = (
        aggregate["agreement"] >= MIN_AGREEMENT
        and aggregate["cohen_kappa"] >= MIN_COHEN_KAPPA
        and controls_pass
        and truncation_count == 0
        and control_truncations == 0
    )

    try:
        label_manifest = labels_path.resolve().relative_to(
            REPO_ROOT
        ).as_posix()
    except ValueError:
        label_manifest = labels_path.name

    return {
        "schema_version": "m14-external-human-factuality-report-v2",
        "dataset": {
            "id": labels[0]["dataset_id"],
            "revision": labels[0]["dataset_revision"],
            "split": labels[0]["dataset_split"],
            "label_manifest": label_manifest,
            "label_manifest_sha256": hashlib.sha256(
                labels_path.read_bytes()
            ).hexdigest(),
            "labeled_cases": len(results),
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
            "retrieval": (
                "source_ordered_union_of_top_2_source_sentences_per_"
                "summary_claim_by_token_coverage"
            ),
            "decision_rule": (
                "pass_if_sigmoid_factual_consistency_score_gte_0.5"
            ),
        },
        "acceptance_gate": {
            "minimum_agreement": MIN_AGREEMENT,
            "minimum_cohen_kappa": MIN_COHEN_KAPPA,
            "require_all_contradiction_controls": True,
            "require_zero_input_truncation": True,
            "pass": quality_gate_pass,
        },
        "aggregate": {
            **aggregate,
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
            "published SummEval expert consistency labels. The accepted "
            "candidate replaces keyword overlap only for semantic "
            "faithfulness evaluation; deterministic citation, numeric, "
            "safety, agency, and hard-bar checks remain independent. This "
            "does not prove TF4 production quality or hidden-set acceptance."
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
    print(
        f"Wrote {args.output}: agreement={aggregate['agreement']:.4f}, "
        f"kappa={aggregate['cohen_kappa']:.4f}, "
        f"contradiction_controls="
        f"{aggregate['contradiction_negative_controls_passed']}/"
        f"{aggregate['contradiction_negative_controls']}, "
        f"quality_gate={report['acceptance_gate']['pass']}"
    )
    return 0 if report["acceptance_gate"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
