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

---

## Cập nhật runtime sau khi merge app repo và GitOps

Thời điểm ghi nhận: 2026-07-21.

Phạm vi của mục này: tiếp tục theo `KAFKA-MIGRATION-PLAN.md`, dừng ở giai đoạn trước cutover. Chưa chuyển traffic checkout/accounting/fraud-detection sang MSK.

### Trạng thái đã hoàn thành

- App repo đã merge các PR sửa MirrorMaker2 chart.
- GitOps repo đã merge PR bật MirrorMaker2 runtime.
- Bot promote GitOps đã cập nhật `targetRevision` sang commit app repo mới.
- ArgoCD đã sync ứng dụng `techx-corp` tới commit app repo mới.
- `KafkaMirrorMaker2/orders-mirrormaker2` đã `Ready`.
- Pod `orders-mirrormaker2-mirrormaker2-0` đã `Running` và container `Ready=true`.
- Kafka Connect REST API trả về 2 connector đang `RUNNING`:
  - `self-hosted->msk.MirrorSourceConnector`
  - `self-hosted->msk.MirrorCheckpointConnector`
- MirrorSource task đang replicate topic partition `orders-0` từ Kafka self-hosted sang MSK.
- ConfigMap worker đã có internal topic replication factor bằng `2`, phù hợp MSK hiện có 2 brokers.
- Topic `orders` trên MSK đã tồn tại, `ReplicationFactor=2`, ISR đủ.

### Lỗi đã gặp và cách xử lý

1. `KafkaMirrorMaker2` ban đầu không apply được vì CRD Strimzi live dùng `kafka.strimzi.io/v1`, không dùng `v1beta2`.

   Cách xử lý: sửa chart sang `apiVersion: kafka.strimzi.io/v1`.

2. Sau khi đổi API version, schema v1 yêu cầu `spec.target` và `spec.mirrors[].source`.

   Cách xử lý: sửa template theo schema Strimzi v1, thêm các field bắt buộc cho Kafka Connect target:

   ```yaml
   target:
     configStorageTopic: mm2-configs
     offsetStorageTopic: mm2-offsets
     statusStorageTopic: mm2-status
     groupId: orders-mirrormaker2
   ```

3. Strimzi operator không hỗ trợ Kafka version `3.9.0`.

   Cách xử lý: GitOps override:

   ```yaml
   mirrormaker2:
     version: 4.2.1
   ```

4. MirrorMaker2 không Ready vì Kafka Connect tạo internal topic `mm2-offsets` với replication factor mặc định `3`, trong khi MSK chỉ có 2 brokers.

   Log lỗi:

   ```text
   Replication factor: 3 larger than available brokers: 2
   ```

   Cách xử lý: thêm config replication factor cho các internal topic:

   ```yaml
   config.storage.replication.factor: "2"
   offset.storage.replication.factor: "2"
   status.storage.replication.factor: "2"
   ```

5. Sau khi PR merge, CR live đã `generation=3` nhưng `observedGeneration=2`, nên ConfigMap/pod vẫn chưa nhận RF=2 ngay.

   Cách xử lý: chờ Strimzi operator reconcile. Sau đó trạng thái chuyển thành:

   ```text
   generation=3 observedGeneration=3 Ready
   pod Running true restart=0
   ```

### Lệnh đã chạy và kết quả chính

Kiểm tra ArgoCD target revision và sync state:

```powershell
kubectl get application techx-corp -n argocd -o jsonpath='{.spec.sources[0].targetRevision} {.status.sync.status} {.status.health.status} {.status.operationState.phase} {.status.operationState.message}'
```

Kết quả chính:

```text
targetRevision=ba9245985e9ffea19d537f50934d92c799d0f399
operationState.phase=Succeeded
operationState.message=successfully synced (all tasks run)
```

Kiểm tra MirrorMaker2 resource:

```powershell
kubectl get kafkamirrormaker2 orders-mirrormaker2 -n techx-tf4
```

Kết quả sau khi operator reconcile:

