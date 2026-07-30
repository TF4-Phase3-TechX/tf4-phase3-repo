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


class ConcurrentReplayStore(MemoryLifecycleStateStore):
    """Force validated groups to race, with isolated bounded barriers."""

    def __init__(
        self,
        groups: dict[str, set[str]],
        *,
        barrier_timeout_seconds: float = 2.0,
    ) -> None:
        super().__init__()
        self.groups = groups
        self.event_to_group = {
            event_id: name for name, event_ids in groups.items() for event_id in event_ids
        }
        self.arrived = {name: set() for name in groups}
        self.ready = {name: asyncio.Event() for name in groups}
        self.barrier_timeout_seconds = barrier_timeout_seconds

    async def compare_and_set(self, key, expected_version, record, ttl_seconds):
        event_id = record.processed_event_ids[-1]
        group_name = self.event_to_group.get(event_id)
        if group_name and event_id not in self.arrived[group_name]:
            self.arrived[group_name].add(event_id)
            if self.arrived[group_name] == self.groups[group_name]:
                self.ready[group_name].set()
            try:
                await asyncio.wait_for(
                    self.ready[group_name].wait(),
                    timeout=self.barrier_timeout_seconds,
                )
            except TimeoutError as exc:
                raise ValueError(
                    f"concurrent_group {group_name!r} did not reach its bounded barrier"
                ) from exc
        return await super().compare_and_set(key, expected_version, record, ttl_seconds)


def _concurrent_groups(scenario: ReplayScenario) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = defaultdict(set)
    for row in scenario.observations:
        if row.concurrent_group:
            groups[row.concurrent_group].add(row.event_id)
    return dict(groups)


