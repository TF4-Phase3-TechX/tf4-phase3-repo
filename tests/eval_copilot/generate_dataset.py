"""
generate_dataset.py — CLI that ties db_source + dataset_builder together
to produce eval_dataset.json.

Usage:
    python generate_dataset.py --source sql \
        --sql-file /path/to/init.sql
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as a script from the package directory.
_SCRIPT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _SCRIPT_DIR / "src"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from db_source import load_products_from_sql  # noqa: E402
from dataset_builder import build_test_cases  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the evaluation dataset (eval_dataset.json)."
    )
    parser.add_argument(
        "--source",
        choices=["sql", "db"],
        default="sql",
        help="Data source type (default: sql).",
    )
    parser.add_argument(
        "--sql-file",
        type=str,
        default=None,
        help="Path to the init.sql file (required when --source=sql).",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------ #
    # 1. Load products                                                    #
    # ------------------------------------------------------------------ #
    if args.source == "sql":
        if not args.sql_file:
            parser.error("--sql-file is required when --source=sql")
        products = load_products_from_sql(args.sql_file)
    else:
        parser.error("--source=db is not yet implemented.")

    print(f"Loaded {len(products)} products from {args.source} source.")

    # ------------------------------------------------------------------ #
    # 2. Build test cases                                                 #
    # ------------------------------------------------------------------ #
    test_cases = build_test_cases(products)
    print(f"Built {len(test_cases)} test cases.")

    # ------------------------------------------------------------------ #
    # 3. Compute dataset hash (over test_cases only, not _meta)           #
    # ------------------------------------------------------------------ #
    tc_json = json.dumps(test_cases, sort_keys=True, ensure_ascii=False)
    dataset_sha256 = hashlib.sha256(tc_json.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------ #
    # 4. Assemble output                                                  #
    # ------------------------------------------------------------------ #
    output = {
        "test_cases": test_cases,
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_file": str(Path(args.sql_file).resolve()) if args.sql_file else None,
            "product_count": len(products),
            "dataset_sha256": dataset_sha256,
        },
    }

    out_path = _SCRIPT_DIR / "eval_dataset.json"
    out_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Dataset written to {out_path}")

    # ------------------------------------------------------------------ #
    # 5. Summary                                                          #
    # ------------------------------------------------------------------ #
    group_counts: dict[str, int] = {}
    for tc in test_cases:
        group_counts[tc["group"]] = group_counts.get(tc["group"], 0) + 1

    print("\n--- Summary ---")
    print(f"Total test cases : {len(test_cases)}")
    print(f"SHA-256          : {dataset_sha256}")
    for group, count in sorted(group_counts.items()):
        print(f"  {group:20s}: {count}")


if __name__ == "__main__":
    main()
