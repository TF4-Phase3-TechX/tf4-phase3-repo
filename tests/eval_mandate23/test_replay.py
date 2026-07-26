import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("replay.py")
SPEC = importlib.util.spec_from_file_location("mandate23_replay", MODULE_PATH)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def test_aggregate_reports_real_hit_latency_and_cost_groups():
    rows = [
        {
            "surface": "product_qa",
            "cache": "miss",
            "latency_ms": 100,
            "model_calls": 1,
            "input_tokens": 50,
            "output_tokens": 10,
            "estimated_cost_usd": 0.001,
        },
        {
            "surface": "product_qa",
            "cache": "hit",
            "latency_ms": 10,
            "model_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0,
        },
    ]

    result = replay.aggregate(rows)["groups"]["product_qa"]

    assert result["hit_rate"] == 0.5
    assert result["latency_ms"]["miss_mean"] == 100
    assert result["latency_ms"]["hit_mean"] == 10
    assert result["model_calls"] == 1
    assert result["estimated_cost_usd"] == 0.001


def test_materialize_cases_repeats_complete_sequences_with_fresh_identities():
    cases = [
        {
            "case_id": "cold",
            "user_id": "user",
            "session_id": "session",
            "request": {"question": "reviews"},
        },
        {
            "case_id": "warm",
            "user_id": "user",
            "session_id": "session",
            "request": {"question": "reviews"},
        },
    ]

    result = replay.materialize_cases(
        cases,
        repetitions=2,
        identity_suffix="-run-123",
    )

    assert [case["case_id"] for case in result] == [
        "cold-r1",
        "warm-r1",
        "cold-r2",
        "warm-r2",
    ]
    assert result[0]["user_id"] == result[1]["user_id"] == "user-run-123-r1"
    assert result[2]["session_id"] == result[3]["session_id"] == (
        "session-run-123-r2"
    )