def _validate_replay_contract(
    scenario: ReplayScenario,
    oracle: ReplayOracle,
) -> list[str]:
    labels = list(dict.fromkeys(row.timestamp_label for row in scenario.observations))
    if len(labels) != oracle.expected_minutes:
        raise ValueError(
            "oracle expected_minutes does not match distinct scenario labels"
        )
    primary_counts: Counter[tuple[str, str]] = Counter(
        (row.timestamp_label, row.service)
        for row in scenario.observations
        if not row.supplemental
    )
    for label in labels:
        for service in oracle.expected_services_per_minute:
            if primary_counts[(label, service)] != 1:
                raise ValueError(
                    f"expected exactly one primary observation for {service} at {label}"
                )
    if oracle.restart_at_label and oracle.restart_at_label not in labels:
        raise ValueError("oracle restart_at_label is absent from scenario")
    actual_groups = set(_concurrent_groups(scenario))
    if actual_groups != set(oracle.expected_concurrent_groups):
        raise ValueError(
            "oracle expected_concurrent_groups does not match scenario groups"
        )
    label_indexes = {label: index for index, label in enumerate(labels)}
    for expectation in oracle.expected_incidents:
        if expectation.service not in scenario.baselines:
            raise ValueError(
                f"oracle incident service lacks baseline: {expectation.service}"
            )
        if expectation.continuity:
            start = expectation.continuity.from_label
            end = expectation.continuity.through_label
            if start not in label_indexes or end not in label_indexes:
                raise ValueError("oracle continuity labels are absent from scenario")
            if label_indexes[start] > label_indexes[end]:
                raise ValueError("oracle continuity window is reversed")
    return labels


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
    labels = _validate_replay_contract(scenario, oracle)
    concurrent_groups = _concurrent_groups(scenario)
    store: MemoryLifecycleStateStore = ConcurrentReplayStore(concurrent_groups)
    engine = LifecycleEngine(
        store,
        retention_seconds=3600,
        evidence_capacity=oracle.evidence_capacity,
    )
    evaluator = FrozenSignalEvaluator()
    stream: list[AlertEvent] = []
    restart_state_recovered = False
    restarted = False
    conflict_observed = 0
    index = 0

    while index < len(scenario.observations):
        row = scenario.observations[index]
        if row.timestamp_label == oracle.restart_at_label and not restarted:
            before = await store.list_all()
            payload = await store.export_json()
            loaded = MemoryLifecycleStateStore.from_json(payload)
            restored = ConcurrentReplayStore(concurrent_groups)
            restored._items = loaded._items
            store = restored
            engine = LifecycleEngine(
                store,
                retention_seconds=3600,
                evidence_capacity=oracle.evidence_capacity,
            )
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
            conflicts_before = engine.concurrency_conflicts_observed
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
            conflict_observed += (
                engine.concurrency_conflicts_observed - conflicts_before
            )
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
    record_by_key = {record.state_key: record for record in records}
    row_by_event = {row.event_id: row for row in scenario.observations}
    primary_by_label: dict[str, list[AlertEvent]] = defaultdict(list)
    for event in stream:
        if not row_by_event[event.event_id].supplemental:
            primary_by_label[event.timestamp].append(event)

    expected_services = set(oracle.expected_services_per_minute)
    silent_gap_count = sum(
        max(
            len(expected_services)
            - len(
                {
                    event.state_key.split("::")[2]
                    for event in primary_by_label.get(label, [])
                    if event.state_key.split("::")[2] in expected_services
                }
            ),
            0,
        )
        for label in labels
    )
    complete = silent_gap_count == 0 and all(
        Counter(
            event.state_key.split("::")[2]
            for event in primary_by_label[label]
            if event.state_key.split("::")[2] in expected_services
        )
        == Counter({service: 1 for service in expected_services})
        for label in labels
    )

    incident_ids_by_key: dict[str, set[str]] = defaultdict(set)
    incident_keys_by_id: dict[str, set[str]] = defaultdict(set)
    for event in stream:
        if event.incident_id:
            incident_ids_by_key[event.state_key].add(event.incident_id)
            incident_keys_by_id[event.incident_id].add(event.state_key)
    for record in records:
        incident_ids_by_key[record.state_key].add(record.incident_id)
        incident_keys_by_id[record.incident_id].add(record.state_key)
        for history in record.incident_history:
            incident_id = str(history["incident_id"])
            incident_ids_by_key[record.state_key].add(incident_id)
            incident_keys_by_id[incident_id].add(record.state_key)

    expected_count_by_key = {
        state_key(
            scenario.environment,
            scenario.namespace,
            item.service,
            item.incident_type,
        ): item.expected_incident_count
        for item in oracle.expected_incidents
    }
    duplicate_incident_count = sum(
        max(len(incident_ids_by_key.get(key, set())) - expected_count, 0)
        for key, expected_count in expected_count_by_key.items()
    ) + sum(max(len(keys) - 1, 0) for keys in incident_keys_by_id.values())
    false_incident_count = sum(
        len(incident_ids)
        for key, incident_ids in incident_ids_by_key.items()
        if key.split("::")[2] in set(oracle.no_incident_services)
    )

    expected_incidents = True
    continuity_results: dict[str, dict[str, bool]] = {}
    label_indexes = {label: index for index, label in enumerate(labels)}
    active_lifecycles = {
        Lifecycle.PENDING,
        Lifecycle.FIRING,
        Lifecycle.ACTIVE_SUSTAINED,
    }
    for expectation in oracle.expected_incidents:
        key = state_key(
            scenario.environment,
            scenario.namespace,
            expectation.service,
            expectation.incident_type,
        )
        record = record_by_key.get(key)
        lifecycle_ok = bool(
            record and record.lifecycle.value == expectation.final_lifecycle
        )
        expected_incidents = expected_incidents and lifecycle_ok
        checks: dict[str, bool] = {"final_lifecycle": lifecycle_ok}
        window_labels = labels
        if expectation.continuity:
            start = label_indexes[expectation.continuity.from_label]
            end = label_indexes[expectation.continuity.through_label]
            window_labels = labels[start : end + 1]
            window_events = [
                event
                for label in window_labels
                for event in primary_by_label[label]
                if event.state_key == key
            ]
            events_by_label = Counter(event.timestamp for event in window_events)
            checks["one_primary_record_per_label"] = all(
                events_by_label[label]
                == expectation.continuity.primary_records_per_label
                for label in window_labels
            )
            if expectation.continuity.require_active_lifecycle:
                checks["active_at_every_label"] = all(
                    event.lifecycle in active_lifecycles for event in window_events
                ) and len(window_events) == len(window_labels)
            if expectation.continuity.require_single_incident_id:
                checks["single_incident_id"] = (
                    len({event.incident_id for event in window_events}) == 1
                    and all(event.incident_id for event in window_events)
                )
            alert_counts = Counter(event.alert_state.value for event in window_events)
            checks["expected_hold_counts"] = all(
                alert_counts[state] == count
                for state, count in expectation.continuity.hold_alert_state_counts.items()
            )
            if expectation.continuity.require_zero_healthy_streak_on_holds:
                hold_states = set(expectation.continuity.hold_alert_state_counts)
                checks["holds_do_not_advance_recovery"] = all(
                    event.healthy_streak == 0
                    for event in window_events
                    if event.alert_state.value in hold_states
                )
        primary_rows = [
            row
            for row in scenario.observations
            if not row.supplemental
            and row.service == expectation.service
            and row.incident_type == expectation.incident_type
            and row.timestamp_label in set(window_labels)
        ]
        if expectation.require_varying_traffic:
            checks["varying_same_service_traffic"] = (
                len({row.traffic_multiplier for row in primary_rows}) > 1
            )
        if expectation.require_frozen_baseline:
            checks["baseline_frozen"] = bool(
                record
                and record.frozen_baseline.values
                == scenario.baselines[expectation.service]
                and record.baseline_version == 1
            )
        if expectation.require_evidence_compaction:
            checks["evidence_compacted_and_hashed"] = bool(
                record
                and len(record.evidence_samples) <= oracle.evidence_capacity
                and record.evidence_count > len(record.evidence_samples)
                and record.evidence_digest
            )
        continuity_results[key] = checks

    concurrency_results: dict[str, bool] = {}
    for group_name, event_ids in concurrent_groups.items():
        first_row = next(
            row for row in scenario.observations if row.event_id in event_ids
        )
        key = state_key(
            scenario.environment,
            scenario.namespace,
            first_row.service,
            first_row.incident_type,
        )
        record = record_by_key.get(key)
        retained_ids = {
            str(item.get("event_id"))
            for item in (record.evidence_samples if record else [])
        }
        concurrency_results[group_name] = event_ids <= retained_ids
    lost_concurrency_groups = sum(not value for value in concurrency_results.values())

    conditions = {
        "external_scenario_schema_validated": True,
        "oracle_separate_from_detector_input": True,
        "expected_incident_lifecycles": expected_incidents,
        "every_minute_contains_each_primary_service": complete,
        "incident_continuity_expectations": all(
            all(checks.values()) for checks in continuity_results.values()
        ),
        "no_unexpected_incidents": false_incident_count == 0,
        "no_duplicate_incident_generations_or_id_collisions": (
            duplicate_incident_count == 0
        ),
        "restart_uses_serialized_state": (
            oracle.restart_at_label is None or restart_state_recovered
        ),
        "concurrent_updates_preserved": (
            not concurrent_groups
            or (
                conflict_observed >= len(concurrent_groups)
                and lost_concurrency_groups == 0
            )
        ),
        "all_evidence_records_are_bounded_and_hashed": all(
            len(record.evidence_samples) <= oracle.evidence_capacity
            and (record.evidence_count == 0 or bool(record.evidence_digest))
            for record in records
        ),
    }
    active = active_lifecycles | {Lifecycle.RECOVERING}
    active_by_time: dict[str, set[str]] = defaultdict(set)
    for event in stream:
        if event.incident_id and event.lifecycle in active:
            active_by_time[event.timestamp].add(event.incident_id)
    summary = {
        "schema_version": "mandate28-summary/v2",
        "scenario_id": scenario.scenario_id,
        "simulated_minutes": oracle.expected_minutes,
        "alert_record_count": len(stream),
        "silent_gap_count": silent_gap_count,
        "false_incident_count": false_incident_count,
        "duplicate_incident_count": duplicate_incident_count,
        "state_recovery_failures": (
            0 if oracle.restart_at_label is None or restart_state_recovered else 1
        ),
        "stacked_incident_count": max(map(len, active_by_time.values()), default=0),
        "concurrency_conflicts_observed": conflict_observed,
        "concurrency_conflicts_lost": lost_concurrency_groups,
        "continuity_checks": continuity_results,
        "concurrency_checks": concurrency_results,
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
