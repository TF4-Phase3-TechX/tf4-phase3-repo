import hashlib
import json

import pytest
from pydantic import ValidationError

from benchmark.generate_mandate28_scenario import build
from benchmark.mandate28_replay import replay, run
from benchmark.mandate28_schema import dump_model, load_scenario


@pytest.mark.asyncio
async def test_external_210_minute_replay_passes_acceptance_conditions():
    scenario, oracle = build()
    stream, incidents, summary = await replay(scenario, oracle)

    assert len(stream) == 210 * 3 + 1
    assert summary["all_passed"] is True
    assert summary["silent_gap_count"] == 0
    assert summary["false_incident_count"] == 0
    assert summary["state_recovery_failures"] == 0
    assert summary["concurrency_conflicts_lost"] == 0
    assert summary["stacked_incident_count"] == 2
    assert summary["conditions"]["two_distinct_concurrent_updates_preserved"]
    assert {item["service"] for item in incidents} == {"service-a", "service-b"}


def _inputs(tmp_path):
    scenario, oracle = build()
    scenario_path = tmp_path / "scenario.json"
    oracle_path = tmp_path / "oracle.json"
    dump_model(scenario_path, scenario)
    dump_model(oracle_path, oracle)
    repository_root = tmp_path / "repo"
    protected = repository_root / "protected.txt"
    protected.parent.mkdir()
    protected.write_text("immutable\n", encoding="utf-8")
    digest = hashlib.sha256(protected.read_bytes()).hexdigest()
    manifest = tmp_path / "protected-manifest.json"
    manifest.write_text(
        json.dumps({"sha256": {"protected.txt": digest}}), encoding="utf-8"
    )
    return scenario_path, oracle_path, manifest, repository_root


@pytest.mark.asyncio
async def test_replay_writes_candidate_not_self_approved_verdict(tmp_path):
    scenario, oracle, manifest, repository_root = _inputs(tmp_path)
    output = tmp_path / "out"
    summary = await run(
        output,
        scenario_path=scenario,
        oracle_path=oracle,
        protected_manifest=manifest,
        repository_root=repository_root,
    )

    assert summary["all_passed"] is True
    assert len((output / "alert-stream.jsonl").read_text().splitlines()) == 631
    candidate = json.loads((output / "candidate-verdict.json").read_text())
    assert candidate["candidate_result"] == "PASS"
    assert candidate["independent_review"]["status"] == "pending"
    assert not (output / "reviewer-verdict.json").exists()


@pytest.mark.asyncio
async def test_replay_refuses_overwrite_without_force(tmp_path):
    scenario, oracle, manifest, repository_root = _inputs(tmp_path)
    output = tmp_path / "out"
    kwargs = {
        "scenario_path": scenario,
        "oracle_path": oracle,
        "protected_manifest": manifest,
        "repository_root": repository_root,
    }
    await run(output, **kwargs)
    with pytest.raises(FileExistsError, match="pass --force"):
        await run(output, **kwargs)


def test_scenario_schema_rejects_detector_labels(tmp_path):
    scenario, _ = build()
    payload = scenario.model_dump(mode="json")
    payload["observations"][0]["breached"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="breached"):
        load_scenario(path)
