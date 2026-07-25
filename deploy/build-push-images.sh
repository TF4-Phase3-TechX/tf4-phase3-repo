#!/usr/bin/env bash
# Build selected app images for AMD64 and ARM64 and publish OCI indexes to ECR.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../techx-corp-platform"
[ -f .env.override ] || { echo "missing .env.override"; exit 1; }
[ "$#" -gt 0 ] || { echo "usage: $0 SERVICE [SERVICE...]" >&2; exit 2; }
echo ">> IMAGE_NAME: $(grep IMAGE_NAME .env.override)"

set -a
[ -f .env ] && . .env
. .env.override
set +a

for SERVICE in "$@"; do
  docker buildx bake -f docker-compose.yml --print "$SERVICE" >/dev/null || {
    echo "unknown or invalid build target: $SERVICE" >&2
    exit 2
  }
  echo ">> Building and pushing: $SERVICE"
  docker buildx bake -f docker-compose.yml \
    --push \
    --set "*.platform=linux/amd64,linux/arm64" \
    "$SERVICE"
done

echo ">> Selected image push complete"
