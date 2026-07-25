#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
input_path="${1:-${repo_root}/tests/eval_mandate14/labeled-observations-v2.jsonl}"
output_path="${2:-/tmp/mandate14-calibration-report.json}"
python_bin="${PYTHON_BIN:-python3}"

args=(
  "${repo_root}/tests/eval_mandate14/run_eval.py"
  --input "${input_path}"
  --output "${output_path}"
  --require-calibration
)
if [[ "${MANDATE14_CERTIFY:-0}" == "1" ]]; then
  args+=(--require-clean-git --require-all-pass)
fi

"${python_bin}" "${args[@]}"
printf 'Mandate 14 report: %s\n' "${output_path}"
