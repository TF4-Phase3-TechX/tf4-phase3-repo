#!/usr/bin/env bash
set -euo pipefail

# Sửa environments/production/app-values.yaml (managedData.kafka block) cho đúng
# giai đoạn cutover, verify bằng helm lint/template, rồi commit+push+tạo PR.
# KHÔNG tự merge — vẫn cần review/merge tay.
#
# Usage:
#   STAGE=producer docs/cdo08/week2/mandate8/scripts/kafka/08-set-kafka-cutover-stage.sh
#   STAGE=consumer docs/cdo08/week2/mandate8/scripts/kafka/08-set-kafka-cutover-stage.sh
#   STAGE=off      docs/cdo08/week2/mandate8/scripts/kafka/08-set-kafka-cutover-stage.sh
#
# STAGE=producer -> managedData.kafka.services: [checkout]                       (Giai đoạn A / Mục C)
# STAGE=consumer -> managedData.kafka.services: [accounting, checkout, fraud-detection] (Giai đoạn B / Mục D)
# STAGE=off      -> managedData.kafka.enabled: false                             (Rollback / Mục F.1)
#
# Env vars:
#   GITOPS_DIR  đường dẫn local clone của tf4-phase3-gitops-manifests (default: ../tf4-phase3-gitops-manifests)
#   CHART_DIR   đường dẫn local techx-corp-chart (default: ./techx-corp-chart)
#   GH_REPO     repo GitOps trên GitHub (default: TF4-Phase3-TechX/tf4-phase3-gitops-manifests)

# Tự tìm thư mục gốc repo app (nơi có techx-corp-chart/) dựa vào vị trí thật của
# script, KHÔNG dựa vào thư mục đang đứng khi gọi lệnh — để chạy bằng full path
# từ bất kỳ đâu vẫn ra đúng path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../../.." && pwd)"
cd "$APP_REPO_ROOT"

STAGE="${STAGE:?Set STAGE=producer|consumer|off}"
GITOPS_DIR="${GITOPS_DIR:-../tf4-phase3-gitops-manifests}"
CHART_DIR="${CHART_DIR:-./techx-corp-chart}"
GH_REPO="${GH_REPO:-TF4-Phase3-TechX/tf4-phase3-gitops-manifests}"
APP_VALUES_REL="environments/production/app-values.yaml"

case "$STAGE" in
  producer)
    NEW_BLOCK=$'  kafka:\n    enabled: true\n    secretName: msk-kafka-secret\n    services: [checkout]'
    EXPECT_COUNT=1
    ;;
  consumer)
    NEW_BLOCK=$'  kafka:\n    enabled: true\n    secretName: msk-kafka-secret\n    services: [accounting, checkout, fraud-detection]'
    EXPECT_COUNT=3
    ;;
  off)
    NEW_BLOCK=$'  kafka:\n    enabled: false\n    secretName: msk-kafka-secret'
    EXPECT_COUNT=0
    ;;
  *)
    echo "STAGE must be producer|consumer|off" >&2
    exit 1
    ;;
esac

if [ ! -d "$GITOPS_DIR/.git" ]; then
  echo "GITOPS_DIR ($GITOPS_DIR) không phải git repo — set GITOPS_DIR đúng đường dẫn local clone." >&2
  exit 1
fi

APP_REPO_DIR="$(pwd)"

echo ">> Pull mới nhất main của gitops repo (tránh conflict với team khác)..."
(cd "$GITOPS_DIR" && git checkout main && git pull origin main)

BRANCH="cdo08-rel-17-kafka-cutover-${STAGE}"
echo ">> Tạo branch $BRANCH..."
(cd "$GITOPS_DIR" && git checkout -B "$BRANCH")

echo ">> Sửa block managedData.kafka trong $APP_VALUES_REL..."
awk -v new="$NEW_BLOCK" '
  BEGIN { in_kafka = 0 }
  /^  kafka:$/ { print new; in_kafka = 1; next }
  in_kafka && (/^  [A-Za-z]/ || /^$/) { in_kafka = 0 }
  !in_kafka { print }
' "$GITOPS_DIR/$APP_VALUES_REL" > "$GITOPS_DIR/$APP_VALUES_REL.tmp"
mv "$GITOPS_DIR/$APP_VALUES_REL.tmp" "$GITOPS_DIR/$APP_VALUES_REL"

echo ">> Verify helm lint..."
helm lint "$CHART_DIR" \
  -f "$GITOPS_DIR/environments/production/app-values.yaml" \
  -f "$GITOPS_DIR/environments/production/flagd-values.yaml" \
  -f "$GITOPS_DIR/environments/production/image-revisions.yaml"

echo ">> Verify helm template — đếm số service nhận KAFKA_SECURITY_PROTOCOL..."
ACTUAL_COUNT=$(helm template techx-corp "$CHART_DIR" \
  -f "$GITOPS_DIR/environments/production/app-values.yaml" \
  -f "$GITOPS_DIR/environments/production/flagd-values.yaml" \
  -f "$GITOPS_DIR/environments/production/image-revisions.yaml" \
  | grep -c "KAFKA_SECURITY_PROTOCOL" || true)

if [ "$ACTUAL_COUNT" != "$EXPECT_COUNT" ]; then
  echo "!! Render sai: kỳ vọng $EXPECT_COUNT lần KAFKA_SECURITY_PROTOCOL, ra $ACTUAL_COUNT." >&2
  echo "!! KHÔNG commit — kiểm tra lại cấu trúc app-values.yaml (có thể team khác đã đổi block managedData)." >&2
  (cd "$GITOPS_DIR" && git checkout -- "$APP_VALUES_REL")
  exit 1
fi
echo "OK: $ACTUAL_COUNT == $EXPECT_COUNT"

cd "$GITOPS_DIR"
git add "$APP_VALUES_REL"
git commit -m "CDO08-REL-17 Kafka cutover stage: ${STAGE}"
git push -u origin "$BRANCH"

gh pr create --repo "$GH_REPO" --base main --head "$BRANCH" \
  --title "feat(gitops): [CDO08-REL-17] Kafka cutover stage: ${STAGE}" \
  --body "Tự động tạo bởi 08-set-kafka-cutover-stage.sh (STAGE=${STAGE}). Đã verify helm lint/template (${ACTUAL_COUNT} service nhận KAFKA_SECURITY_PROTOCOL). Review diff rồi merge tay — script không tự merge." \
  || gh pr edit "$BRANCH" --repo "$GH_REPO" \
       --title "feat(gitops): [CDO08-REL-17] Kafka cutover stage: ${STAGE}"

cd "$APP_REPO_DIR"
echo ">> Xong. PR đã tạo/cập nhật cho branch $BRANCH — review rồi tự merge."
