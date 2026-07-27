#!/usr/bin/env python3
"""Mandate-26 external cross-service RCA replay.

Usage (from repository root):
    py -3 techx-corp-platform/src/aiops/benchmark/rca_replay.py \\
      docs/aio1/mandate-26/rca-labeled-scenarios-v1.jsonl \\
      --output docs/aio1/mandate-26/rca-replay-report-v1.json \\
      --force

Exit codes:
    0 = all parsed cases executed and all labeled acceptance cases passed
    1 = an evaluated labeled case failed
    2 = input/schema/execution error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow `python benchmark/rca_replay.py` and `python -m benchmark.rca_replay`
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app.dependency_graph import DependencyGraph, TECHX_CALL_GRAPH  # noqa: E402
from app.rca_engine import (  # noqa: E402
    RCAEngine,
    RCAEngineConfig,
    RCAEngineInput,
    parse_traces_payload,
)
from app.rca_models import RCAObservation, SignalObservation  # noqa: E402
from app.service_identity import normalize_service_name  # noqa: E402
from benchmark.rca_schema import (  # noqa: E402
    SCHEMA_NAME,
    SCHEMA_VERSION,
    RCASchemaError,
    split_engine_and_labels,
    validate_case,
)
from benchmark.rca_schema import _parse_ts  # noqa: E402


REPORT_SCHEMA = "techx.aiops.rca.report"
MAX_CASES = 200
MAX_FILE_BYTES = 25 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_revision() -> str:
    try:
        root = Path(__file__).resolve().parents[4]
        # parents: benchmark->aiops->src->techx-corp-platform->repo
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise RCASchemaError(f"Scenarios file not found: {path}")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise RCASchemaError(f"Scenarios file exceeds {MAX_FILE_BYTES} bytes")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise RCASchemaError(f"Scenarios file is empty: {path}")
    cases: list[dict[str, Any]] = []
    for line_no, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise RCASchemaError(f"JSON parse error at line {line_no}: {exc}") from exc
    if not cases:
        raise RCASchemaError(f"No valid scenarios found in file: {path}")
    if len(cases) > MAX_CASES:
        raise RCASchemaError(f"Too many cases ({len(cases)} > {MAX_CASES})")
    return cases


def _build_observations(
    engine_input: dict[str, Any],
) -> list[RCAObservation]:
    aliases = engine_input.get("service_aliases") or {}
    observations: list[RCAObservation] = []
    for raw in engine_input.get("observations") or []:
        identity = normalize_service_name(raw.get("service"), aliases=aliases)
        signals: list[SignalObservation] = []
        for sig in raw.get("signals") or []:
            observed = _parse_ts(
                sig.get("observed_at") or raw.get("observed_at"),
                field="observed_at",
                case_id=str(engine_input.get("id")),
            ) or datetime.now(timezone.utc)
            first_b = _parse_ts(
                sig.get("first_breached_at"),
                field="first_breached_at",
                case_id=str(engine_input.get("id")),
            )
            first_a = _parse_ts(
                sig.get("first_anomalous_at"),
                field="first_anomalous_at",
                case_id=str(engine_input.get("id")),
            )
            anomalous = bool(sig.get("anomalous", False))
            breached = bool(sig.get("breached", anomalous))
            signals.append(
                SignalObservation(
                    signal=str(sig.get("signal")),
                    anomalous=anomalous,
                    breached=breached,
                    coverage_status=sig.get("coverage_status") or "available",
                    confidence=float(sig.get("confidence", 0.0) or 0.0),
                    severity=str(sig.get("severity") or "medium"),
                    observed_at=observed,
                    first_breached_at=first_b or (observed if breached else None),
                    first_anomalous_at=first_a or (observed if anomalous else None),
                )
            )
        first_breached = _parse_ts(
            raw.get("first_breached_at"),
            field="first_breached_at",
            case_id=str(engine_input.get("id")),
        )
        first_anomalous = _parse_ts(
            raw.get("first_anomalous_at"),
            field="first_anomalous_at",
            case_id=str(engine_input.get("id")),
        )
        if first_breached is None:
            times = [s.first_breached_at for s in signals if s.first_breached_at]
            first_breached = min(times) if times else None
        if first_anomalous is None:
            times = [s.first_anomalous_at for s in signals if s.first_anomalous_at]
            first_anomalous = min(times) if times else None
        observations.append(
            RCAObservation(
                service=identity.canonical_service,
                original_service_names=[identity.original_service],
                signals=signals,
                first_breached_at=first_breached,
                first_anomalous_at=first_anomalous,
            )
        )
    return observations


def _build_graph(engine_input: dict[str, Any]) -> DependencyGraph:
    topology = engine_input.get("topology")
    aliases = engine_input.get("service_aliases") or {}
    if not topology:
        return DependencyGraph.from_static(TECHX_CALL_GRAPH)
    replace = bool(topology.get("replace_static") or topology.get("unseen"))
    base = None if replace else DependencyGraph.from_static(TECHX_CALL_GRAPH)
    graph = base if base is not None else DependencyGraph()
    edges = topology.get("edges") or []
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            caller, callee = edge
            conf = 1.0
            prov = "scenario"
        else:
            caller = edge.get("caller") or edge.get("from")
            callee = edge.get("callee") or edge.get("to")
            conf = float(edge.get("confidence", 1.0))
            prov = str(edge.get("provenance") or "scenario")
        caller_n = normalize_service_name(str(caller), aliases=aliases).canonical_service
        callee_n = normalize_service_name(str(callee), aliases=aliases).canonical_service
        graph.add_edge(caller_n, callee_n, provenance=prov, confidence=conf)
    if replace:
        graph.provenance_log.append("scenario:replace_static")
    else:
        graph.provenance_log.append("scenario:overlay")
    return graph


def run_case(
    case: dict[str, Any],
    engine: RCAEngine,
    *,
    captured_engine_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    engine_input, labels = split_engine_and_labels(case)
    if captured_engine_payloads is not None:
        captured_engine_payloads.append(json.loads(json.dumps(engine_input, default=str)))

    aliases = engine_input.get("service_aliases") or {}
    observations = _build_observations(engine_input)
    parse, unavailable_from_traces = parse_traces_payload(
        engine_input.get("traces"),
        aliases=aliases,
        max_traces=engine.config.max_traces,
        max_spans=engine.config.max_spans,
    )
    unavailable = list(engine_input.get("unavailable_signals") or [])
    for item in unavailable_from_traces:
        if item not in unavailable:
            unavailable.append(item)

    graph = _build_graph(engine_input)
    started = time.perf_counter()
    result = engine.analyze(
        RCAEngineInput(
            observations=observations,
            traces=parse,
            graph=graph,
            unavailable_signals=unavailable,
            topology_provenance=list(graph.provenance_log),
        )
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    evaluation: dict[str, Any] | None = None
    passed: bool | None = None
    if labels:
        expected_root = labels.get("expected_root_service")
        expected_status = labels.get("expected_attribution_status")
        noise = labels.get("correlated_noise_services") or []
        if not isinstance(noise, list):
            noise = []
        ranking = [c.service for c in result.candidates]
        root_at_1 = bool(expected_root) and result.suspected_root_service == expected_root
        root_at_3 = bool(expected_root) and expected_root in ranking[:3]
        rr = 0.0
        if expected_root and expected_root in ranking:
            rr = 1.0 / (ranking.index(expected_root) + 1)

        predicted_noise = {
            c.service
            for c in result.candidates
            if c.classification == "unexplained_parallel_anomaly"
        }
        expected_noise = {
            normalize_service_name(str(s), aliases=aliases).canonical_service for s in noise
        }
        tp = len(predicted_noise & expected_noise)
        fp = len(predicted_noise - expected_noise)
        fn = len(expected_noise - predicted_noise)
        precision = tp / (tp + fp) if (tp + fp) else (1.0 if not expected_noise else 0.0)
        recall = tp / (tp + fn) if (tp + fn) else (1.0 if not expected_noise else 0.0)
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0.0
        )

        status_ok = True
        if expected_status:
            status_ok = result.attribution_status == expected_status
        root_ok = True
        if expected_root:
            root_ok = root_at_1
        # Status-only cases (no expected root)
        if expected_status and not expected_root:
            root_ok = True
            passed = status_ok
        else:
            passed = bool(root_ok and status_ok)

        evaluation = {
            "expected_root_service": expected_root,
            "expected_attribution_status": expected_status,
            "expected_noise_services": sorted(expected_noise),
            "root_at_1": root_at_1 if expected_root else None,
            "root_at_3": root_at_3 if expected_root else None,
            "reciprocal_rank": round(rr, 6) if expected_root else None,
            "noise_precision": round(precision, 6),
            "noise_recall": round(recall, 6),
            "noise_f1": round(f1, 6),
            "predicted_noise_services": sorted(predicted_noise),
            "passed": passed,
        }

    return {
        "id": case.get("id"),
        "description": case.get("description"),
        "attribution_status": result.attribution_status,
        "suspected_root_service": result.suspected_root_service,
        "confidence": result.confidence,
        "score_margin": result.score_margin,
        "explanation": result.explanation,
        "candidates": [c.model_dump(mode="json") for c in result.candidates],
        "unavailable_signals": result.unavailable_signals,
        "topology_provenance": result.topology_provenance,
        "processing_ms": round(elapsed_ms, 3),
        "trace_count": result.trace_count,
        "span_count": result.span_count,
        "evaluation": evaluation,
        "passed": passed,
    }


def aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [c for c in cases if c.get("evaluation") is not None]
    root_hits_1 = [
        c["evaluation"]["root_at_1"]
        for c in labeled
        if c["evaluation"].get("root_at_1") is not None
    ]
    root_hits_3 = [
        c["evaluation"]["root_at_3"]
        for c in labeled
        if c["evaluation"].get("root_at_3") is not None
    ]
    rrs = [
        c["evaluation"]["reciprocal_rank"]
        for c in labeled
        if c["evaluation"].get("reciprocal_rank") is not None
    ]
    noise_f1 = [c["evaluation"]["noise_f1"] for c in labeled]
    times = [c["processing_ms"] for c in cases if c.get("processing_ms") is not None]
    times_sorted = sorted(times)

    def pct(p: float) -> float | None:
        if not times_sorted:
            return None
        if len(times_sorted) == 1:
            return times_sorted[0]
        k = (len(times_sorted) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return times_sorted[int(k)]
        return times_sorted[f] * (c - k) + times_sorted[c] * (k - f)

    attributed = sum(1 for c in cases if c.get("attribution_status") == "attributed")
    abstained = len(cases) - attributed
    labeled_pass = [c for c in labeled if c.get("passed") is True]
    labeled_fail = [c for c in labeled if c.get("passed") is False]

    return {
        "cases_total": len(cases),
        "labeled_total": len(labeled),
        "labeled_passed": len(labeled_pass),
        "labeled_failed": len(labeled_fail),
        "root_at_1": (sum(1 for x in root_hits_1 if x) / len(root_hits_1)) if root_hits_1 else None,
        "root_at_3": (sum(1 for x in root_hits_3 if x) / len(root_hits_3)) if root_hits_3 else None,
        "mrr": (sum(rrs) / len(rrs)) if rrs else None,
        "noise_f1_mean": (sum(noise_f1) / len(noise_f1)) if noise_f1 else None,
        "attribution_coverage": attributed / len(cases) if cases else 0.0,
        "abstention_rate": abstained / len(cases) if cases else 0.0,
        "processing_ms_p50": pct(0.50),
        "processing_ms_p95": pct(0.95),
        "processing_ms_mean": statistics.fmean(times) if times else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mandate-26 RCA external replay")
    parser.add_argument("scenarios", type=Path, help="JSONL scenario file")
    parser.add_argument("--output", type=Path, required=True, help="Report JSON path")
    parser.add_argument("--force", action="store_true", help="Overwrite existing report")
    parser.add_argument("--model-version", default="m26-v1")
    args = parser.parse_args(argv)

    if args.output.exists() and not args.force:
        print(f"Output exists (use --force): {args.output}", file=sys.stderr)
        return 2

    try:
        raw_cases = load_jsonl(args.scenarios)
        validated: list[dict[str, Any]] = []
        ids: set[str] = set()
        for i, raw in enumerate(raw_cases):
            case = validate_case(raw, index=i + 1)
            cid = case["id"]
            if cid in ids:
                raise RCASchemaError(f"duplicate case id: {cid!r}")
            ids.add(cid)
            validated.append(case)
    except RCASchemaError as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"io error: {exc}", file=sys.stderr)
        return 2

    engine = RCAEngine(RCAEngineConfig(model_version=args.model_version))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for case in validated:
        try:
            results.append(run_case(case, engine))
        except Exception as exc:  # noqa: BLE001 — report per-case
            errors.append({"id": case.get("id"), "error": f"{type(exc).__name__}: {exc}"})
            results.append(
                {
                    "id": case.get("id"),
                    "error": f"{type(exc).__name__}: {exc}",
                    "passed": False,
                }
            )

    if errors and len(errors) == len(validated):
        print("all cases failed to execute", file=sys.stderr)
        return 2

    agg = aggregate(results)
    report = {
        "schema_name": REPORT_SCHEMA,
        "schema_version": 1,
        "generated_at": utc_now(),
        "git_revision": git_revision(),
        "model_version": args.model_version,
        "input_path": str(args.scenarios).replace("\\", "/"),
        "input_sha256": sha256_file(args.scenarios),
        "config": {
            "trace_weight": engine.config.trace_weight,
            "topology_weight": engine.config.topology_weight,
            "temporal_weight": engine.config.temporal_weight,
            "anomaly_weight": engine.config.anomaly_weight,
            "contradiction_penalty": engine.config.contradiction_penalty,
            "parallel_anomaly_penalty": engine.config.parallel_anomaly_penalty,
            "temporal_tolerance_seconds": engine.config.temporal_tolerance_seconds,
            "max_services": engine.config.max_services,
            "max_traces": engine.config.max_traces,
            "max_spans": engine.config.max_spans,
        },
        "aggregate": agg,
        "cases": results,
        "errors": errors,
        "limitations": [
            "Seed feature weights are deterministic design seeds, not production-calibrated coefficients.",
            "Labeled suite is small and does not prove production causal accuracy.",
            "Absence of a graph edge is not proof of absence of causality.",
            "Episode state is process-local and lost on restart in the runtime worker.",
            "RCA is informational and does not retarget Mandate-22 remediation.",
            f"Labeled sample size for Root@1: {agg.get('labeled_total')}",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "aggregate": agg, "errors": len(errors)}))

    if errors and not results:
        return 2
    if any(c.get("passed") is False for c in results if c.get("evaluation") is not None):
        return 1
    if errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
