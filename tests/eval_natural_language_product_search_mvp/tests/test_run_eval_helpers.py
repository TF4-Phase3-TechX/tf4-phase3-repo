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

from run_eval import get_database_hash, load_env_override


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
