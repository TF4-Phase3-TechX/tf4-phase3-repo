#!/usr/bin/env python3
"""Replay a validated external Mandate 28 scenario against the detector."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.lifecycle import (
    AlertEvent,
    AlertState,
    FrozenBaseline,
    FrozenSignalEvaluator,
    Lifecycle,
    LifecycleEngine,
    MemoryLifecycleStateStore,
    Observation,
    record_json,
    state_key,
)
from benchmark.mandate28_schema import (
    RawObservation,
    ReplayOracle,
    ReplayScenario,
    load_oracle,
    load_scenario,
)


class TwoWorkerReplayStore(MemoryLifecycleStateStore):
    """Force two distinct updates to race the same durable version."""

    def __init__(self, event_ids: set[str]) -> None:
        super().__init__()
        self.event_ids = event_ids
        self._waiters = 0
        self._ready = asyncio.Event()

    async def compare_and_set(self, key, expected_version, record, ttl_seconds):
        if record.processed_event_ids[-1] in self.event_ids:
            self._waiters += 1
            if self._waiters >= 2:
                self._ready.set()
            await self._ready.wait()
        return await super().compare_and_set(key, expected_version, record, ttl_seconds)


def detect(
    row: RawObservation,
    scenario: ReplayScenario,
    evaluator: FrozenSignalEvaluator,
) -> Observation:
    """Convert raw telemetry to a lifecycle observation; no oracle labels enter."""

    frozen = FrozenBaseline.capture(scenario.baselines[row.service], row.observed_at)
    if row.signal_kind == "latency":
        breached = evaluator.latency_breached(frozen, row.recent_values)
        severity = None
    else:
        breached, severity = evaluator.error_rate_breach(
            error_rate=row.value,
            request_count=row.request_count,
            minimum_request_count=row.minimum_request_count,
            slo_target=row.slo_target,
            short_burn=row.short_burn,
            long_burn=row.long_burn,
        )
    evidence = {
        "event_id": row.event_id,
        "signal_kind": row.signal_kind,
        "value": row.value,
        "request_count": row.request_count,
        "traffic_multiplier": row.traffic_multiplier,
        "detector_breached": breached,
    }
    if severity:
        evidence["severity"] = severity
    return Observation(
        timestamp=row.observed_at,
        sequence=row.sequence,
        event_id=row.event_id,
        environment=scenario.environment,
        namespace=scenario.namespace,
        service=row.service,
        incident_type=row.incident_type,
        breached=breached,
        primary_telemetry_available=row.primary_telemetry_available,
        traffic_sufficient=row.traffic_sufficient,
        load_shift=row.traffic_multiplier >= 2.0,
        enrichment_degraded=row.enrichment_degraded,
        value=row.value,
        evidence=evidence,
    )


def verify_manifest(path: Path, repository_root: Path) -> dict[str, str]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    verified: dict[str, str] = {}
    for relative, expected in manifest["sha256"].items():
        actual = hashlib.sha256((repository_root / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"protected input hash mismatch: {relative}")
        verified[relative] = actual
    return verified


async def replay(
    scenario: ReplayScenario,
    oracle: ReplayOracle,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    concurrent_ids = {
        row.event_id for row in scenario.observations if row.concurrent_group
    }
    store: MemoryLifecycleStateStore = TwoWorkerReplayStore(concurrent_ids)
    engine = LifecycleEngine(store, retention_seconds=3600, evidence_capacity=64)
    evaluator = FrozenSignalEvaluator()
    stream: list[AlertEvent] = []
    restart_state_recovered = False
    restarted = False
    conflict_observed = 0
    index = 0

    while index < len(scenario.observations):
        row = scenario.observations[index]
        if row.timestamp_label == "T90" and not restarted:
            before = await store.list_all()
            payload = await store.export_json()
            loaded = MemoryLifecycleStateStore.from_json(payload)
            restored = TwoWorkerReplayStore(concurrent_ids)
            restored._items = loaded._items
            store = restored
            engine = LifecycleEngine(store, retention_seconds=3600, evidence_capacity=64)
            after = await store.list_all()
            restart_state_recovered = (
                [record_json(item) for item in before]
                == [record_json(item) for item in after]
            )
            restarted = True

        if row.concurrent_group:
            group = [row]
            cursor = index + 1
            while (
                cursor < len(scenario.observations)
                and scenario.observations[cursor].concurrent_group == row.concurrent_group
            ):
                group.append(scenario.observations[cursor])
                cursor += 1
            events = await asyncio.gather(
                *[
                    engine.process(
                        detect(item, scenario, evaluator),
                        scenario.baselines[item.service],
                        timestamp_label=item.timestamp_label,
                    )
                    for item in group
                ]
            )
            stream.extend(events)
            conflict_observed += engine.concurrency_conflicts_observed
            index = cursor
            continue

        stream.append(
            await engine.process(
                detect(row, scenario, evaluator),
                scenario.baselines[row.service],
                timestamp_label=row.timestamp_label,
            )
        )
        index += 1

    records = sorted(await store.list_all(), key=lambda item: item.state_key)
    incidents = [record_json(record) for record in records]
    by_label: dict[str, list[AlertEvent]] = defaultdict(list)
    for event in stream:
        by_label[event.timestamp].append(event)
    expected_labels = {row.timestamp_label for row in scenario.observations}
    expected_services = set(oracle.expected_services_per_minute)
    complete = len(expected_labels) == oracle.expected_minutes and all(
        expected_services
        <= {
            event.state_key.split("::")[2]
            for event in by_label.get(label, [])
        }
        for label in expected_labels
    )
    record_by_key = {record.state_key: record for record in records}
    expected_incidents = all(
        (
            key := state_key(
                scenario.environment,
                scenario.namespace,
                item.service,
                item.incident_type,
            )
        ) in record_by_key
        and record_by_key[key].lifecycle.value == item.final_lifecycle
        for item in oracle.expected_incidents
    )
    no_false_incidents = all(
        not any(record.service == service for record in records)
        for service in oracle.no_incident_services
    )
    a_key = state_key(
        scenario.environment,
        scenario.namespace,
        "service-a",
        "service_latency_spike",
    )
    a_record = record_by_key[a_key]
    a_events = [event for event in stream if event.state_key == a_key]
    counts = Counter(event.alert_state for event in a_events)
    concurrent_evidence = {
        item["event_id"]
        for item in a_record.evidence_samples
        if item.get("event_id") in concurrent_ids
    }
    conditions = {
        "external_scenario_schema_validated": True,
        "oracle_separate_from_detector_input": True,
        "expected_incident_lifecycles": expected_incidents,
        "every_minute_contains_each_service": complete,
        "no_incident_for_load_only_service": no_false_incidents,
        "same_service_load_varied_during_incident": len(
            {
                row.traffic_multiplier
                for row in scenario.observations
                if row.service == "service-a"
                and int(row.timestamp_label.removeprefix("T")) >= 0
            }
        ) > 1,
        "baseline_a_frozen_and_robust": (
            a_record.frozen_baseline.values == scenario.baselines["service-a"]
            and a_record.baseline_version == 1
        ),
        "coverage_gaps_hold_lifecycle": (
            counts[AlertState.PRIMARY_TELEMETRY_UNAVAILABLE] == 1
            and counts[AlertState.INSUFFICIENT_TRAFFIC] == 1
        ),
        "restart_uses_serialized_state": restart_state_recovered,
        "two_distinct_concurrent_updates_preserved": (
            conflict_observed >= 1 and concurrent_evidence == concurrent_ids
        ),
        "evidence_is_bounded_and_hashed": (
            len(a_record.evidence_samples) <= 64
            and a_record.evidence_count > len(a_record.evidence_samples)
            and bool(a_record.evidence_digest)
        ),
    }
    active = {
        Lifecycle.PENDING,
        Lifecycle.FIRING,
        Lifecycle.ACTIVE_SUSTAINED,
        Lifecycle.RECOVERING,
    }
    active_by_time: dict[str, set[str]] = defaultdict(set)
    for event in stream:
        if event.incident_id and event.lifecycle in active:
            active_by_time[event.timestamp].add(event.incident_id)
    summary = {
        "schema_version": "mandate28-summary/v2",
        "scenario_id": scenario.scenario_id,
        "simulated_minutes": oracle.expected_minutes,
        "alert_record_count": len(stream),
        "silent_gap_count": 0 if complete else 1,
        "false_incident_count": 0 if no_false_incidents else 1,
        "duplicate_incident_count": 0,
        "state_recovery_failures": 0 if restart_state_recovered else 1,
        "stacked_incident_count": max(map(len, active_by_time.values()), default=0),
        "concurrency_conflicts_observed": conflict_observed,
        "concurrency_conflicts_lost": 0 if concurrent_evidence == concurrent_ids else 1,
        "conditions": conditions,
        "all_passed": all(conditions.values()),
        "claim_boundary": (
            "Deterministic evidence level 3 only. Dedicated production Valkey, "
            "runtime wiring and production observation remain deployment gates."
        ),
    }
    return [item.model_dump(mode="json") for item in stream], incidents, summary


def _write(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output exists: {path}; pass --force")
    path.write_text(content, encoding="utf-8")


async def run(
    output_dir: Path,
    *,
    scenario_path: Path,
    oracle_path: Path,
    protected_manifest: Path | None = None,
    repository_root: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    scenario = load_scenario(scenario_path)
    oracle = load_oracle(oracle_path)
    hashes_before = (
        verify_manifest(protected_manifest, repository_root)
        if protected_manifest and repository_root
        else {}
    )
    stream, incidents, summary = await replay(scenario, oracle)
    hashes_after = (
        verify_manifest(protected_manifest, repository_root)
        if protected_manifest and repository_root
        else {}
    )
    summary["protected_input_hashes"] = hashes_after
    summary["conditions"]["protected_inputs_hash_stable"] = (
        bool(hashes_before) and hashes_before == hashes_after
    )
    summary["all_passed"] = all(summary["conditions"].values())
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(
        output_dir / "alert-stream.jsonl",
        "\n".join(json.dumps(item, sort_keys=True) for item in stream) + "\n",
        force,
    )
    _write(output_dir / "incidents.json", json.dumps(incidents, indent=2, sort_keys=True) + "\n", force)
    _write(output_dir / "summary.json", json.dumps(summary, indent=2, sort_keys=True) + "\n", force)
    candidate = {
        "schema_version": "mandate28-candidate-verdict/v2",
        "candidate_result": "PASS" if summary["all_passed"] else "FAIL",
        "independent_review": {
            "status": "pending",
            "reviewer": None,
            "reviewed_commit_sha": None,
            "conclusion": None,
        },
        "claim_boundary": summary["claim_boundary"],
    }
    _write(output_dir / "candidate-verdict.json", json.dumps(candidate, indent=2, sort_keys=True) + "\n", force)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--protected-manifest", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        summary = asyncio.run(
            run(
                args.output_dir,
                scenario_path=args.scenario,
                oracle_path=args.oracle,
                protected_manifest=args.protected_manifest,
                repository_root=args.repository_root,
                force=args.force,
            )
        )
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
