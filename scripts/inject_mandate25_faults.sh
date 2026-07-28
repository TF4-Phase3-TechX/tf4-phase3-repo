#!/usr/bin/env bash
set -euo pipefail

# Application-owned Mandate 25 control. This never edits or publishes flagd.
# Port-forward product-reviews first, export the dedicated control token, then:
#   ./scripts/inject_mandate25_faults.sh throttling -- <replay command...>

TARGET="${MANDATE25_TARGET:-127.0.0.1:3551}"
TTL_SECONDS="${MANDATE25_FAULT_TTL_SECONDS:-60}"
TOKEN="${MANDATE25_FAULT_TOKEN:-}"
CONTROL_PATH="/tf4.mandate25.ResilienceControl"

if [[ -z "${TOKEN}" ]]; then
  echo "MANDATE25_FAULT_TOKEN is required" >&2
  exit 2
fi

rpc() {
  local method="$1"
  local payload="$2"
  python3 - "${TARGET}" "${TOKEN}" "${CONTROL_PATH}/${method}" "${payload}" <<'PY'
import grpc
import json
import sys

target, token, method, raw_payload = sys.argv[1:]
channel = grpc.insecure_channel(target)
try:
    call = channel.unary_unary(
        method,
        request_serializer=lambda value: json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"),
        response_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    response = call(
        json.loads(raw_payload),
        timeout=5,
        metadata=(("x-mandate25-token", token),),
    )
    print(json.dumps(response, sort_keys=True))
finally:
    channel.close()
PY
}

status() {
  rpc "GetStatus" "{}"
}

restore() {
  rpc "SetFault" '{"mode":"off","ttl_seconds":0}' >/dev/null || true
  status || true
}

mode="${1:-}"
case "${mode}" in
  status)
    status
    exit 0
    ;;
  recover)
    restore
    exit 0
    ;;
  timeout|throttling|provider_5xx|malformed_output)
    ;;
  *)
    echo "usage: $0 {timeout|throttling|provider_5xx|malformed_output} -- <replay command...>" >&2
    echo "       $0 {status|recover}" >&2
    exit 2
    ;;
esac

if [[ "${2:-}" != "--" || "$#" -lt 3 ]]; then
  echo "a bounded replay command is required after --" >&2
  exit 2
fi
shift 2

trap restore EXIT INT TERM
rpc "SetFault" "{\"mode\":\"${mode}\",\"ttl_seconds\":${TTL_SECONDS}}"
status
"$@"
