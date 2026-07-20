#!/usr/bin/env bash
# Build selected app images single-arch (amd64) and push them to ECR.
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
  docker buildx bake -f docker-compose.yml --load --set "*.platform=linux/amd64" "$SERVICE"
  docker push "$IMAGE_NAME:$DEMO_VERSION-$SERVICE"
done

echo ">> Selected image push complete"
