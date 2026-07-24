"""Make the standalone Mandate 14 scorer importable from repository-root pytest."""

from __future__ import annotations

import sys
from pathlib import Path


SCORER_DIR = Path(__file__).resolve().parents[1]
if str(SCORER_DIR) not in sys.path:
    sys.path.insert(0, str(SCORER_DIR))
