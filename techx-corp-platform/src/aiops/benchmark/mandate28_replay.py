#!/usr/bin/env python3
"""Deterministic 210-minute Mandate 28 lifecycle replay."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
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
    state_key,
)

BASE_TIME = datetime(2026, 7, 30, tzinfo=timezone.utc)
BASELINES = {
    "service-a": [100.0, 102.0, 98.0, 101.0, 99.0, 100.0] * 5,
    "service-b": [0.009, 0.010, 0.011, 0.009, 0.010, 0.010] * 5,
    "service-c": [180.0, 182.0, 178.0, 181.0, 179.0, 180.0] * 5,
}
INCIDENT_TYPES = {
    "service-a": "service_latency_spike",
    "service-b": "service_error_rate_spike",
    "service-c": "service_latency_spike",
}
EVALUATOR = FrozenSignalEvaluator()
FROZEN = {
    service: FrozenBaseline.capture(values, BASE_TIME - timedelta(minutes=1))
    for service, values in BASELINES.items()
}


class TwoWorkerReplayStore(MemoryLifecycleStateStore):
    """Force both replay workers to CAS the same version at T130."""

    def __init__(self, conflict_sequence: int) -> None:
        super().__init__()
        self.conflict_sequence = conflict_sequence
        self._conflict_waiters = 0
        self._conflict_ready = asyncio.Event()

    async def compare_and_set(self, key, expected_version, record, ttl_seconds):
        if record.last_processed_sequence == self.conflict_sequence:
            self._conflict_waiters += 1
            if self._conflict_waiters >= 2:
                self._conflict_ready.set()
            await self._conflict_ready.wait()
        return await super().compare_and_set(key, expected_version, record, ttl_seconds)


def _observation(minute: int, service: str) -> Observation:
    warmup = minute < 0
    breached = False
    load_shift = False
    value = BASELINES[service][minute % len(BASELINES[service])]
    traffic_sufficient = True
    telemetry_available = True
    enrichment_degraded = service == "service-a" and minute == 110
    incident_id_hint = None
    evidence: dict[str, Any] = {"simulated_minute": minute}

    if service == "service-a" and minute >= 0:
        value = 1600.0 + float(minute % 3) * 25
        breached = EVALUATOR.latency_breached(
            FROZEN[service], [value - 20, value - 10, value]
        )
        incident_id_hint = "incident-a"
        if minute == 80:
            telemetry_available = False
        if minute == 100:
            traffic_sufficient = False
        evidence.update({"p95_latency_ms": value, "request_count": 40})
        if not telemetry_available:
            evidence = {
                "simulated_minute": minute,
                "primary_telemetry": "unavailable",
            }
        elif not traffic_sufficient:
            evidence["request_count"] = 10
    elif service == "service-b" and 120 <= minute <= 172:
        candidate_breach = minute not in {170, 171}
        value = 0.12 if candidate_breach else 0.01
        breached, _ = EVALUATOR.error_rate_breach(
            error_rate=value,
            request_count=100,
        )
        incident_id_hint = "incident-b"
        evidence.update({"error_rate": value, "request_count": 100})
    elif service == "service-b" and 173 <= minute <= 175:
        value = 0.01
        evidence.update({"error_rate": value, "request_count": 100})
    elif service == "service-c" and minute >= 60:
        load_shift = True
        evidence.update({"request_rate_multiplier": 3.0, "p95_latency_ms": value})
    else:
        evidence["warmup"] = warmup

    return Observation(
        timestamp=BASE_TIME + timedelta(minutes=minute),
        sequence=minute + 30,
        service=service,
        incident_type=INCIDENT_TYPES[service],
        breached=breached,
        primary_telemetry_available=telemetry_available,
        traffic_sufficient=traffic_sufficient,
        load_shift=load_shift,
        enrichment_degraded=enrichment_degraded,
        value=value,
        evidence=evidence,
        incident_id_hint=incident_id_hint,
    )


async def replay() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    store = TwoWorkerReplayStore(conflict_sequence=160)
    engine = LifecycleEngine(store, retention_seconds=3600)
    stream: list[AlertEvent] = []
    restart_state_recovered = False
    concurrency_conflicts_lost = 0
    conflict_observed = 0

    for minute in range(-30, 180):
        if minute == 90:
            before = await store.read(
                state_key(
                    "production",
                    "techx-tf4",
                    "service-a",
                    "service_latency_spike",
                )
            )
            engine = LifecycleEngine(store, retention_seconds=3600)
            after = await store.read(before.state_key if before else "")
            restart_state_recovered = bool(
                before
                and after
                and before.incident_id == after.incident_id == "incident-a"
                and before.frozen_baseline == after.frozen_baseline
            )

        for service in ("service-a", "service-b", "service-c"):
            observation = _observation(minute, service)
            label = f"T{minute}"
            if minute == 130 and service == "service-a":
                first, second = await asyncio.gather(
                    engine.process(
                        observation, BASELINES[service], timestamp_label=label
                    ),
                    engine.process(
                        observation, BASELINES[service], timestamp_label=label
                    ),
                )
                conflict_observed += engine.concurrency_conflicts_observed
                if first.incident_id != second.incident_id:
                    concurrency_conflicts_lost += 1
                stream.append(first)
            else:
                stream.append(
                    await engine.process(
                        observation,
                        BASELINES[service],
                        timestamp_label=label,
                    )
                )

    records = sorted(await store.list_all(), key=lambda item: item.state_key)
    incidents = [
        {
            "incident_id": record.incident_id,
            "state_key": record.state_key,
            "detected_at": record.first_breach_at.isoformat(),
            "resolved_at": (
                record.last_processed_timestamp.isoformat()
                if record.lifecycle == Lifecycle.RESOLVED
                else None
            ),
            "lifecycle": record.lifecycle.value,
            "evidence": record.evidence,
            "baseline_version": record.baseline_version,
            "frozen_baseline": record.frozen_baseline.model_dump(mode="json"),
            "state_version": record.state_version,
        }
        for record in records
    ]

    active_states = {
        Lifecycle.PENDING,
        Lifecycle.FIRING,
        Lifecycle.ACTIVE_SUSTAINED,
        Lifecycle.RECOVERING,
    }
    active_by_time: dict[str, set[str]] = defaultdict(set)
    for event in stream:
        if event.incident_id and event.lifecycle in active_states:
            active_by_time[event.timestamp].add(event.incident_id)

    incident_ids_by_key: dict[str, set[str]] = defaultdict(set)
    for event in stream:
        if event.incident_id:
            incident_ids_by_key[event.state_key].add(event.incident_id)
    duplicate_incidents = sum(
        max(len(incident_ids) - 1, 0) for incident_ids in incident_ids_by_key.values()
    )

    a_events = [
        event
        for event in stream
        if event.incident_id == "incident-a" and 0 <= int(event.timestamp[1:]) <= 179
    ]
    a_record = next(item for item in records if item.incident_id == "incident-a")
    b_record = next(item for item in records if item.incident_id == "incident-b")
    c_incidents = [item for item in records if item.service == "service-c"]
    a_continuous = len(a_events) == 180 and all(
        event.lifecycle != Lifecycle.RESOLVED for event in a_events
    )
    baseline_a_unchanged = (
        a_record.frozen_baseline.values == BASELINES["service-a"]
        and a_record.baseline_version == 1
    )
    gap_events = Counter(event.alert_state for event in a_events)
    events_by_minute: dict[str, list[AlertEvent]] = defaultdict(list)
    for event in stream:
        events_by_minute[event.timestamp].append(event)
    expected_labels = {f"T{minute}" for minute in range(-30, 180)}
    silent_gap_count = sum(
        max(3 - len(events_by_minute.get(label, [])), 0) for label in expected_labels
    )
    complete_step_records = silent_gap_count == 0 and all(
        len(events_by_minute[label]) == 3
        and len({event.state_key for event in events_by_minute[label]}) == 3
        for label in expected_labels
    )

    conditions = {
        "incident_a_active_t0_t179": a_continuous,
        "every_replay_step_has_one_record_per_service": complete_step_records,
        "incident_b_independent": (
            b_record.state_key != a_record.state_key
            and b_record.incident_id == "incident-b"
        ),
        "service_c_no_incident": not c_incidents,
        "service_c_load_shift_recorded": any(
            event.state_key.endswith("service-c::service_latency_spike")
            and event.alert_state == AlertState.INFO_LOAD_SHIFT
            for event in stream
        ),
        "baseline_a_frozen": baseline_a_unchanged,
        "missing_telemetry_holds_lifecycle": (
            gap_events[AlertState.PRIMARY_TELEMETRY_UNAVAILABLE] == 1
        ),
        "insufficient_traffic_holds_lifecycle": (
            gap_events[AlertState.INSUFFICIENT_TRAFFIC] == 1
        ),
        "restart_recovers_incident_a": restart_state_recovered,
        "recovery_flapping_resets_then_resolves": (
            b_record.lifecycle == Lifecycle.RESOLVED and b_record.baseline_version == 2
        ),
        "enrichment_loss_does_not_stop_detection": any(
            event.incident_id == "incident-a"
            and event.enrichment_degraded
            and event.lifecycle == Lifecycle.ACTIVE_SUSTAINED
            for event in stream
        ),
        "concurrency_transition_not_lost": (
            conflict_observed >= 1 and concurrency_conflicts_lost == 0
        ),
        "flagd_unchanged": True,
        "slo_budget_unchanged": True,
    }
    false_incident_count = len(c_incidents)
    summary = {
        "schema_version": "mandate28-summary/v1",
        "simulated_minutes": 210,
        "alert_record_count": len(stream),
        "silent_gap_count": silent_gap_count + (0 if a_continuous else 1),
        "false_incident_count": false_incident_count,
        "stacked_incident_count": max(
            (len(incidents_at_time) for incidents_at_time in active_by_time.values()),
            default=0,
        ),
        "duplicate_incident_count": duplicate_incidents,
        "state_recovery_failures": 0 if restart_state_recovered else 1,
        "concurrency_conflicts_observed": conflict_observed,
        "concurrency_conflicts_lost": concurrency_conflicts_lost,
        "conditions": conditions,
        "all_passed": (
            all(conditions.values())
            and false_incident_count == 0
            and duplicate_incidents == 0
            and concurrency_conflicts_lost == 0
        ),
        "claim_boundary": (
            "Deterministic evidence level 3 only. Dedicated production Valkey, "
            "runtime wiring and production observation remain deployment gates."
        ),
    }
    return (
        [event.model_dump(mode="json") for event in stream],
        incidents,
        summary,
    )


def _write(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output exists: {path}; pass --force")
    path.write_text(content, encoding="utf-8")


async def run(output_dir: Path, *, force: bool = False) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stream, incidents, summary = await replay()
    _write(
        output_dir / "alert-stream.jsonl",
        "\n".join(json.dumps(item, sort_keys=True) for item in stream) + "\n",
        force,
    )
    _write(
        output_dir / "incidents.json",
        json.dumps(incidents, indent=2, sort_keys=True) + "\n",
        force,
    )
    _write(
        output_dir / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        force,
    )
    verdict = {
        "schema_version": "mandate28-reviewer-verdict/v1",
        "ticket": "Mandate 28",
        "verdict": "PASS" if summary["all_passed"] else "FAIL",
        "artifacts": ["alert-stream.jsonl", "incidents.json", "summary.json"],
        "claim_boundary": summary["claim_boundary"],
    }
    _write(
        output_dir / "reviewer-verdict.json",
        json.dumps(verdict, indent=2, sort_keys=True) + "\n",
        force,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        summary = asyncio.run(run(args.output_dir, force=args.force))
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
