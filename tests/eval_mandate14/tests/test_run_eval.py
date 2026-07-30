import json
from pathlib import Path

import pytest

from run_eval import (
    DEFAULT_CASE_SCHEMA,
    build_report,
    load_jsonl,
    require_no_semantic_truncation,
)


def valid_case(case_id="M14-SCHEMA-001"):
    return {
        "schema_version": "mandate14-case-v2",
        "case_id": case_id,
        "surface": "copilot",
        "variant": "candidate",
        "category": "multi_turn_injection",
        "human_pass": True,
        "sources": [],
        "expected": {
            "outcome": "block",
            "valid_task": False,
            "injection_present": True,
            "allowed_tools": [],
        },
        "observed": {
            "outcome": "guardrail_blocked",
            "response_text": "",
            "claims": [],
            "blocked": True,
            "tool_calls": [],
            "latency_ms": 1,
            "input_tokens": 0,
            "output_tokens": 0,
            "model_requests": 0,
            "estimated_cost_usd": 0,
        },
    }


def write_jsonl(path: Path, cases):
    path.write_text(
        "".join(json.dumps(case) + "\n" for case in cases),
        encoding="utf-8",
    )


def test_external_jsonl_validates(tmp_path):
    path = tmp_path / "cases.jsonl"
    write_jsonl(path, [valid_case()])
    loaded = load_jsonl(path, DEFAULT_CASE_SCHEMA)
    assert loaded[0]["case_id"] == "M14-SCHEMA-001"


def test_duplicate_case_id_fails_before_scoring(tmp_path):
    path = tmp_path / "cases.jsonl"
    write_jsonl(path, [valid_case(), valid_case()])
    with pytest.raises(ValueError, match="duplicate case_id"):
        load_jsonl(path, DEFAULT_CASE_SCHEMA)


def test_duplicate_source_id_fails_before_scoring(tmp_path):
    value = valid_case()
    value["sources"] = [
        {"source_id": "same", "source_type": "review", "text": "one"},
        {"source_id": "same", "source_type": "review", "text": "two"},
    ]
    path = tmp_path / "cases.jsonl"
    write_jsonl(path, [value])
    with pytest.raises(ValueError, match="duplicate source_id"):
        load_jsonl(path, DEFAULT_CASE_SCHEMA)


def test_unknown_top_level_field_is_rejected(tmp_path):
    value = valid_case()
    value["unexpected"] = True
    path = tmp_path / "cases.jsonl"
    write_jsonl(path, [value])
    with pytest.raises(ValueError, match="schema validation failed"):
        load_jsonl(path, DEFAULT_CASE_SCHEMA)


def test_report_records_dataset_hash_and_hard_bars(tmp_path):
    path = tmp_path / "cases.jsonl"
    write_jsonl(path, [valid_case()])
    raw = path.read_bytes()
    report = build_report(load_jsonl(path), raw)
    assert report["schema_version"] == "mandate14-report-v2"
    assert len(report["dataset_sha256"]) == 64
    assert report["aggregate"]["hard_bars"]["pass"]


def test_semantic_truncation_fails_closed():
    report = {
        "aggregate": {
            "semantic_faithfulness_judge": {
                "input_truncated_count": 1,
            }
        }
    }
    with pytest.raises(ValueError, match="input truncated"):
        require_no_semantic_truncation(report)
