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

## Cập nhật sau review PR #401

Review yêu cầu sửa 2 điểm trước khi merge:

1. `01-verify-msk-connectivity.sh` dùng `kubectl run --rm` nhưng chưa attach bằng `-i`, nên `kubectl` chặn ngay trước khi tạo pod.
2. Debug pod trong script chưa tuân thủ admission policy của cluster: cần `runAsNonRoot`, drop toàn bộ Linux capabilities và khai báo `resources.requests/limits`.
3. `values.schema.json` cho `mirrormaker2` còn quá lỏng vì `additionalProperties=true`, dễ bỏ lọt typo như `boostrapServers`.

Đã xử lý:

```text
docs/cdo08/week2/mandate8/scripts/kafka/01-verify-msk-connectivity.sh
techx-corp-chart/values.schema.json
```

Chi tiết:

- Thêm `-i` cho `kubectl run --rm`.
- Thêm `--overrides` để pod test MSK connectivity tuân thủ policy:
  - `runAsNonRoot=true`
  - `runAsUser=65534`
  - `runAsGroup=65534`
  - `seccompProfile=RuntimeDefault`
  - `allowPrivilegeEscalation=false`
  - `capabilities.drop=["ALL"]`
  - `resources.requests/limits`
- Thêm biến `KUBECTL="${KUBECTL:-kubectl}"` để có thể override path kubectl khi cần chạy từ môi trường Windows/Git Bash.
- Siết schema `mirrormaker2` về `additionalProperties=false`.
- Khai báo rõ các field con:
  - `name`
  - `replicas`
  - `version`
  - `connectCluster`
  - `sourceCluster.alias`
  - `sourceCluster.bootstrapServers`
  - `targetCluster.alias`
  - `targetCluster.bootstrapServers`
  - `targetCluster.securityProtocol`
  - `targetCluster.saslMechanism`
  - `targetCluster.username`
  - `targetCluster.passwordSecret.name`
  - `targetCluster.passwordSecret.key`
  - `topicsPattern`
  - `groupsPattern`
  - `replicationPolicyClass`
  - `sourceConnector.tasksMax`
  - `resources`

Lệnh verify sau khi sửa:

```bash
bash -n docs/cdo08/week2/mandate8/scripts/kafka/01-verify-msk-connectivity.sh
```

Kết quả:

```text
Pass
```

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

```bash
helm template techx-corp ./techx-corp-chart \
  --set mirrormaker2.enabled=true \
  --set-string "mirrormaker2.targetCluster.bootstrapServers=b-1.example.kafka.us-east-1.amazonaws.com:9096\,b-2.example.kafka.us-east-1.amazonaws.com:9096" \
  --show-only templates/mirrormaker2.yaml
```

Kết quả:

```text
Pass, render được KafkaMirrorMaker2 manifest với IdentityReplicationPolicy.
```

```bash
helm template techx-corp ./techx-corp-chart \
  -f ../tf4-phase3-gitops-manifests/environments/production/app-values.yaml \
  -f ../tf4-phase3-gitops-manifests/environments/production/flagd-values.yaml \
  -f ../tf4-phase3-gitops-manifests/environments/production/image-revisions.yaml
```

Kết quả:

```text
Pass
```

Lưu ý: chưa chạy runtime `01-verify-msk-connectivity.sh` trực tiếp trên cluster trong phiên này vì shell tool không có `kubectl` trong PATH của bash. Script đã được sửa theo đúng pattern đã pass ở PR Valkey và đã pass syntax check.

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
