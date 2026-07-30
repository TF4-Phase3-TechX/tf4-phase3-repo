"""Validated external inputs for the Mandate 28 replay."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RawObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp_label: str
    observed_at: datetime
    event_id: str = Field(min_length=1)
    sequence: int
    service: str = Field(min_length=1)
    incident_type: str = Field(min_length=1)
    signal_kind: Literal["latency", "error_rate"]
    value: float
    recent_values: list[float] = Field(default_factory=list)
    request_count: float = 100
    minimum_request_count: float = 20
    slo_target: float | None = None
    short_burn: float | None = None
    long_burn: float | None = None
    primary_telemetry_available: bool = True
    traffic_sufficient: bool = True
    traffic_multiplier: float = 1.0
    enrichment_degraded: bool = False
    concurrent_group: str | None = None


class ReplayScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mandate28-scenario/v2"]
    scenario_id: str
    environment: str = "production"
    namespace: str = "techx-tf4"
    baselines: dict[str, list[float]]
    observations: list[RawObservation] = Field(min_length=1)


class IncidentExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str
    incident_type: str
    final_lifecycle: str


class ReplayOracle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mandate28-oracle/v2"]
    expected_minutes: int
    expected_services_per_minute: list[str]
    expected_incidents: list[IncidentExpectation]
    no_incident_services: list[str]


def load_scenario(path: Path) -> ReplayScenario:
    """Load and strictly validate a caller-supplied JSON or JSONL scenario."""

    if path.suffix == ".jsonl":
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if not lines or lines[0].pop("record_type", None) != "metadata":
            raise ValueError("JSONL scenario must start with a metadata record")
        observations = []
        for item in lines[1:]:
            if item.pop("record_type", None) != "observation":
                raise ValueError("JSONL scenario rows must be observation records")
            observations.append(item)
        return ReplayScenario.model_validate({**lines[0], "observations": observations})
    return ReplayScenario.model_validate_json(path.read_text(encoding="utf-8"))


def load_oracle(path: Path) -> ReplayOracle:
    """Load an oracle that is deliberately separate from detector inputs."""

    return ReplayOracle.model_validate_json(path.read_text(encoding="utf-8"))


def dump_model(path: Path, model: BaseModel) -> None:
    path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def dump_scenario_jsonl(path: Path, scenario: ReplayScenario) -> None:
    metadata = scenario.model_dump(mode="json", exclude={"observations"})
    records = [
        {"record_type": "metadata", **metadata},
        *[
            {"record_type": "observation", **item.model_dump(mode="json")}
            for item in scenario.observations
        ],
    ]
    path.write_text(
        "\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n",
        encoding="utf-8",
    )