```text
orders-mirrormaker2 DesiredReplicas=1 Ready
```

Kiểm tra generation:

```powershell
kubectl get kafkamirrormaker2 orders-mirrormaker2 -n techx-tf4 -o jsonpath='{.metadata.generation} {.status.observedGeneration} {.status.conditions[*].type} {.status.replicas} {.status.readyReplicas}'
```

Kết quả:

```text
3 3 Ready 1
```

Kiểm tra pod:

```powershell
kubectl get pod orders-mirrormaker2-mirrormaker2-0 -n techx-tf4 -o jsonpath='{.status.phase} {.status.containerStatuses[0].ready} {.status.containerStatuses[0].restartCount}'
```

Kết quả:

```text
Running true 0
```

Kiểm tra ConfigMap worker đã nhận RF=2:

```powershell
kubectl get cm orders-mirrormaker2-mirrormaker2-config -n techx-tf4 -o yaml |
  Select-String -Pattern 'replication.factor|config.storage|offset.storage|status.storage|bootstrap.servers|security.protocol|sasl.mechanism'
```

Kết quả chính:

```text
config.storage.topic=mm2-configs
offset.storage.topic=mm2-offsets
status.storage.topic=mm2-status
config.storage.replication.factor=2
offset.storage.replication.factor=2
status.storage.replication.factor=2
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
```

Kiểm tra Kafka Connect connector status:

```powershell
kubectl exec -n techx-tf4 orders-mirrormaker2-mirrormaker2-0 -- curl -s http://localhost:8083/connectors?expand=status
```

Kết quả chính:

```text
self-hosted->msk.MirrorCheckpointConnector: connector RUNNING, task 0 RUNNING
self-hosted->msk.MirrorSourceConnector: connector RUNNING, task 0 RUNNING
```

Kiểm tra log replication:

```powershell
kubectl logs orders-mirrormaker2-mirrormaker2-0 -n techx-tf4 --tail=200 |
  Select-String -Pattern 'ERROR|WARN|Exception|failed|Unable|replication.factor|Started|Herder|Ready|Successfully|logged in|Connector|Task'
```

Kết quả chính:

```text
MirrorSourceTask replicating 1 topic-partitions self-hosted->msk: [orders-0]
WorkerSourceTask self-hosted->msk.MirrorSourceConnector-0 finished initialization and start
```

Kiểm tra topic `orders` trên MSK:

```powershell
kubectl exec -n techx-tf4 orders-mirrormaker2-mirrormaker2-0 -- sh -c '/opt/kafka/bin/kafka-topics.sh --bootstrap-server b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096 --command-config /tmp/strimzi-connect.properties --describe --topic orders'
```

Kết quả chính:

```text
Topic: orders
PartitionCount: 3
ReplicationFactor: 2
Replicas: 1,2 / 2,1
Isr: 1,2 / 2,1
```

Lưu ý: lệnh Kafka CLI có lúc timeout sau khi đã in metadata. Metadata topic vẫn đọc được thành công.

### Trạng thái hiện tại theo plan

Đã đạt phần chính của Bước 2.1:

- MirrorMaker2 đã deploy qua GitOps.
- Pod MirrorMaker2 Running/Ready.
- Connector sync task RUNNING.
- Topic `orders` có trên MSK.

Đang ở Bước 2.2:

- Cần tiếp tục monitor MirrorMaker2 lag/catch-up ổn định.
- Chưa thực hiện Bước 3 Cutover Window.
- Chưa promote checkout producer.
- Chưa promote accounting/fraud-detection consumers.

### Việc cần làm tiếp trước cutover

1. Theo dõi MirrorMaker2 log/lag thêm một khoảng ổn định.
2. Nếu cần parity test bằng event thật, phải thống nhất trước vì publish vào topic `orders` có thể được consumer thật xử lý.
3. Khi bắt đầu Bước 3.1 cutover producer, cần quay video/lấy evidence từ đầu:
   - ArgoCD app state.
   - Rollout state.
   - checkout green pod Ready.
   - promote producer.
   - log publish sang MSK.
   - MM2 catch-up.
   - promote consumers.
   - accounting/fraud-detection consume/process.
   - rollback path vẫn rõ.

