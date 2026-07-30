#!/usr/bin/env python3
"""Generate the reference raw scenario and its independent oracle."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from benchmark.mandate28_schema import (
    IncidentExpectation,
    RawObservation,
    ReplayOracle,
    ReplayScenario,
    dump_model,
    dump_scenario_jsonl,
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


def build() -> tuple[ReplayScenario, ReplayOracle]:
    rows: list[RawObservation] = []
    sequence = 0
    for minute in range(-30, 180):
        for service in ("service-a", "service-b", "service-c"):
            value = BASELINES[service][minute % len(BASELINES[service])]
            signal_kind = "error_rate" if service == "service-b" else "latency"
            recent = [value] * 3 if signal_kind == "latency" else []
            request_count = 100.0
            primary = True
            traffic = True
            multiplier = 1.0
            enrichment = False
            short_burn = None
            long_burn = None

            if service == "service-a" and minute >= 0:
                value = 1600.0 + float(minute % 3) * 25
                recent = [value - 20, value - 10, value]
                # Same-service load varies throughout Incident A; it is evidence,
                # never a pre-labelled detector result.
                multiplier = 1.0 + (minute % 5) * 0.55
                primary = minute != 80
                traffic = minute != 100
                request_count = 10.0 if not traffic else 40.0 + (minute % 4) * 15
                enrichment = minute == 110
            elif service == "service-b" and 120 <= minute <= 172:
                value = 0.01 if minute in {170, 171} else 0.12
                short_burn = 1.0 if value < 0.05 else 12.0
                long_burn = 1.0 if value < 0.05 else 11.0
            elif service == "service-b" and 173 <= minute <= 175:
                value = 0.01
                short_burn = long_burn = 1.0
            elif service == "service-c" and minute >= 60:
                multiplier = 3.0 + (minute % 3) * 0.25

            rows.append(
                RawObservation(
                    timestamp_label=f"T{minute}",
                    observed_at=BASE_TIME + timedelta(minutes=minute),
                    event_id=f"{service}-T{minute}-primary",
                    sequence=sequence,
                    service=service,
                    incident_type=INCIDENT_TYPES[service],
                    signal_kind=signal_kind,
                    value=value,
                    recent_values=recent,
                    request_count=request_count,
                    slo_target=0.99 if service == "service-b" else None,
                    short_burn=short_burn,
                    long_burn=long_burn,
                    primary_telemetry_available=primary,
                    traffic_sufficient=traffic,
                    traffic_multiplier=multiplier,
                    enrichment_degraded=enrichment,
                    concurrent_group=(
                        "service-a-T130" if service == "service-a" and minute == 130 else None
                    ),
                )
            )
            sequence += 1
            if service == "service-a" and minute == 130:
                rows.append(
                    RawObservation(
                        timestamp_label="T130",
                        observed_at=BASE_TIME + timedelta(minutes=130),
                        event_id="service-a-T130-concurrent",
                        sequence=sequence,
                        service=service,
                        incident_type=INCIDENT_TYPES[service],
                        signal_kind="latency",
                        value=1660.0,
                        recent_values=[1630.0, 1645.0, 1660.0],
                        request_count=85,
                        traffic_multiplier=2.75,
                        concurrent_group="service-a-T130",
                    )
                )
                sequence += 1

    scenario = ReplayScenario(
        schema_version="mandate28-scenario/v2",
        scenario_id="mandate28-reference-210m-v2",
        baselines=BASELINES,
        observations=rows,
    )
    oracle = ReplayOracle(
        schema_version="mandate28-oracle/v2",
        expected_minutes=210,
        expected_services_per_minute=["service-a", "service-b", "service-c"],
        expected_incidents=[
            IncidentExpectation(
                service="service-a",
                incident_type=INCIDENT_TYPES["service-a"],
                final_lifecycle="ACTIVE_SUSTAINED",
            ),
            IncidentExpectation(
                service="service-b",
                incident_type=INCIDENT_TYPES["service-b"],
                final_lifecycle="RESOLVED",
            ),
        ],
        no_incident_services=["service-c"],
    )
    return scenario, oracle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    args = parser.parse_args()
    scenario, oracle = build()
    args.scenario.parent.mkdir(parents=True, exist_ok=True)
    args.oracle.parent.mkdir(parents=True, exist_ok=True)
    if args.scenario.suffix == ".jsonl":
        dump_scenario_jsonl(args.scenario, scenario)
    else:
        dump_model(args.scenario, scenario)
    dump_model(args.oracle, oracle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
