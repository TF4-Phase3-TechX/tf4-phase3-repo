import json

import pytest

from benchmark.mitigation_replay import replay


@pytest.mark.asyncio
async def test_external_replay_covers_success_and_verified_rollback(tmp_path):
    path = tmp_path / "scenarios.jsonl"
    cases = [
        {
            "id": "success",
            "service": "product-reviews",
            "expected_status": "resolved",
            "action_health": [True, True],
            "rollback_health": [],
        },
        {
            "id": "forced-wrong",
            "service": "product-reviews",
            "expected_status": "rolled_back",
            "action_health": [False, False],
            "rollback_health": [True, True],
        },
    ]
    path.write_text("\n".join(json.dumps(case) for case in cases), encoding="utf-8")

    report = await replay(path)

    assert report["all_passed"] is True
    assert report["cases"][0]["actual_status"] == "resolved"
    assert report["cases"][1]["actual_status"] == "rolled_back"
    assert report["cases"][1]["patches"][-1]["revision"] == "current"
    assert any(
        event["event"] == "rollback_verified"
        for event in report["cases"][1]["audit"]
    )


@pytest.mark.asyncio
async def test_external_replay_fails_closed_when_rollback_unhealthy(tmp_path):
    path = tmp_path / "scenario.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "rollback-unhealthy",
                "service": "product-reviews",
                "expected_status": "escalated",
                "action_health": [False],
                "rollback_health": [False],
            }
        ),
        encoding="utf-8",
    )

    report = await replay(path)

    case = report["cases"][0]
    assert case["passed"] is True
    assert case["mutation_blocked"] is True
