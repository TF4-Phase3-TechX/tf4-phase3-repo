"""Reproducible seed sensitivity check for the Mandate 7a detector.

This is deliberately a labelled design fixture, not production evidence. It
checks that modest parameter changes do not turn stable/noisy series into
incidents and that both acute and gradual degradations remain detectable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from app.config import Settings
from app.detection import signal_gate


@dataclass(frozen=True)
class Case:
    name: str
    points: tuple[float, ...]
    floor: float
    anomalous: bool
    purpose: str


CASES = (
    Case("flat-normal", (100,) * 12, 1000, False, "steady low latency"),
    Case(
        "busy-stable",
        (990, 1000, 1010, 995, 1005, 1000, 990, 1010, 1020),
        900,
        False,
        "busy service above the safety floor without degradation",
    ),
    Case(
        "oscillating-noise",
        (100, 120, 90, 125, 85, 115, 95, 110, 105),
        1000,
        False,
        "non-monotonic noise must not look like a drain",
    ),
    Case(
        "acute-spike",
        (100, 102, 98, 101, 99, 103, 1750, 1800),
        1000,
        True,
        "sudden user-visible degradation",
    ),
    Case(
        "masked-incident",
        (100, 101, 99, 100, 5000, 102, 98, 155, 160),
        150,
        True,
        "historical noise must not mask a separate incident",
    ),
    Case(
        "borderline-ratio-no-corroboration",
        (100, 130, 80, 120, 90, 136, 100, 142),
        130,
        False,
        "a noisy 1.34x boundary shift is below the selected ratio seed",
    ),
    Case(
        "gradual-drift",
        (400, 400, 400, 400, 400, 400, 400, 400, 430, 490, 550, 610, 680, 750),
        1000,
        True,
        "slow degradation in the early-warning zone must fire before the absolute floor",
    ),
    Case(
        "moderate-gradual-drift",
        (500, 500, 500, 500, 500, 500, 500, 500, 530, 570, 610, 650, 690, 720),
        1000,
        True,
        "the selected trend seed catches a moderate monotonic rise",
    ),
    Case(
        "stable-error-rate",
        (0.06, 0.061, 0.059, 0.06, 0.062, 0.06, 0.061, 0.06),
        0.05,
        False,
        "stable high load is not itself an anomaly",
    ),
    Case(
        "gradual-error-rate",
        (0.02,) * 8 + (0.022, 0.025, 0.028, 0.031, 0.034, 0.038),
        0.05,
        True,
        "slow error-budget degradation below the safety floor",
    ),
)


def load_cases(path: Path) -> tuple[tuple[Case, ...], dict[str, object]]:
    """Load labelled replay cases collected from Prometheus or another source."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("calibration dataset must contain a non-empty cases list")
    cases = []
    for raw in raw_cases:
        points = raw.get("points", [])
        if not isinstance(points, list) or not points:
            raise ValueError(f"case {raw.get('name', '<unnamed>')} has no points")
        cases.append(
            Case(
                name=str(raw["name"]),
                points=tuple(float(point) for point in points),
                floor=float(raw["floor"]),
                anomalous=bool(raw["anomalous"]),
                purpose=str(raw.get("purpose", "labelled replay window")),
            )
        )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    source = payload.get("source", {})
    if not isinstance(source, dict):
        source = {}
    source = {**source, "dataset_canonical_sha256": hashlib.sha256(canonical).hexdigest()}
    metadata = {
        "scope": str(payload.get("scope", "labelled external replay dataset")),
        "source": source,
    }
    return tuple(cases), metadata


def evaluate(
    settings: Settings,
    cases: tuple[Case, ...] = CASES,
    *,
    replay_all_points: bool = False,
) -> dict[str, object]:
    rows = []
    tp = fp = tn = fn = 0
    for case in cases:
        first_detection_index = None
        if replay_all_points:
            streak = 0
            predicted = False
            coverage = "unavailable"
            scores = {}
            for end in range(1, len(case.points) + 1):
                start = max(0, end - settings.lookback_minutes)
                breached, coverage, scores = signal_gate(
                    list(case.points[start:end]),
                    case.floor,
                    settings,
                    include_isolation=False,
                )
                streak = streak + 1 if breached else 0
                if streak >= settings.sustained_polls:
                    predicted = True
                    first_detection_index = end - 1
                    break
        else:
            predicted, coverage, scores = signal_gate(
                list(case.points), case.floor, settings, include_isolation=False
            )
        if predicted and case.anomalous:
            tp += 1
        elif predicted:
            fp += 1
        elif case.anomalous:
            fn += 1
        else:
            tn += 1
        rows.append(
            {
                "case": case.name,
                "expected": case.anomalous,
                "predicted": predicted,
                "coverage": coverage,
                "mode": "slow-drift" if scores["slow_drift"] else "acute-or-healthy",
                "ratio": round(scores["ratio"], 4),
                "trend": round(scores["trend"], 4),
                "first_detection_index": first_detection_index,
                "purpose": case.purpose,
            }
        )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "cases": rows,
    }


def candidates(base: Settings):
    for alpha in (0.2, 0.35, 0.5):
        for ratio in (1.3, 1.5, 1.8):
            for trend in (0.2, 0.25, 0.35):
                for floor_ratio in (0.6, 0.7, 0.8):
                    yield replace(
                        base,
                        ewma_alpha=alpha,
                        ratio_threshold=ratio,
                        trend_min_relative_change=trend,
                        trend_min_floor_ratio=floor_ratio,
                    )


