#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
dataset="${1:-${repo_root}/tests/eval_mandate14/public-cases-v1.jsonl}"
output_dir="${2:-/tmp/mandate14-public-evidence}"
product_reviews_target="${PRODUCT_REVIEWS_TARGET:-localhost:3550}"
cart_target="${CART_TARGET:-localhost:7070}"
python_bin="${PYTHON_BIN:-python3}"

args=(
  "${repo_root}/tests/eval_mandate14/run_harness.py"
  --dataset "${dataset}"
  --output-dir "${output_dir}"
  --product-reviews-target "${product_reviews_target}"
  --cart-target "${cart_target}"
  --runtime-env "${MANDATE14_RUNTIME_ENV:-local}"
)
if [[ "${MANDATE14_CERTIFY:-0}" == "1" ]]; then
  args+=(--require-clean-git)
fi

"${python_bin}" "${args[@]}"
printf 'Mandate 14 runtime evidence: %s\n' "${output_dir}"
