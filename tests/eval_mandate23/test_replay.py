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


def test_validate_expectations_checks_memory_text_and_product_referent():
    case = {
        "expect": {
            "cache": "miss",
            "memory_status": "recalled",
            "outcome": "memory_recalled",
            "response_contains": "telescopes",
            "response_not_contains": "books",
            "result_product_ids": ["p1"],
        }
    }
    observation = {
        "cache": "miss",
        "memory_status": "recalled",
        "response": {
            "outcome": "memory_recalled",
            "response": "Stored preferences: telescopes.",
            "results": [{"id": "p1"}],
        },
    }

    checked, errors = replay.validate_expectations(case, observation)

    assert checked == 6
    assert errors == []


def test_validate_expectations_reports_semantic_failures():
    case = {
        "expect": {
            "cache": "hit",
            "memory_status": "not_found",
            "response_not_contains": "telescopes",
            "result_product_ids_contains": ["expected-product"],
        }
    }
    observation = {
        "cache": "miss",
        "memory_status": "recalled",
        "response": {
            "response": "Stored preferences: telescopes.",
            "results": [{"id": "wrong-product"}],
        },
    }

    checked, errors = replay.validate_expectations(case, observation)

    assert checked == 4
    assert len(errors) == 4
    assert any("cache" in error for error in errors)
    assert any("expected-product" in error for error in errors)


def test_aggregate_excludes_semantic_assertion_failures():
    rows = [
        {
            "surface": "copilot",
            "cache": "miss",
            "latency_ms": 10,
            "assertions": {"status": "passed", "checked": 2},
        },
        {
            "surface": "copilot",
            "cache": "hit",
            "latency_ms": 5,
            "assertions": {"status": "failed", "checked": 2},
            "error": "AssertionError",
        },
    ]

    result = replay.aggregate(rows)["groups"]["copilot"]

    assert result["successful_cases"] == 1
    assert result["failed_cases"] == 1
    assert result["validated_cases"] == 2
    assert result["assertion_failures"] == 1
    assert result["cache_hits"] == 0


def test_run_case_marks_semantic_assertion_failure_as_error():
    class Stub:
        def SearchProductsAIAssistant(self, _request, timeout):
            assert timeout == 2
            return replay.demo_pb2.SearchProductsAIAssistantResponse(
                response="No stored preferences.",
                outcome="memory_not_found",
                cache_status="miss",
                memory_status="not_found",
            )

    row = replay.run_case(
        Stub(),
        {
            "case_id": "semantic-failure",
            "surface": "copilot",
            "request": {"query": "Show what you remember"},
            "user_id": "user-a",
            "session_id": "session-a",
            "expect": {
                "memory_status": "recalled",
                "response_contains": "telescopes",
            },
        },
        timeout_seconds=2,
        default_product_id="",
    )

    assert row["assertions"] == {"status": "failed", "checked": 2}
    assert row["error"] == "AssertionError"
    assert "memory_status" in row["error_message"]
