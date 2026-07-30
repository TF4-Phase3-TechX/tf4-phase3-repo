import json

import pytest

from benchmark.mitigation_replay import replay


@pytest.mark.asyncio
async def test_external_replay_covers_success_and_forced_wrong_compensation(tmp_path):
    path = tmp_path / "scenarios.jsonl"
    cases = [
        {
            "id": "success",
            "expected_outcome": "resolved",
            "action_health": [True, True, True],
        },
        {
            "id": "forced-wrong",
            "expected_outcome": "compensated_escalated",
            "action_health": [False, False, False],
        },
    ]
    path.write_text("\n".join(json.dumps(case) for case in cases), encoding="utf-8")
    report = await replay(path)
    assert report["all_passed"] is True
    forced = report["cases"][1]
    assert forced["mutation_blocked"] is True
    assert [item["event"] for item in forced["timeline"]].count("pr_open") == 2
    assert "/compensation/" in forced["timeline"][-2]["branch"]


@pytest.mark.asyncio
async def test_external_replay_covers_compensation_failure_escalation(tmp_path):
    path = tmp_path / "scenario.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "compensation-failure",
                "expected_outcome": "compensation_failed",
                "action_health": [False],
                "compensation_runtime_healthy": False,
                "runtime_timeout_seconds": 0.001,
            }
        ),
        encoding="utf-8",
    )
    report = await replay(path)
    case = report["cases"][0]
    assert case["passed"] is True
    assert case["mutation_blocked"] is True
