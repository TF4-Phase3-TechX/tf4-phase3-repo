#!/usr/bin/env sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output_root="${1:-${repo_root}/tests/eval_mandate23/evidence/${timestamp}}"
target="${MANDATE23_GRPC_TARGET:-}"
if [ -z "${target}" ] && command -v docker >/dev/null 2>&1; then
  set -- --env-file "${repo_root}/techx-corp-platform/.env"
  if [ -f "${repo_root}/techx-corp-platform/.env.override" ]; then
    set -- "$@" --env-file "${repo_root}/techx-corp-platform/.env.override"
  fi
  published_port="$(
    docker compose "$@" \
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

export BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.amazon.nova-2-lite-v1:0}"
export BEDROCK_GUARDRAIL_VERSION="${BEDROCK_GUARDRAIL_VERSION:-3}"
export BEDROCK_INPUT_USD_PER_MILLION="${BEDROCK_INPUT_USD_PER_MILLION:-0.30}"
export BEDROCK_OUTPUT_USD_PER_MILLION="${BEDROCK_OUTPUT_USD_PER_MILLION:-2.50}"

mkdir -p "${output_root}"

"${python_bin}" "${repo_root}/tests/eval_mandate23/replay.py" \
  --input "${repo_root}/tests/eval_mandate23/cases.example.jsonl" \
  --target "${target}" \
  --output-dir "${output_root}/runtime" \
  --repetitions "${MANDATE23_REPETITIONS:-3}" \
  --identity-suffix="-${timestamp}"

"${python_bin}" "${repo_root}/tests/eval_mandate23/replay.py" \
  --input "${repo_root}/tests/eval_mandate23/cases.short-term.jsonl" \
  --target "${target}" \
  --output-dir "${output_root}/short-term" \
  --repetitions "${MANDATE23_REPETITIONS:-3}" \
  --identity-suffix="-${timestamp}"

db_dsn="${MANDATE23_DB_DSN:-${DB_CONNECTION_STRING:-}}"
if [ -n "${db_dsn}" ]; then
  "${python_bin}" "${repo_root}/tests/eval_mandate23/invalidation_drill.py" \
    --db-dsn "${db_dsn}" \
    --target "${target}" \
    --user-id "mandate23-invalidation-user-${timestamp}" \
    --session-id "mandate23-invalidation-session-${timestamp}" \
    --output "${output_root}/invalidation.json"
elif [ "${MANDATE23_REQUIRE_INVALIDATION:-0}" = "1" ]; then
  echo "MANDATE23_DB_DSN or DB_CONNECTION_STRING is required for invalidation" >&2
  exit 2
else
  printf '%s\n' \
    "Invalidation skipped: set MANDATE23_DB_DSN or DB_CONNECTION_STRING." \
    >"${output_root}/invalidation-skipped.txt"
fi

echo "Mandate 23 evidence written to ${output_root}"
