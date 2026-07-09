#!/usr/bin/env bash
# Build 17 app image single-arch (amd64) từ source và push lên ECR.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../techx-corp-platform"
[ -f .env.override ] || { echo "missing .env.override"; exit 1; }
echo ">> IMAGE_NAME: $(grep IMAGE_NAME .env.override)"

# Nạp các biến môi trường từ .env và .env.override
set -a
[ -f .env ] && . .env
. .env.override
set +a

# Danh sách dịch vụ trong compose cần build và push
SERVICES=(
  accounting
  ad
  cart
  checkout
  currency
  email
  fraud-detection
  frontend
  frontend-proxy
  image-provider
  load-generator
  payment
  product-catalog
  product-reviews
  quote
  recommendation
  shipping
  # flagd-ui is intentionally skipped: it is not used by the current Helm release.
  # flagd-ui
  kafka
  opensearch
  llm
)

echo ">> Bắt đầu build & push tuần tự để tối ưu tài nguyên, tránh tràn RAM..."
for SERVICE in "${SERVICES[@]}"; do
  echo "=========================================="
  echo ">> Đang xử lý dịch vụ: $SERVICE"
  echo "=========================================="
  # Biên dịch và nạp vào local Docker daemon
  docker buildx bake -f docker-compose.yml --load --set "*.platform=linux/amd64" "$SERVICE"
  
  # Đẩy ảnh lên AWS ECR bằng lệnh push gốc của Docker
  echo ">> Đẩy ảnh lên ECR: $IMAGE_NAME:$DEMO_VERSION-$SERVICE"
  docker push "$IMAGE_NAME:$DEMO_VERSION-$SERVICE"
done

echo "TẤT CẢ ĐÃ HOÀN THÀNH -> https://us-east-1.console.aws.amazon.com/ecr/repositories/private/511825856493/techx-corp?region=us-east-1"
