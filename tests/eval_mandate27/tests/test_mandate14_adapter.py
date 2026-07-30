from datetime import datetime, timezone

from tests.eval_mandate27.adapters.mandate14 import convert_reports


def test_mandate14_result_converts_without_raw_content():
    report = {
        "per_case": [
            {
                "case_id": "case-1",
                "surface": "review_summary",
                "grounding": {
                    "faithfulness": 0.10,
                    "semantic_faithfulness": 0.75,
                },
                "abstention": {"observed": False},
            },
            {
                "case_id": "case-2",
                "surface": "copilot",
                "grounding": {"semantic_faithfulness": None},
                "abstention": {"observed": True},
            },
        ]
    }

    rows = convert_reports(
        [report],
        model_id="model-v1",
        guardrail_version="3",
        started_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
    )

    assert rows[0]["metrics"] == {"abstained": 0, "faithfulness": 0.75}
    assert rows[1]["metrics"] == {"abstained": 1}
    assert "response" not in str(rows)


def test_mandate14_adapter_never_substitutes_lexical_for_semantic():
    report = {
        "per_case": [
            {
                "case_id": "case-1",
                "surface": "review_summary",
                "grounding": {
                    "faithfulness": 1.0,
                    "semantic_faithfulness": 0.0,
                },
                "abstention": {"observed": False},
            }
        ]
    }

    rows = convert_reports(
        [report],
        model_id="model-v1",
        guardrail_version="3",
    )

    assert rows[0]["metrics"]["faithfulness"] == 0.0


def test_semantic_adapter_fails_closed_for_lexical_only_report():
    report = {
        "per_case": [
            {
                "case_id": "case-1",
                "surface": "review_summary",
                "grounding": {"faithfulness": 1.0},
                "abstention": {"observed": False},
            }
        ]
    }

    try:
        convert_reports(
            [report],
            model_id="model-v1",
            guardrail_version="3",
        )
    except ValueError as error:
        assert "semantic_faithfulness" in str(error)
    else:
        raise AssertionError("lexical-only report must fail closed")