def render_report(payload: dict[str, object]) -> str:
    seed = payload["seed"]
    production_dataset = bool(payload.get("production_dataset"))
    source = payload.get("source", {})
    lines = [
        "# Mandate 7a detector calibration replay",
        "",
        f"Generated by `python -m benchmark.calibrate_detection`. Scope: **{payload['scope']}**.",
        "",
        (
            "This is production-informed replay evidence. It becomes production precision/recall evidence only when every normal/incident label and incident boundary has been independently validated."
            if production_dataset
            else "This is a labelled design fixture, **not production precision/recall evidence**. Production-window calibration remains an activation gate."
        ),
        "",
        "## Seed result",
        "",
        f"- Cases: {payload['case_count']}",
        f"- TP/FP/TN/FN: {seed['tp']}/{seed['fp']}/{seed['tn']}/{seed['fn']}",
        f"- Precision/recall/F1 on this fixture: {seed['precision']}/{seed['recall']}/{seed['f1']}",
        f"- Grid candidates checked: {len(payload['grid'])}",
        f"- Replay mode: {'rolling 30-sample windows with sustained-poll confirmation' if production_dataset else 'final point per design fixture'}",
        *(
            [
                f"- Namespace: `{source.get('namespace', 'not recorded')}`",
                f"- Canonical dataset SHA-256: `{source.get('dataset_canonical_sha256', 'not recorded')}`",
            ]
            if production_dataset and isinstance(source, dict)
            else []
        ),
        "",
        "| Case | Expected | Predicted | First detection sample | Mode | Ratio | Trend | Purpose |",
        "|---|---:|---:|---:|---|---:|---:|---|",
    ]
    for row in seed["cases"]:
        lines.append(
            f"| {row['case']} | {row['expected']} | {row['predicted']} | {row['first_detection_index']} | {row['mode']} | "
            f"{row['ratio']} | {row['trend']} | {row['purpose']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The grid is a sensitivity check: it makes parameter selection reproducible and exposes which knobs change outcomes. A production-derived dataset reduces reliance on engineering judgement, but does not prove optimality outside the captured and labelled windows.",
            "",
            "Isolation Forest is intentionally excluded from the firing gate. Its configurable contribution is limited to confidence/audit evidence, so an opaque unsupervised classification cannot create an incident by itself.",
            "",
            "## Production activation gate",
            "",
            (
                "This replay provides an initial seed from existing TF4 traffic. Mandate 7b must add independently validated labels, LLM/provider windows, broader non-overlapping normal windows, controlled incident drills and alert-delivery/lead-time evidence before production-accuracy claims or live remediation approval."
                if production_dataset
                else "Re-run the same evaluation over labelled TF4 normal, load-test and injected-incident windows; compare false-positive rate, recall and detection lead time; then update Helm values through review. Until that evidence exists, these values remain conservative design seeds."
            ),
            "",
        ]
    )
    if production_dataset:
        floor_sensitivity = {}
        for candidate in payload["grid"]:
            floor_ratio = candidate["settings"]["trend_min_floor_ratio"]
            result = candidate["result"]
            previous = floor_sensitivity.get(floor_ratio)
            if previous is None or result["f1"] > previous["f1"]:
                floor_sensitivity[floor_ratio] = result
        lines.extend(
            [
                "## Early-warning boundary sensitivity",
                "",
                "The selected 0.70 seed is the only tested SLO-proximity boundary that retained every labelled incident signal without paging on a labelled normal latency ramp. This is evidence for the initial seed, not proof that 0.70 generalises to unseen traffic.",
                "",
                "| Minimum current/SLO ratio | Best precision | Best recall | Best F1 | FP | FN |",
                "|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for floor_ratio, result in sorted(floor_sensitivity.items()):
            lines.append(
                f"| {floor_ratio} | {result['precision']} | {result['recall']} | {result['f1']} | {result['fp']} | {result['fn']} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--dataset",
        type=Path,
        help="Labelled replay dataset; omit to use the built-in design fixture",
    )
    args = parser.parse_args()

    base = Settings()
    cases = CASES
    metadata: dict[str, object] = {
        "scope": "labelled synthetic design fixture; not production evidence",
        "source": {},
    }
    if args.dataset:
        cases, metadata = load_cases(args.dataset)
    source = metadata["source"] if isinstance(metadata["source"], dict) else {}
    production_dataset = source.get("kind") == "prometheus_query_range"
    seed = evaluate(base, cases, replay_all_points=production_dataset)
    grid = []
    for candidate in candidates(base):
        result = evaluate(
            candidate, cases, replay_all_points=production_dataset
        )
        grid.append(
            {
                "settings": {
                    "ewma_alpha": candidate.ewma_alpha,
                    "ratio_threshold": candidate.ratio_threshold,
                    "trend_min_relative_change": candidate.trend_min_relative_change,
                    "trend_min_floor_ratio": candidate.trend_min_floor_ratio,
                },
                "result": {key: result[key] for key in ("tp", "fp", "tn", "fn", "precision", "recall", "f1")},
            }
        )
    payload = {
        "scope": metadata["scope"],
        "source": source,
        "production_dataset": production_dataset,
        "case_count": len(cases),
        "seed_settings": {
            key: value
            for key, value in asdict(base).items()
            if key
            in {
                "baseline_mad_multiplier",
                "baseline_relative_band",
                "zscore_threshold",
                "ratio_threshold",
                "ewma_alpha",
                "ewma_threshold",
                "trend_window",
                "trend_min_relative_change",
                "trend_min_current_ratio",
                "trend_min_consistency",
                "trend_min_floor_ratio",
                "isolation_contamination",
                "isolation_confidence_weight",
            }
        },
        "seed": seed,
        "grid": grid,
    }
    rendered = render_report(payload)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    if not args.json and not args.report:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
