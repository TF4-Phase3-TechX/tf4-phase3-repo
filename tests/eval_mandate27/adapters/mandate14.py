"""Convert one or more Mandate 14 reports into Mandate 27 observations."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..common import write_jsonl
from ..contract import validate
from ..surface_mapping import canonical_surface


def convert_reports(
    reports: list[dict[str, Any]],
    *,
    model_id: str,
    guardrail_version: str,
    scorer_version: str = "mandate14-semantic-v3",
    started_at: datetime | None = None,
) -> list[dict[str, Any]]:
    current = started_at or datetime.now(timezone.utc)
    rows = []
    for report_index, report in enumerate(reports):
        per_case = report.get("per_case")
        if not isinstance(per_case, list) or not per_case:
            raise ValueError("Mandate 14 report must contain non-empty per_case")
        for case_index, result in enumerate(per_case):
            metrics: dict[str, Any] = {
                "abstained": int(bool(result["abstention"]["observed"])),
            }
            grounding = result["grounding"]
            if scorer_version == "mandate14-lexical-v2":
                faithfulness = grounding.get("faithfulness")
            else:
                if (
                    "semantic_faithfulness" not in grounding
                    and "faithfulness" in grounding
                ):
                    raise ValueError(
                        "semantic scorer requires "
                        "grounding.semantic_faithfulness; refusing lexical "
                        "faithfulness substitution"
                    )
                faithfulness = grounding.get("semantic_faithfulness")
            if faithfulness is not None:
                metrics["faithfulness"] = float(faithfulness)
            row = {
                "schema_version": "mandate27-observation-v1",
                "event_id": (
                    f"m14-{report_index:03d}-{case_index:04d}-"
                    f"{result['case_id']}"
                ),
                "observed_at": current.isoformat().replace("+00:00", "Z"),
                "surface": canonical_surface(result["surface"]),
                "model_id": model_id,
                "guardrail_version": guardrail_version,
                "scorer_version": scorer_version,
                "metrics": metrics,
            }
            validate(row, "observation.schema.json")
            rows.append(row)
            current += timedelta(seconds=1)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--guardrail-version", required=True)
    parser.add_argument(
        "--scorer-version", default="mandate14-semantic-v3"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.reports
    ]
    rows = convert_reports(
        reports,
        model_id=args.model_id,
        guardrail_version=args.guardrail_version,
        scorer_version=args.scorer_version,
    )
    write_jsonl(args.output, rows)
    print(f"output={args.output} observations={len(rows)}")


if __name__ == "__main__":
    main()
