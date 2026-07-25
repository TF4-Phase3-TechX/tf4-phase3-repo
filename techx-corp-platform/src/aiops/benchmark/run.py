from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .rcaeval import RCAEvalArchive, metric_windows, stratified_sample
from .scoring import rank_services


def _metrics(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    if not rows:
        return {"cases": 0, "top1": 0.0, "top3": 0.0, "mrr": 0.0}
    ranks = [row["rank"] for row in rows]
    return {
        "cases": len(rows),
        "top1": round(sum(rank == 1 for rank in ranks) / len(ranks), 4),
        "top3": round(sum(rank <= 3 for rank in ranks) / len(ranks), 4),
        "mrr": round(sum(1 / rank for rank in ranks) / len(ranks), 4),
    }


def benchmark(
    dataset: Path,
    *,
    max_cases: int | None,
    seed: int,
    baseline_seconds: int,
    incident_seconds: int,
    guard_seconds: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    with RCAEvalArchive(dataset) as archive:
        all_labels = archive.labels()
        labels = stratified_sample(all_labels, max_cases, seed)
        seen: set[str] = set()
        for index, (label, injection_time, metrics) in enumerate(archive.iter_cases(labels), 1):
            try:
                seen.add(label.name)
                windows = list(
                    metric_windows(
                        metrics,
                        injection_time,
                        baseline_seconds=baseline_seconds,
                        incident_seconds=incident_seconds,
                        guard_seconds=guard_seconds,
                    )
                )
                ranking = rank_services(windows)
                services = [candidate.service for candidate in ranking]
                rank = services.index(label.service) + 1 if label.service in services else len(services) + 1
                rows.append(
                    {
                        "case": label.name,
                        "system": label.system,
                        "fault": label.fault,
                        "ground_truth_service": label.service,
                        "rank": rank,
                        "candidate_count": len(ranking),
                        "top_candidates": [candidate.as_dict() for candidate in ranking[:5]],
                    }
                )
                print(
                    f"[{index}/{len(labels)}] {label.name}: rank={rank} "
                    f"top1={services[0] if services else 'none'}",
                    flush=True,
                )
            except Exception as exc:  # keep the benchmark auditable across imperfect cases
                failures.append({"case": label.name, "error": f"{type(exc).__name__}: {exc}"})
                print(f"[{index}/{len(labels)}] {label.name}: ERROR {exc}", flush=True)
        for label in labels:
            if label.name not in seen:
                failures.append({"case": label.name, "error": "case payload was not found in the archive stream"})
    by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_fault: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_system[row["system"]].append(row)
        by_fault[row["fault"]].append(row)
    return {
        "benchmark": "RCAEval-v2 offline service-localization",
        "algorithm": "TF4 BARO-lite deterministic baseline-vs-incident scorer",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "name": dataset.name,
            "size_bytes": dataset.stat().st_size,
            "available_cases": len(all_labels),
            "selected_cases": len(labels),
            "selection": "deterministic round-robin stratified by system and fault",
            "seed": seed,
        },
        "window": {
            "baseline_seconds": baseline_seconds,
            "incident_seconds": incident_seconds,
            "pre_injection_guard_seconds": guard_seconds,
        },
        "aggregate": _metrics(rows),
        "by_system": {key: _metrics(value) for key, value in sorted(by_system.items())},
        "by_fault": {key: _metrics(value) for key, value in sorted(by_fault.items())},
        "failures": failures,
        "cases": rows,
        "limitations": [
            "This run evaluates service localization, not incident detection precision/recall.",
            "BARO-lite is research-inspired and is not claimed as a reproduction of the BARO paper.",
            "The current benchmark uses metrics only; runtime TF4 correlation also uses logs and traces.",
            "RCAEval services and telemetry differ from the TF4 production service set.",
            "The supplied archive contains data only and no license/readme; do not redistribute it until provenance and licensing are confirmed.",
        ],
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    aggregate = result["aggregate"]
    lines = [
        "# RCAEval-v2 BARO-lite Benchmark Evidence",
        "",
        f"Generated: `{result['generated_at']}`",
        "",
        "## Result",
        "",
        "| Cases | Top-1 | Top-3 | MRR | Failures |",
        "| ---: | ---: | ---: | ---: | ---: |",
        f"| {aggregate['cases']} | {aggregate['top1']:.4f} | {aggregate['top3']:.4f} | "
        f"{aggregate['mrr']:.4f} | {len(result['failures'])} |",
        "",
        "## Reproduction",
        "",
        "```bash",
        "cd techx-corp-platform/src/aiops",
        "python -m benchmark.run /path/to/RCAEval-v2.zip --max-cases "
        f"{result['dataset']['selected_cases']} --seed {result['dataset']['seed']} "
        f"--baseline-seconds {result['window']['baseline_seconds']} "
        f"--incident-seconds {result['window']['incident_seconds']} "
        f"--guard-seconds {result['window']['pre_injection_guard_seconds']}",
        "```",
        "",
        "Selection is deterministic and stratified by RCAEval system and fault type.",
        "The scorer compares a pre-injection baseline window with the labeled incident window, ranks metrics, "
        "then aggregates the three strongest metric signals per service.",
        "",
        "## Per-system",
        "",
        "| System | Cases | Top-1 | Top-3 | MRR |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for system, metrics in result["by_system"].items():
        lines.append(
            f"| {system} | {metrics['cases']} | {metrics['top1']:.4f} | "
            f"{metrics['top3']:.4f} | {metrics['mrr']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Per-fault",
            "",
            "| Fault | Cases | Top-1 | Top-3 | MRR |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for fault, metrics in result["by_fault"].items():
        lines.append(
            f"| {fault} | {metrics['cases']} | {metrics['top1']:.4f} | "
            f"{metrics['top3']:.4f} | {metrics['mrr']:.4f} |"
        )
    misses = [row for row in result["cases"] if row["rank"] > 1]
    lines.extend(["", "## Miss analysis", ""])
    if misses:
        lines.extend(
            [
                "| Case | Ground truth | Rank | Top prediction |",
                "| --- | --- | ---: | --- |",
            ]
        )
        for row in misses[:20]:
            candidates = row["top_candidates"]
            top = candidates[0]["service"] if candidates else "none"
            lines.append(f"| {row['case']} | {row['ground_truth_service']} | {row['rank']} | {top} |")
    else:
        lines.append("No Top-1 misses in the selected sample.")
    lines.extend(["", "## Scope and limitations", ""])
    lines.extend(f"- {item}" for item in result["limitations"])
    lines.extend(
        [
            "",
            "This artifact is offline benchmark evidence for implementation quality. It is not the live E2E alert, "
            "precision/recall or lead-time evidence required by Mandate 07b.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TF4 BARO-lite scorer on RCAEval-v2")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--max-cases", type=int, default=60)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--baseline-seconds", type=int, default=600)
    parser.add_argument("--incident-seconds", type=int, default=600)
    parser.add_argument("--guard-seconds", type=int, default=30)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = benchmark(
        args.dataset,
        max_cases=args.max_cases,
        seed=args.seed,
        baseline_seconds=args.baseline_seconds,
        incident_seconds=args.incident_seconds,
        guard_seconds=args.guard_seconds,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.report:
        write_markdown(result, args.report)
    print(json.dumps({"aggregate": result["aggregate"], "failures": len(result["failures"])}, indent=2))


if __name__ == "__main__":
    main()
