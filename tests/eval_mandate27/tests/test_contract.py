import json
from pathlib import Path

import pytest

from tests.eval_mandate27.contract import load_observations
from tests.eval_mandate27.generate_fixtures import build_series


def write_rows(path: Path, rows):
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_external_contract_accepts_content_free_series(tmp_path):
    path = tmp_path / "series.jsonl"
    rows = build_series("stable", samples_per_surface=2)
    write_rows(path, rows)

    assert load_observations(path) == rows


def test_external_contract_rejects_unknown_content_field(tmp_path):
    path = tmp_path / "series.jsonl"
    rows = build_series("stable", samples_per_surface=1)
    rows[0]["prompt"] = "must never be accepted"
    write_rows(path, rows)

    with pytest.raises(ValueError, match="Additional properties"):
        load_observations(path)


def test_external_contract_rejects_duplicate_identity(tmp_path):
    path = tmp_path / "series.jsonl"
    rows = build_series("stable", samples_per_surface=2)
    rows[1]["event_id"] = rows[0]["event_id"]
    write_rows(path, rows)

    with pytest.raises(ValueError, match="duplicate event_id"):
        load_observations(path)


def test_external_contract_rejects_out_of_order_timestamp(tmp_path):
    path = tmp_path / "series.jsonl"
    rows = build_series("stable", samples_per_surface=2)
    rows[-1]["observed_at"] = "2020-01-01T00:00:00Z"
    write_rows(path, rows)

    with pytest.raises(ValueError, match="non-decreasing"):
        load_observations(path)

