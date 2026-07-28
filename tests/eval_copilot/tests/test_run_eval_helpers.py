#!/usr/bin/env python3
"""
test_run_eval_helpers.py — Unit tests for evaluation framework helper functions,
verifying security secret filtering, config source integrity tracking, and graceful degradation.
"""

import os
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_EVAL_DIR = _TESTS_DIR.parent
_REPO_DIR = _EVAL_DIR.parent.parent

if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))
if str(_EVAL_DIR / "src") not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR / "src"))

from run_eval import (
    generate_report,
    generate_run_readme,
    get_database_hash,
    load_env_override,
)


def test_load_env_override_filters_secrets(tmp_path):
    """Verify load_env_override strictly whitelists safe config keys and excludes secrets."""
    env_override_file = tmp_path / ".env.override"
    env_override_file.write_text(
        "BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0\n"
        "BEDROCK_GUARDRAIL_ID=guardrail-123\n"
        "AWS_REGION=us-east-1\n"
        "AWS_ACCESS_KEY_ID=MOCK_AWS_ACCESS_KEY_ID_12345\n"
        "AWS_SECRET_ACCESS_KEY=MOCK_AWS_SECRET_ACCESS_KEY_67890\n"
        "DATABASE_PASSWORD=super-secret-password-123\n"
        "API_SECRET_TOKEN=xyz987secret\n",
        encoding="utf-8",
    )

    env_config, config_source = load_env_override(override_path=env_override_file)

    # Assert whitelist fields are present
    assert env_config["BEDROCK_MODEL_ID"] == "us.amazon.nova-2-lite-v1:0"
    assert env_config["BEDROCK_GUARDRAIL_ID"] == "guardrail-123"
    assert env_config["AWS_REGION"] == "us-east-1"
    assert config_source == "env_override"

    # Assert secret fields are STRICTLY EXCLUDED
    assert "AWS_ACCESS_KEY_ID" not in env_config
    assert "AWS_SECRET_ACCESS_KEY" not in env_config
    assert "DATABASE_PASSWORD" not in env_config
    assert "API_SECRET_TOKEN" not in env_config


def test_load_env_override_tracks_fallback_source(tmp_path):
    """Verify load_env_override flags fallback source when .env.override is missing."""
    example_file = tmp_path / ".env.override.example"
    example_file.write_text(
        "BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0\n"
        "BEDROCK_GUARDRAIL_ID=disabled\n",
        encoding="utf-8",
    )

    missing_override = tmp_path / ".env.override"

    env_config, config_source = load_env_override(
        override_path=missing_override, example_path=example_file
    )

    assert env_config["BEDROCK_MODEL_ID"] == "us.amazon.nova-2-lite-v1:0"
    assert config_source == "env_override_example (FALLBACK - NOT PRODUCTION)"


def test_get_database_hash_valid_file(tmp_path):
    """Verify get_database_hash returns sha256 hex digest for existing SQL file."""
    sql_file = tmp_path / "init.sql"
    sql_file.write_text("CREATE TABLE products (id TEXT PRIMARY KEY);", encoding="utf-8")

    db_hash = get_database_hash(sql_file_path=sql_file)
    assert len(db_hash) == 64
    assert db_hash != "unavailable"


def test_get_database_hash_missing_file_graceful_degradation(tmp_path):
    """Verify get_database_hash returns 'unavailable' gracefully when SQL file is missing."""
    missing_sql = tmp_path / "non_existent_init.sql"

    db_hash = get_database_hash(sql_file_path=missing_sql)
    assert db_hash == "unavailable"


def test_run_readme_has_no_trailing_whitespace(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    dataset_path = tmp_path / "eval_dataset.json"
    dataset_path.write_text("{}\n", encoding="utf-8")
    evidence_data = {
        "timestamp_utc": "2026-07-24T00:00:00+00:00",
        "git_sha": "abc123",
        "model_id": "test-model",
        "runtime_env": "local",
        "config_source": "environment",
        "summary": {
            "total_cases": 0,
            "passed_cases": 0,
            "failed_cases": 0,
            "pass_rate": 0.0,
        },
        "results": [],
    }

    generate_run_readme(
        run_dir,
        dataset_path,
        "dataset-hash",
        "database-hash",
        "python run_eval.py",
        evidence_data,
        0.0,
        0.0,
    )

    lines = (run_dir / "README.md").read_text(encoding="utf-8").splitlines()
    assert all(line == line.rstrip() for line in lines)


def test_report_observations_are_derived_from_latest_results(tmp_path):
    evidence_dir = tmp_path / "evidence"
    run_dir = evidence_dir / "run"
    run_dir.mkdir(parents=True)
    report_path = tmp_path / "report.md"

    def result(test_id, *, actual_ids=None, refused=False):
        return {
            "test_id": test_id,
            "group": "regression",
            "query": test_id,
            "expected_product_ids": actual_ids or [],
            "expected_behavior": "cart_action_proposal"
            if test_id == "TC-51"
            else "refuse_injection",
            "actual_product_ids": actual_ids or [],
            "actual_refused": refused,
            "refusal_reason": "guardrail_blocked" if refused else "",
            "input_tokens": 1,
            "output_tokens": 1,
            "estimated_cost_usd": 0.0,
            "passed": True,
            "reason": "pass",
            "details": {},
        }

    results = [
        result("TC-34", refused=True),
        result("TC-46", refused=True),
        result("TC-47", refused=True),
        result("TC-51", actual_ids=["6E92ZMYYFZ"]),
    ]
    evidence = {
        "timestamp_utc": "2026-07-24T00:00:00+00:00",
        "git_sha": "abc123",
        "database_sha256": "db-hash",
        "dataset_sha256": "dataset-hash",
        "runtime_env": "local",
        "model_id": "test-model",
        "config_source": "environment",
        "summary": {
            "total_cases": 4,
            "passed_cases": 4,
            "failed_cases": 0,
            "pass_rate": 1.0,
            "total_input_tokens": 4,
            "total_output_tokens": 4,
            "total_estimated_cost_usd": 0.0,
        },
        "results": results,
    }
    (run_dir / "results.json").write_text(
        __import__("json").dumps(evidence), encoding="utf-8"
    )

    generate_report(evidence_dir, report_path)

    report = report_path.read_text(encoding="utf-8")
    assert "all 4 cases passed" in report
    assert "`6E92ZMYYFZ`" in report
    assert "The ten remaining failures" not in report
    assert "1YMWWN1N4O" not in report