---

## Cập nhật pre-cutover: phát hiện lỗi CheckpointConnector trước khi quay evidence cutover

Thời điểm ghi nhận: 2026-07-21.

Khi chuẩn bị vào cutover, đã kiểm tra lại live state:

```powershell
kubectl get kafkamirrormaker2 orders-mirrormaker2 -n techx-tf4 -o jsonpath='{.metadata.generation} {.status.observedGeneration} {.status.conditions[*].type} {.status.replicas} {.status.readyReplicas}'
```

Kết quả:

```text
3 3 Ready 1
```

```powershell
kubectl get pod orders-mirrormaker2-mirrormaker2-0 -n techx-tf4 -o jsonpath='{.status.phase} {.status.containerStatuses[0].ready} {.status.containerStatuses[0].restartCount}'
```

Kết quả:

```text
Running true 0
```

```powershell
kubectl exec -n techx-tf4 orders-mirrormaker2-mirrormaker2-0 -- curl -s http://localhost:8083/connectors?expand=status
```

Kết quả chính:

```text
self-hosted->msk.MirrorCheckpointConnector: RUNNING
self-hosted->msk.MirrorSourceConnector: RUNNING
tasks: RUNNING
```

Tuy nhiên log 10 phút gần nhất có lỗi lặp lại ở `MirrorCheckpointConnector`:

```text
Unable to sync offsets for consumer group accounting.
Unable to sync offsets for consumer group fraud-detection.
UnknownTopicOrPartitionException: Failed altering group offsets for the following partitions: [self-hosted.orders-0]
```

Phân tích:

- `MirrorSourceConnector` đang dùng `IdentityReplicationPolicy`, nên topic đích là `orders`.
- `MirrorCheckpointConnector` chưa được set cùng `replication.policy.class`.
- Vì vậy checkpoint/offset sync vẫn map offset sang tên topic dạng alias `self-hosted.orders`, trong khi MSK đang có topic identity là `orders`.
- Không nên vào cutover consumer khi checkpoint offset sync còn lỗi lặp lại.

Cách xử lý đã chuẩn bị trong app repo:

```yaml
checkpointConnector:
  config:
    replication.policy.class: "org.apache.kafka.connect.mirror.IdentityReplicationPolicy"
```

File đã sửa:

```text
techx-corp-chart/templates/mirrormaker2.yaml
```

Lệnh verify local:

```powershell
helm lint ./techx-corp-chart -f ../tf4-phase3-gitops-manifests/environments/production/app-values.yaml -f ../tf4-phase3-gitops-manifests/environments/production/flagd-values.yaml -f ../tf4-phase3-gitops-manifests/environments/production/image-revisions.yaml
```

Kết quả:

```text
1 chart(s) linted, 0 chart(s) failed
```

```powershell
helm template techx-corp ./techx-corp-chart -f ../tf4-phase3-gitops-manifests/environments/production/app-values.yaml -f ../tf4-phase3-gitops-manifests/environments/production/flagd-values.yaml -f ../tf4-phase3-gitops-manifests/environments/production/image-revisions.yaml --show-only templates/mirrormaker2.yaml
```

Kết quả chính:

```text
sourceConnector.config.replication.policy.class: org.apache.kafka.connect.mirror.IdentityReplicationPolicy
checkpointConnector.config.replication.policy.class: org.apache.kafka.connect.mirror.IdentityReplicationPolicy
```

Trạng thái:

- Chưa vào cutover.
- Cần tạo PR app repo cho fix này.
- Sau khi app PR merge, đợi bot promote GitOps targetRevision.
- Sau khi ArgoCD sync xong, kiểm tra lại log `MirrorCheckpointConnector`.
- Chỉ bắt đầu quay video cutover khi lỗi offset sync không còn lặp lại và pre-cutover check pass.
