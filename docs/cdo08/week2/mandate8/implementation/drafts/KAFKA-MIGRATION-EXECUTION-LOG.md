# Kafka Migration Execution Log

Ngày ghi nhận: 2026-07-20

Task liên quan: `[CDO08-REL-17][P0][Kafka] Migrate event flow to MSK and verify producer consumer parity`

## Tóm tắt ngắn

Đã chuẩn bị phần **MirrorMaker2 trong app repo** theo `KAFKA-MIGRATION-PLAN.md`.

Các thay đổi này **chưa bật migration runtime** vì `mirrormaker2.enabled=false` mặc định. Nghĩa là PR này chỉ thêm khả năng render MirrorMaker2 và script hỗ trợ; production chưa chạy MirrorMaker2 cho tới khi GitOps values bật flag trong bước sau.

## Vì sao cần làm

Plan yêu cầu dùng Strimzi `KafkaMirrorMaker2` để sync event từ Kafka self-hosted sang MSK trước khi cutover producer/consumer.

Muốn làm được bước đó thì app repo cần có:

- Helm template render được `KafkaMirrorMaker2`.
- Values mặc định an toàn, chưa bật khi chưa được duyệt.
- Scripts để verify connectivity, deploy/render, monitor lag, promote rollout và rollback.

## File đã thêm hoặc sửa

### Helm chart

```text
techx-corp-chart/templates/mirrormaker2.yaml
techx-corp-chart/values.yaml
techx-corp-chart/values.schema.json
```

Ý nghĩa:

- `mirrormaker2.yaml`: tạo Strimzi `KafkaMirrorMaker2` manifest khi bật `mirrormaker2.enabled=true`.
- `values.yaml`: thêm cấu hình mặc định cho MirrorMaker2, nhưng để `enabled=false`.
- `values.schema.json`: cho phép chart nhận key `mirrormaker2` mà không fail schema validation.

### Scripts theo plan

```text
docs/cdo08/week2/mandate8/scripts/kafka/01-verify-msk-connectivity.sh
docs/cdo08/week2/mandate8/scripts/kafka/02-deploy-mirrormaker2.sh
docs/cdo08/week2/mandate8/scripts/kafka/03-monitor-mm2-lag.sh
docs/cdo08/week2/mandate8/scripts/kafka/04-promote-producers.sh
docs/cdo08/week2/mandate8/scripts/kafka/05-verify-catchup.sh
docs/cdo08/week2/mandate8/scripts/kafka/06-promote-consumers.sh
docs/cdo08/week2/mandate8/scripts/kafka/07-cleanup.sh
docs/cdo08/week2/mandate8/scripts/kafka/rollback-01-abort-rollout.sh
docs/cdo08/week2/mandate8/scripts/kafka/rollback-02-reset-offsets.sh
```

Ý nghĩa:

- `01`: kiểm tra pod trong cluster connect được tới MSK brokers.
- `02`: render MirrorMaker2 manifest để chuẩn bị deploy qua GitOps.
- `03`: xem trạng thái/log MirrorMaker2.
- `04`: promote rollout producer `checkout`.
- `05`: kiểm tra catch-up/lag trước khi chuyển consumers.
- `06`: promote rollout consumers `accounting` và `fraud-detection`.
- `07`: nhắc cleanup phải qua GitOps và không xóa Kafka self-hosted sớm.
- `rollback-01`: abort rollout khi cần rollback.
- `rollback-02`: dry-run reset offsets trên Kafka self-hosted.

## Cấu hình an toàn

MirrorMaker2 mặc định đang tắt:

```yaml
mirrormaker2:
  enabled: false
```

Khi chưa bật flag này, chart production không render `KafkaMirrorMaker2`.

Target MSK bootstrap không hardcode trong secret hoặc source. Khi bật MirrorMaker2, truyền bootstrap qua values:

```text
mirrormaker2.targetCluster.bootstrapServers
```

Password lấy từ Kubernetes Secret đã sync bởi ESO:

```text
secret: msk-kafka-secret
key: password
```

Scripts không decode hoặc in password.

## Lệnh đã chạy

### 1. Kiểm tra repo

```bash
git status --short --branch
```

Kết quả:

