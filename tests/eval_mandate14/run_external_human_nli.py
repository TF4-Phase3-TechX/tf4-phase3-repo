#!/usr/bin/env python3
"""Run pinned NLI faithfulness calibration against 100 SummEval human labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from fetch_summeval_human_labels import (
    DATASET_ID,
    DATASET_REVISION,
    DATASET_SPLIT,
    DEFAULT_OUTPUT as DEFAULT_LABELS,
    load_pinned_rows,
)


MODEL_ID = "cross-encoder/nli-deberta-v3-small"
MODEL_REVISION = "fa2804872c3b4bd748f38c0185cc85775361e735"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = Path(__file__).with_name("external-human-nli-report-v1.json")

CONTRADICTION_CONTROLS = (
    {
        "case_id": "M14-NLI-CONTRA-001",
        "premise": "The product battery lasts ten hours after a full charge.",
        "hypothesis": "The product battery lasts only two hours.",
    },
    {
        "case_id": "M14-NLI-CONTRA-002",
        "premise": "The watch is waterproof to a depth of ten meters.",
        "hypothesis": "The watch is not waterproof.",
    },
    {
        "case_id": "M14-NLI-CONTRA-003",
        "premise": "The available colors are red and blue only.",
        "hypothesis": "The product is available in green.",
    },
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_labels(path: Path) -> list[dict[str, Any]]:
    labels = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(labels) != 100:
        raise ValueError(f"expected 100 external labels, found {len(labels)}")
    if sum(bool(item["human_pass"]) for item in labels) != 50:
        raise ValueError("external labels must contain 50 pass and 50 fail rows")
    if any(item["dataset_revision"] != DATASET_REVISION for item in labels):
        raise ValueError("label manifest contains an unpinned dataset revision")
    return labels


def _fetch_pairs(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = load_pinned_rows()
    indexed = {int(item["row_idx"]): item["row"] for item in rows}
    pairs: list[dict[str, Any]] = []
    for label in labels:
        row = indexed[label["row_idx"]]
        source = row["text"]
        summary = row["machine_summaries"][label["summary_index"]]
        if row["id"] != label["document_id"]:
            raise ValueError(f"{label['case_id']}: document identity changed")
        if _sha256(source) != label["source_sha256"]:
            raise ValueError(f"{label['case_id']}: source hash changed")
        if _sha256(summary) != label["summary_sha256"]:
            raise ValueError(f"{label['case_id']}: summary hash changed")
        pairs.append({**label, "premise": source, "hypothesis": summary})
    return pairs


def _cohen_kappa(tp: int, tn: int, fp: int, fn: int) -> float:
    total = tp + tn + fp + fn
    agreement = (tp + tn) / total
    human_positive = (tp + fn) / total
    human_negative = (tn + fp) / total
    nli_positive = (tp + fp) / total
    nli_negative = (tn + fn) / total
    expected = human_positive * nli_positive + human_negative * nli_negative
    return (agreement - expected) / (1 - expected) if expected != 1 else 1.0


def _sentences(text: str) -> list[str]:
    sentences = [
        value.strip()
        for value in re.split(r"(?<=[.!?])\s+|\n+", text)
        if len(value.split()) >= 3
    ]
    return sentences or [text.strip()]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _retrieve_evidence(source: str, claim: str, top_k: int = 3) -> str:
    """Retrieve evidence lexically, while leaving the support decision to NLI."""
    claim_tokens = _tokens(claim)
    ranked = []
    for index, sentence in enumerate(_sentences(source)):
        sentence_tokens = _tokens(sentence)
        overlap = len(claim_tokens & sentence_tokens)
        coverage = overlap / max(len(claim_tokens), 1)
        ranked.append((coverage, overlap, -index, sentence))
    ranked.sort(reverse=True)
    selected = [item[3] for item in ranked[:top_k]]
    return " ".join(selected)


def _score_pairs(
    pairs: list[dict[str, Any]],
    *,
    batch_size: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
    )
    model.eval()
    labels = {
        str(value).lower(): int(key)
        for key, value in model.config.id2label.items()
    }
    required = {"contradiction", "entailment", "neutral"}
    if set(labels) != required:
        raise RuntimeError(f"unexpected NLI labels: {labels}")

    expanded: list[dict[str, Any]] = []
    for item_index, item in enumerate(pairs):
        claims = _sentences(item["hypothesis"])
        for claim_index, claim in enumerate(claims):
            expanded.append(
                {
                    "item_index": item_index,
                    "claim_index": claim_index,
                    "premise": _retrieve_evidence(item["premise"], claim),
                    "hypothesis": claim,
                }
            )

    claim_results: list[dict[str, Any]] = []
    truncation_count = 0
    for start in range(0, len(expanded), batch_size):
        batch = expanded[start : start + batch_size]
        full_lengths = tokenizer(
            [item["premise"] for item in batch],
            [item["hypothesis"] for item in batch],
            add_special_tokens=True,
            truncation=False,
            return_length=True,
        )["length"]
        encoded = tokenizer(
            [item["premise"] for item in batch],
            [item["hypothesis"] for item in batch],
            padding=True,
            truncation="only_first",
            max_length=512,
            return_tensors="pt",
        )
        with torch.inference_mode():
            probabilities = torch.softmax(model(**encoded).logits, dim=-1).cpu()
        for item, full_length, probability in zip(
            batch, full_lengths, probabilities, strict=True
        ):
            scores = {
                name: float(probability[index])
                for name, index in labels.items()
            }
            predicted_label = max(scores, key=scores.get)
            truncation_count += int(full_length > 512)
            claim_results.append(
                {
                    "item_index": item["item_index"],
                    "claim_index": item["claim_index"],
                    "claim_sha256": _sha256(item["hypothesis"]),
                    "evidence_sha256": _sha256(item["premise"]),
                    "nli_label": predicted_label,
                    "nli_probabilities": {
                        name: round(value, 6) for name, value in sorted(scores.items())
                    },
                    "input_truncated": full_length > 512,
                }
            )

    by_item: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for result in claim_results:
        by_item[result["item_index"]].append(result)
    results: list[dict[str, Any]] = []
    for item_index, item in enumerate(pairs):
        claims = sorted(by_item[item_index], key=lambda value: value["claim_index"])
        predicted_pass = bool(claims) and all(
            claim["nli_label"] == "entailment" for claim in claims
        )
        contradiction_dominates = any(
            claim["nli_probabilities"]["contradiction"]
            > claim["nli_probabilities"]["entailment"]
            for claim in claims
        )
        results.append(
            {
                "case_id": item["case_id"],
                "document_id": item.get("document_id"),
                "summary_index": item.get("summary_index"),
                "source_sha256": _sha256(item["premise"]),
                "summary_sha256": _sha256(item["hypothesis"]),
                "human_pass": item.get("human_pass"),
                "expert_consistency_score": item.get("expert_consistency_score"),
                "nli_label": "entailment" if predicted_pass else (
                    "contradiction" if contradiction_dominates else "neutral"
                ),
                "nli_pass": predicted_pass,
                "claim_count": len(claims),
                "claim_results": claims,
                "input_truncated": any(claim["input_truncated"] for claim in claims),
            }
        )
    return results, {"input_truncated_count": truncation_count}


def build_report(labels_path: Path, batch_size: int) -> dict[str, Any]:
    labels = _load_labels(labels_path)
    pairs = _fetch_pairs(labels)
    results, runtime = _score_pairs(pairs, batch_size=batch_size)

    tp = sum(item["human_pass"] is True and item["nli_pass"] is True for item in results)
    tn = sum(item["human_pass"] is False and item["nli_pass"] is False for item in results)
    fp = sum(item["human_pass"] is False and item["nli_pass"] is True for item in results)
    fn = sum(item["human_pass"] is True and item["nli_pass"] is False for item in results)
    agreement = (tp + tn) / len(results)
    kappa = _cohen_kappa(tp, tn, fp, fn)

    controls = [dict(item) for item in CONTRADICTION_CONTROLS]
    control_results, _ = _score_pairs(controls, batch_size=batch_size)
    def control_passed(item: dict[str, Any]) -> bool:
        return item["nli_pass"] is False and any(
            claim["nli_probabilities"]["contradiction"]
            > claim["nli_probabilities"]["entailment"]
            for claim in item["claim_results"]
        )

    contradiction_pass = all(control_passed(item) for item in control_results)
    for item in control_results:
        item.pop("human_pass", None)
        item.pop("expert_consistency_score", None)
        item["negative_control_pass"] = control_passed(item)

    try:
        label_manifest = labels_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        # Keep committed reports machine-independent even when a caller supplies
        # a label file outside the repository.
        label_manifest = labels_path.name

    return {
        "schema_version": "m14-external-human-nli-report-v1",
        "dataset": {
            "id": DATASET_ID,
            "revision": DATASET_REVISION,
            "split": DATASET_SPLIT,
            "label_manifest": label_manifest,
            "label_manifest_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
            "labeled_cases": len(results),
            "human_pass": 50,
            "human_fail": 50,
        },
        "model": {
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "max_length": 512,
            "retrieval": "top_3_source_sentences_by_claim_token_coverage",
            "decision_rule": "nli_pass_if_every_summary_sentence_argmax_is_entailment",
        },
        "aggregate": {
            "agreement": agreement,
            "cohen_kappa": kappa,
            "confusion_matrix": {
                "true_positive": tp,
                "true_negative": tn,
                "false_positive": fp,
                "false_negative": fn,
            },
            **runtime,
            "contradiction_negative_controls": len(control_results),
            "contradiction_negative_controls_passed": sum(
                item["negative_control_pass"] for item in control_results
            ),
            "contradiction_gate_pass": contradiction_pass,
        },
        "cases": results,
        "contradiction_controls": control_results,
        "claim_boundary": (
            "External English news-domain calibration against published SummEval expert "
            "consistency labels. It does not replace TF4-domain labels, prove production "
            "quality, or make NLI a causal judge."
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
        f"{aggregate['contradiction_negative_controls']}"
    )
    return 0 if aggregate["contradiction_gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
