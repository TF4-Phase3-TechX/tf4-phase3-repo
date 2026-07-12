#!/usr/bin/env bash
# Local-only check for the rendered load-generator deployment.
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Usage: $0 <rendered-manifest.yaml>" >&2
  exit 64
fi

if [[ -n "${PYTHON:-}" ]]; then
  python_cmd=("$PYTHON")
elif command -v python3 >/dev/null 2>&1; then
  python_cmd=(python3)
elif command -v py >/dev/null 2>&1; then
  python_cmd=(py -3)
else
  echo "Python 3 is required (set PYTHON if it is not on PATH)." >&2
  exit 69
fi

"${python_cmd[@]}" - "$1" <<'PY'
from pathlib import Path
import re
import sys

content = Path(sys.argv[1]).read_text(encoding="utf-8")
documents = re.split(r"(?m)^---\s*$", content)

deployments = [
    document for document in documents
    if re.search(r"(?m)^kind:\s*Deployment\s*$", document)
    and re.search(r"(?m)^  name:\s*load-generator\s*$", document)
]
if len(deployments) != 1:
    raise SystemExit(f"Expected one load-generator Deployment; found {len(deployments)}.")

matches = re.findall(
    r"(?m)^        - name:\s*LOCUST_AUTOSTART\s*$\n^          value:\s*(.+?)\s*$",
    deployments[0],
)
if matches != ['"false"']:
    raise SystemExit(f'Expected one LOCUST_AUTOSTART="false"; found {matches}.')

print('Verified load-generator LOCUST_AUTOSTART="false".')
PY