```text
Repo app sạch trên main trước khi sửa.
```

### 2. Đọc plan và chart hiện có

```powershell
Get-Content -Raw docs\cdo08\week2\mandate8\implementation\drafts\KAFKA-MIGRATION-PLAN.md
Get-Content -Raw techx-corp-chart\values.yaml
Get-Content -Raw techx-corp-chart\templates\_helpers.tpl
Get-Content -Raw techx-corp-chart\values.schema.json
Get-Content -Raw techx-corp-chart\templates\component.yaml
```

Mục đích:

- Xác nhận plan yêu cầu MirrorMaker2.
- Bám đúng convention Helm chart hiện tại.
- Đảm bảo thêm values/schema không phá chart.

### 3. Render chart mặc định

PowerShell:

```powershell
helm template techx-corp ./techx-corp-chart > $env:TEMP\rel17-default-render.yaml
```

Git Bash:

```bash
helm template techx-corp ./techx-corp-chart > /tmp/rel17-default-render.yaml
```

Kết quả:

```text
Pass
```

Ý nghĩa:

- Khi `mirrormaker2.enabled=false`, chart vẫn render bình thường.
- Production không bị thay đổi runtime bởi PR này.

### 4. Render riêng MirrorMaker2 khi bật flag

PowerShell hoặc Git Bash đều dùng được nếu escape dấu phẩy đúng:

```bash
helm template techx-corp ./techx-corp-chart \
  --set mirrormaker2.enabled=true \
  --set-string "mirrormaker2.targetCluster.bootstrapServers=b-1.example.kafka.us-east-1.amazonaws.com:9096\,b-2.example.kafka.us-east-1.amazonaws.com:9096" \
  --show-only templates/mirrormaker2.yaml
```

Kết quả:

```text
Pass, render được KafkaMirrorMaker2 manifest.
```

Lưu ý:

Nếu không escape dấu phẩy trong bootstrap list, Helm sẽ fail:

```text
Error: failed parsing --set-string data: key "com:9096" has no value
```

Cách đúng là dùng:

```text
\, 
```

giữa hai broker.

### 5. Helm lint với production values

```bash
helm lint ./techx-corp-chart \
  -f ../tf4-phase3-gitops-manifests/environments/production/app-values.yaml \
  -f ../tf4-phase3-gitops-manifests/environments/production/flagd-values.yaml \
  -f ../tf4-phase3-gitops-manifests/environments/production/image-revisions.yaml
```

Kết quả:

```text
1 chart(s) linted, 0 chart(s) failed
```

### 6. Render với production values

PowerShell:

```powershell
helm template techx-corp ./techx-corp-chart `
  -f ..\tf4-phase3-gitops-manifests\environments\production\app-values.yaml `
  -f ..\tf4-phase3-gitops-manifests\environments\production\flagd-values.yaml `
  -f ..\tf4-phase3-gitops-manifests\environments\production\image-revisions.yaml > $env:TEMP\rel17-prod-render.yaml
```

Git Bash:

```bash
helm template techx-corp ./techx-corp-chart \
  -f ../tf4-phase3-gitops-manifests/environments/production/app-values.yaml \
  -f ../tf4-phase3-gitops-manifests/environments/production/flagd-values.yaml \
  -f ../tf4-phase3-gitops-manifests/environments/production/image-revisions.yaml > /tmp/rel17-prod-render.yaml
```

Kết quả:

```text
Pass
```

## Kết quả hiện tại

```text
MirrorMaker2 template: đã có
MirrorMaker2 default enabled: false
Migration scripts: đã có
Helm default render: pass
Helm MirrorMaker2 render: pass
Helm lint production values: pass
Helm production render: pass
Secret value committed: không
Runtime migration enabled: chưa
```

## Việc cần làm tiếp

1. Tạo PR app repo cho các file trên.
2. Sau khi PR app merge, cập nhật GitOps values để bật:

   ```yaml
   mirrormaker2:
     enabled: true
   ```

3. Truyền MSK bootstrap thật vào:

   ```text
   mirrormaker2.targetCluster.bootstrapServers
   ```

4. Verify MirrorMaker2 Running.
5. Verify lag/catch-up về 0.
6. Sau đó mới cutover producer/consumer theo plan.
