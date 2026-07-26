#!/usr/bin/env sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output_dir="${1:-${repo_root}/tests/eval_mandate23/evidence/${timestamp}}"
target="${MANDATE23_GRPC_TARGET:-}"
if [ -z "${target}" ] && command -v docker >/dev/null 2>&1; then
  published_port="$(
    docker compose \
      --env-file "${repo_root}/techx-corp-platform/.env" \
      --env-file "${repo_root}/techx-corp-platform/.env.override" \
      -f "${repo_root}/techx-corp-platform/docker-compose.yml" \
      port product-reviews 3551 2>/dev/null |
      awk -F: 'NR == 1 { print $NF }'
  )"
  if [ -n "${published_port}" ]; then
    target="localhost:${published_port}"
  fi
fi
target="${target:-localhost:3551}"
python_bin="${MANDATE23_PYTHON:-${repo_root}/techx-corp-platform/src/product-reviews/venv/bin/python}"
if [ ! -x "${python_bin}" ]; then
  python_bin=python3
fi

exec "${python_bin}" "${repo_root}/tests/eval_mandate23/replay.py" \
  --input "${repo_root}/tests/eval_mandate23/cases.example.jsonl" \
  --target "${target}" \
  --output-dir "${output_dir}" \
  --repetitions "${MANDATE23_REPETITIONS:-3}" \
  --identity-suffix="-${timestamp}"
