from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class RunbookCatalog:
    def __init__(self, path: str | None = None):
        default = Path(__file__).resolve().parent.parent / "runbooks.yaml"
        source = Path(path or os.getenv("AIOPS_RUNBOOK_PATH", str(default)))
        content = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        self.items: dict[str, dict[str, Any]] = {
            item["id"]: item for item in content.get("runbooks", []) if isinstance(item, dict) and item.get("id")
        }

    def action_for(self, runbook_id: str) -> str | None:
        item = self.items.get(runbook_id)
        if item is None:
            raise ValueError(f"Unknown runbook: {runbook_id}")
        return item.get("automatic_action")
