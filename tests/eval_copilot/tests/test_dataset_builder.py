from __future__ import annotations

import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = EVAL_DIR / "src"
for path in (EVAL_DIR, SRC_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dataset_builder import build_test_cases  # noqa: E402
from db_source import load_products_from_sql  # noqa: E402
from generate_dataset import stable_source_path  # noqa: E402


REPO_ROOT = EVAL_DIR.parents[1]
INIT_SQL = REPO_ROOT / "techx-corp-platform" / "src" / "postgresql" / "init.sql"


def _case(cases: list[dict], test_id: str) -> dict:
    return next(case for case in cases if case["test_id"] == test_id)


def test_category_price_expectations_come_from_init_sql():
    cases = build_test_cases(load_products_from_sql(str(INIT_SQL)))

    accessories = _case(cases, "TC-11")
    assert accessories["query"] == "accessories over $1000"
    assert accessories["expected_product_ids"] == ["9SIQT8TOJO"]
    assert accessories["group"] == "attribute_filter"

    no_match = _case(cases, "TC-12")
    assert no_match["query"] == "travel over $500"
    assert no_match["expected_product_ids"] == []
    assert no_match["group"] == "valid_empty_result"


def test_unresolved_comparison_requires_clarification():
    cases = build_test_cases(load_products_from_sql(str(INIT_SQL)))

    unresolved = _case(cases, "TC-60")
    assert unresolved["expected_behavior"] == "ambiguous_clarification"


def test_source_path_is_repo_relative_for_reproducible_metadata():
    assert stable_source_path(str(INIT_SQL)) == (
        "techx-corp-platform/src/postgresql/init.sql"
    )
