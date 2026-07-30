import json

import pytest

from benchmark.mandate28_replay import replay, run


@pytest.mark.asyncio
async def test_210_minute_replay_passes_all_acceptance_conditions():
    stream, incidents, summary = await replay()

    assert len(stream) == 210 * 3
    assert summary["all_passed"] is True
    assert summary["silent_gap_count"] == 0
    assert summary["false_incident_count"] == 0
    assert summary["duplicate_incident_count"] == 0
    assert summary["state_recovery_failures"] == 0
    assert summary["concurrency_conflicts_lost"] == 0
    assert summary["stacked_incident_count"] == 2
    assert summary["conditions"]["every_replay_step_has_one_record_per_service"] is True
    assert {item["incident_id"] for item in incidents} == {
        "incident-a",
        "incident-b",
    }


@pytest.mark.asyncio
async def test_replay_writes_machine_readable_artifacts(tmp_path):
    summary = await run(tmp_path)

    assert summary["all_passed"] is True
    alert_lines = (
        (tmp_path / "alert-stream.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(alert_lines) == 630
    assert all(json.loads(line)["alert_state"] for line in alert_lines)
    assert json.loads((tmp_path / "summary.json").read_text())["all_passed"] is True
    assert (
        json.loads((tmp_path / "reviewer-verdict.json").read_text())["verdict"]
        == "PASS"
    )


@pytest.mark.asyncio
async def test_replay_refuses_to_overwrite_evidence_without_force(tmp_path):
    await run(tmp_path)
    with pytest.raises(FileExistsError, match="pass --force"):
        await run(tmp_path)
