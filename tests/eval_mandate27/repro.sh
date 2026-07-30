#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
output_dir="${1:-/tmp/mandate27-evidence}"
python_bin="${PYTHON_BIN:-python3}"

cd "${repo_root}"
mkdir -p "${output_dir}"
"${python_bin}" -m pytest -q tests/eval_mandate27/tests \
  | tee "${output_dir}/pytest.txt"
"${python_bin}" -m tests.eval_mandate27.evidence --output-dir "${output_dir}"
