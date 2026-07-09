# Runtime Reliability Findings - CDO08 Week 1

## 0. Task metadata

| Field               | Value                                                                                               |
| ------------------- | --------------------------------------------------------------------------------------------------- |
| Task                | `[Runtime] Scan Kubernetes runtime reliability risks cho CDO08 Week 1`                              |
| Owner               | Hoàng Nam                                                                                           |
| Pillar              | Reliability                                                                                         |
| Priority            | P1                                                                                                  |
| Output              | `docs/cdo08/week1/nam-runtime-reliability-findings.md`                                              |
| Scope               | Kubernetes runtime reliability: replicas, probes, pod status, Helm upgrade/rollback, PDB candidates |
| Runtime environment | EKS `techx-tf4-cluster`, namespace `techx-tf4`                                                      |
| Runtime evidence time | 2026-07-08 21:03 ICT đến 2026-07-09 09:36 ICT; dùng evidence mới nhất lúc 09:36 cho trạng thái hiện tại |
| Current status      | Draft report từ static chart/source analysis và runtime kubectl/Helm evidence đã có                 |

## 1. Mục tiêu

Tài liệu này tổng hợp kết quả scan Kubernetes runtime reliability trong phạm vi CDO08 Week 1. Mục tiêu là xác định các rủi ro availability hiện tại liên quan đến replica coverage, readiness/liveness probe, pod status, Helm upgrade/rollback path và PodDisruptionBudget cho các service critical.

Tài liệu này không tạo hoặc thay đổi runtime resource. Các đề xuất bên dưới là backlog candidates cho Week 2-3, có thể được đưa vào backlog tổng và đánh giá tiếp bằng rubric ưu tiên.

## 2. Scope scan

| Scope item                                                | Trạng thái scan             | Ghi chú                                                                                                                                       |
| --------------------------------------------------------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Replica coverage cho service critical                     | Completed                   | Runtime `kubectl get deploy,sts` xác nhận toàn bộ app deployments trong `techx-tf4` đang `1/1`; không có StatefulSet trong namespace hiện tại |
| Readiness probe coverage                                  | Completed                   | Runtime jsonpath xác nhận toàn bộ app deployments hiện không có readiness probe                                                               |
| Liveness probe coverage                                   | Completed                   | Runtime jsonpath xác nhận toàn bộ app deployments hiện không có liveness probe                                                                |
| Pod status/restarts/events                                | Completed                   | Evidence mới nhất cho thấy pods `Running`, restart `0`; event history ghi nhận một số incident đã recover                                     |
| Helm upgrade path                                         | Completed                   | `helm list`, `helm status`, `helm history` đã verify được release `techx-corp`                                                                |
| Helm rollback path                                        | Partially verified          | Đã xác định được revision history để rollback; chưa chạy rollback thật vì cần approval trước khi thay đổi live cluster                        |
| PodDisruptionBudget candidates                            | Completed                   | `kubectl get pdb` hiện trả `No resources found` trong namespace `techx-tf4`                                                                   |
| Runtime evidence bằng kubectl trong namespace `techx-tf4` | Completed for task coverage | Namespace-scoped kubectl/Helm checks đã đủ cho phạm vi runtime reliability scan                                                               |

## 3. Runtime baseline

### 3.1 Evidence sources

| Evidence source       | Command/file                                               | Kết luận chính                                                                                                                             |
| --------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Chart replica default | `techx-corp-chart/values.yaml:28`                          | `default.replicas: 1`; phần lớn app service kế thừa single replica                                                                         |
| Chart replica render  | `techx-corp-chart/templates/_objects.tpl:13`               | Deployment render replicas từ component hoặc default values                                                                                |
| Chart probe render    | `techx-corp-chart/templates/_objects.tpl:73-79`, `125-131` | Template có support readiness/liveness nếu values khai báo                                                                                 |
| Chart probe values    | `techx-corp-chart/values.yaml:152-154`                     | Baseline values chỉ có comment mẫu probe, chưa cấu hình probe thật                                                                         |
| Runtime replicas      | `kubectl -n techx-tf4 get deploy,sts`                      | Tất cả app deployments hiện `READY 1/1`; không có StatefulSet trong `techx-tf4`; stateful dependencies vẫn chạy dạng Deployment `1/1`      |
| Runtime probes        | `kubectl -n techx-tf4 get deploy -o jsonpath=...`          | Toàn bộ app deployments hiện có `readiness=` và `liveness=` trống                                                                          |
| Runtime pods          | `kubectl -n techx-tf4 get pods -o wide`                    | Evidence mới nhất lúc 09:01 ICT cho thấy toàn bộ pods `1/1 Running`, restart `0`, phân bố trên 2 node                                      |
| Runtime events        | `kubectl -n techx-tf4 get events --sort-by=.lastTimestamp` | Event history có ClusterIP repair warning, accounting CrashLoop/OOMKilled đã recover, rollout sang image tag `2c041a7-*`                   |
| Runtime PDB           | `kubectl -n techx-tf4 get pdb`                             | `No resources found in techx-tf4 namespace`; revenue path và stateful dependencies chưa có PDB                                             |
| Helm runtime evidence | `helm -n techx-tf4 list/status/history techx-corp`         | Release `techx-corp` đang `deployed`, revision `11`, `Upgrade complete`; history có revision `2-10` superseded để xác định rollback target |
| Observability scope   | Runtime events + deploy team update                        | Observability stack cũ không còn nằm trong `techx-tf4`; theo deploy team đang update/migrate sang namespace `techx-observability`          |

### 3.2 Replica matrix từ chart và runtime

| Service/component | Chart replicas | Runtime desired/ready | Criticality | Reliability note                                                                       |
| ----------------- | -------------: | --------------------- | ----------- | -------------------------------------------------------------------------------------- |
| `frontend-proxy`  |              1 | 1/1                   | P0          | Public entrypoint single replica; nếu pod lỗi/rollout lỗi sẽ ảnh hưởng toàn storefront |
| `frontend`        |              1 | 1/1                   | P0          | Storefront UI/API single replica; ảnh hưởng browse/cart/checkout UX                    |
| `checkout`        |              1 | 1/1                   | P0          | Revenue path single replica; ảnh hưởng trực tiếp checkout                              |
| `cart`            |              1 | 1/1                   | P0          | Cart API single replica; phụ thuộc `valkey-cart`                                       |
| `payment`         |              1 | 1/1                   | P0          | Payment là bước checkout critical                                                      |
| `product-catalog` |              1 | 1/1                   | P0          | Browse và checkout item lookup phụ thuộc service này                                   |
| `shipping`        |              1 | 1/1                   | P0/P1       | Downstream trong checkout path                                                         |
| `quote`           |              1 | 1/1                   | P0/P1       | Downstream trong shipping/quote path                                                   |
| `currency`        |              1 | 1/1                   | P0/P1       | Price conversion single replica                                                        |
| `postgresql`      |              1 | 1/1                   | P0          | Stateful DB chạy dạng Deployment `1/1`; pod đã được recreate trong event history       |
| `valkey-cart`     |              1 | 1/1                   | P0          | Cart state dependency single replica; pod đã được recreate trong event history         |
| `kafka`           |              1 | 1/1                   | P1          | Single broker/controller quorum `1@kafka:9093`; event path phụ thuộc vào một broker    |
| `flagd`           |              1 | 1/1                   | P1          | Feature flag/incident mechanism single replica; cần review sync safety trước khi scale |
| `product-reviews` |              1 | 1/1                   | P1/P2       | AI review feature single replica; cần phối hợp AIO nếu scale ảnh hưởng LLM/API cost    |
| `recommendation`  |              1 | 1/1                   | P2          | UX degrade nếu down, không trực tiếp block checkout                                    |
| `email`           |              1 | 1/1                   | P2          | Email confirmation/delivery path có thể degrade nếu pod lỗi                            |
| `ad`              |              1 | 1/1                   | P2          | UX degrade thấp hơn checkout path                                                      |

Runtime conclusion: evidence mới nhất cho thấy toàn bộ pods trong `techx-tf4` đang `Running` và deployments đều `1/1`. Tuy vậy toàn bộ service critical vẫn single-replica, nên các incident trước đó như image pull failure, accounting OOMKilled hoặc recreate stateful pod đều có thể tác động trực tiếp đến availability vì không có pod dự phòng.

### 3.3 Probe coverage matrix

| Service/component | Readiness probe | Liveness probe | Runtime/source note                                                                        | Risk                                                            |
| ----------------- | --------------- | -------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| `frontend-proxy`  | No              | No             | Runtime jsonpath trả `readiness=` và `liveness=` trống                                     | Public entrypoint có thể nhận traffic khi chưa sẵn sàng         |
| `frontend`        | No              | No             | Runtime không có probes                                                                    | UI/API có thể nhận traffic trước khi app sẵn sàng               |
| `checkout`        | No              | No             | Source có gRPC health service nhưng trả `SERVING` tĩnh; chart chưa nối probe               | Checkout có thể nhận request khi chưa thật sự ready             |
| `cart`            | No              | No             | Có gRPC health/readinessCheck ở source; hiện chưa ping Valkey thật; runtime không có probe | Cart có thể nhận traffic khi Valkey unavailable sau startup     |
| `payment`         | No              | No             | Source có gRPC health service nhưng trạng thái luôn `SERVING`; runtime không có probe      | Payment rollout/unhealthy khó được Kubernetes gate/restart đúng |
| `product-catalog` | No              | No             | Source có gRPC health service nhưng chưa ping DB; runtime không có probe                   | Browse/checkout lookup có thể lỗi nếu DB chưa sẵn sàng          |
| `shipping`        | No              | No             | Chưa xác định health protocol đầy đủ                                                       | Checkout downstream risk                                        |
| `quote`           | No              | No             | Chưa xác định health protocol đầy đủ                                                       | Checkout downstream risk                                        |
| `currency`        | No              | No             | Source có gRPC health service; runtime không có probe                                      | Price conversion risk                                           |
| `postgresql`      | No              | No             | Runtime không có `pg_isready` readiness/liveness                                           | DB dependency chưa có native readiness gate                     |
| `valkey-cart`     | No              | No             | Runtime không có Valkey/Redis `PING` readiness/liveness                                    | Cart state dependency chưa có readiness gate                    |
| `kafka`           | No              | No             | Runtime không có broker readiness/liveness                                                 | Event path có thể unstable trong rollout/restart                |
| `flagd`           | No              | No             | Runtime không có probe                                                                     | Feature flag/incident control path có thể không rõ trạng thái   |
| `product-reviews` | No              | No             | Source có gRPC health service nhưng trả `SERVING` tĩnh                                     | AI UX/SLO degrade                                               |
| `recommendation`  | No              | No             | Runtime không có probe                                                                     | UX degrade                                                      |
| `email`           | No              | No             | Runtime không có probe                                                                     | Email path degrade/delay                                        |
| `ad`              | No              | No             | Runtime không có probe                                                                     | UX degrade thấp                                                 |

### 3.4 Pod/runtime status hiện tại

Runtime commands đã chạy trong lần kiểm tra mới nhất:

```bash
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get deploy,sts
kubectl -n techx-tf4 get deploy -o jsonpath='{...readinessProbe...livenessProbe...}'
kubectl -n techx-tf4 get pdb
kubectl -n techx-tf4 get events --sort-by=.lastTimestamp
helm -n techx-tf4 list
helm -n techx-tf4 status techx-corp
helm -n techx-tf4 history techx-corp
```

Kết luận từ output runtime mới nhất ngày 2026-07-09:

- Lúc 09:01 ICT, `kubectl get pods -o wide` cho thấy toàn bộ pods trong `techx-tf4` đều `1/1 Running`, `RESTARTS=0`.
- Lúc 09:01 ICT, `kubectl get deploy,sts` cho thấy toàn bộ deployments đều `READY 1/1`, `AVAILABLE 1`; không có StatefulSet trong namespace này.
- Lúc 09:13 ICT, `kubectl get events` cho thấy event history còn các warning/incident đã recover: `ClusterIPNotAllocated ... repairing` hàng loạt, `accounting` pod cũ `BackOff`, rollout/redeploy nhiều workload sang image tag `2c041a7-*`.
- `accounting` pod cũ từng `CrashLoopBackOff` do `OOMKilled`, `Exit Code: 137`, `Restart Count: 89`, `memory limit/request: 120Mi`; pod mới `accounting-bb95b6697-ff8ts` đang `Running`, `Restart Count: 0`.
- Lúc 09:36 ICT, Helm release `techx-corp` đang `deployed`, revision `11`, `Upgrade complete`; history có revision `2-10` để xác định rollback target nếu cần.
- Observability stack cũ (`grafana`, `jaeger`, `prometheus`, `opensearch`, `otel-collector-agent`) không còn nằm trong `techx-tf4`; theo update từ deploy team, phần này đang được migrate/update sang namespace `techx-observability`.

## 4. Findings

| Finding ID      | Finding/gap                                                                                          | Pillar               | Service/component ảnh hưởng                                                                                                    | Evidence                                                                                                                                                                                                     | Impact                                                                                                                                                                                               | Đề xuất xử lý                                                                                                                                                                | Priority đề xuất | Owner phối hợp                                         |
| --------------- | ---------------------------------------------------------------------------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- | ------------------------------------------------------ |
| NAM-RUNTIME-001 | Revenue path services đang single-replica                                                            | Reliability          | `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `product-catalog`, `shipping`, `quote`, `currency`                | `values.yaml:28 default.replicas: 1`; runtime `kubectl get deploy,sts` ngày 2026-07-09 cho thấy các service đều `READY 1/1`, `AVAILABLE 1`, không có pod dự phòng                                            | Single replica làm rollout/image issue/pod crash tác động trực tiếp tới customer traffic và checkout path; không có pod thứ hai để giữ availability                                                  | Tăng replica tối thiểu 2 cho nhóm P0 sau khi có resource request, readiness, smoke test và cost review; rollout bằng Helm có verify                                          | P0               | CDO04 cost/resource, Quân checkout flow, Nguyên review |
| NAM-RUNTIME-002 | Stateful dependencies single-replica và chưa có HA/persistence rõ                                    | Reliability          | `postgresql`, `valkey-cart`, `kafka`                                                                                           | Runtime `postgresql`, `valkey-cart`, `kafka` đều Deployment `1/1`; `kafka` có controller quorum `1@kafka:9093`; event history cho thấy `postgresql` và `valkey-cart` từng bị recreate trong rollout          | DB/cache/event broker là single point of failure; ảnh hưởng cart state, product data, post-order events/accounting/fraud                                                                             | Tạo backlog riêng cho PostgreSQL backup/restore/HA, Valkey persistence/replication, Kafka durability/acks/consumer lag; không chỉ tăng replica cơ học                        | P0/P1            | Data owner, CDO04 cost, Quân/Phương tùy ownership      |
| NAM-RUNTIME-003 | App services critical thiếu readiness/liveness probes                                                | Reliability          | Revenue path + stateful dependencies + flag/AI/UX services                                                                     | Runtime jsonpath ngày 2026-07-09 xác nhận toàn bộ app deployments có `readiness=` và `liveness=` trống                                                                                                       | Kubernetes có thể route traffic vào pod chưa ready; container unhealthy có thể không được restart đúng lúc; rollout dễ gây request fail                                                              | Thêm readiness/liveness theo protocol: HTTP/gRPC/TCP/native command; ưu tiên `frontend-proxy`, `checkout`, `cart`, `payment`, `product-catalog`, `postgresql`, `valkey-cart` | P0               | Nguyên review, Quân checkout smoke test, data owner    |
| NAM-RUNTIME-004 | Health endpoints trong source còn nhiều trạng thái tĩnh, chưa phản ánh dependency thực               | Reliability          | `checkout`, `payment`, `product-catalog`, `product-reviews`, `cart`, `currency`                                                | Source evidence: nhiều gRPC health `Check` trả `SERVING` tĩnh; `cart` readiness chủ yếu theo feature flag, chưa ping Valkey thật                                                                             | Nếu chỉ nối probe vào endpoint tĩnh thì Kubernetes sẽ báo healthy dù dependency chính có thể lỗi                                                                                                     | Cải thiện readiness để kiểm tra dependency tối thiểu, nhẹ và bounded timeout; liveness không check downstream nặng                                                           | P1               | Service owners, AIO nếu liên quan LLM/product-reviews  |
| NAM-RUNTIME-005 | Helm rollback metadata đã verify, nhưng chưa rollback live cluster                                   | Reliability          | Helm release `techx-corp` trong namespace `techx-tf4`                                                                          | `helm list`, `helm status techx-corp`, `helm history techx-corp` đã chạy được; release hiện `deployed`, revision `11`, history có revision `2-10` superseded                                                 | Team đã xác định được rollback target, nhưng full rollback behavior chưa được test vì task không được phép thay đổi live runtime nếu chưa approve                                                    | Giữ rollback runbook; chỉ chạy `helm rollback techx-corp <REVISION> --wait --timeout 10m` khi có approval và maintenance/incident context                                    | P2               | Nguyên/deploy owner                                    |
| NAM-RUNTIME-006 | Helm upgrade/rollback path cần chuẩn hóa và luôn include flagd sync overlay                          | Reliability/Security | Helm deploy flow, `flagd`                                                                                                      | `GETTING_STARTED.md` yêu cầu deploy với `values-flagd-sync.yaml`; Helm release hiện revision `11` deployed; flagd vẫn là incident mechanism được bảo vệ                                                      | Upgrade sai values có thể làm mất flagd path hoặc phá incident mechanism BTC; rollback không rõ kéo dài downtime                                                                                     | Dùng runbook chuẩn: `helm upgrade --install ... -f deploy/values-flagd-sync.yaml`; trước/sau deploy verify pods, services, frontend, checkout, observability, flagd          | P1               | Thuỷ flagd/secrets, Nguyên/deploy owner                |
| NAM-RUNTIME-007 | Namespace `techx-tf4` hiện không có PodDisruptionBudget                                              | Reliability          | Revenue path services; `postgresql`, `valkey-cart`, `kafka`                                                                    | `kubectl -n techx-tf4 get pdb` trả `No resources found in techx-tf4 namespace`                                                                                                                               | Revenue path và stateful dependencies không được bảo vệ trước voluntary disruption; tuy nhiên PDB chỉ có ý nghĩa sau khi service có >=2 replicas và readiness phù hợp                                | Tạo PDB candidates sau khi tăng replicas và thêm readiness; tránh tạo PDB cho single-replica workload theo cách có thể block node drain                                      | P1/P2            | CDO04 cost, Nguyên review                              |
| NAM-RUNTIME-008 | Critical app pods từng `ImagePullBackOff`/`ErrImagePull` trong window scan do image tag chưa tồn tại | Reliability          | `frontend-proxy`, `frontend`, `checkout`, `cart`, `currency`, `accounting`, `ad`, `email`, `fraud-detection`, `image-provider` | Lúc 2026-07-08 21:03-21:04, nhiều pods `0/1 ImagePullBackOff`; ECR `describe-images` trả `ImageNotFoundException` cho tag `1.0-frontend-proxy`; rollout sau đó dùng image tag `2c041a7-*` và pods đã recover | Customer/revenue path từng có nguy cơ down/degraded vì entrypoint/frontend/checkout/cart không available; finding đã recover nhưng là evidence thật về rollout/image pipeline risk                   | Review build/push pipeline, tag naming, Helm values image tags; bổ sung deploy preflight check và rollout smoke test để tránh lặp lại                                        | P1               | Deploy owner/CDO04, Nguyên, service owners             |
| NAM-RUNTIME-009 | `accounting` từng CrashLoopBackOff do OOMKilled                                                      | Reliability          | `accounting`, Kafka post-order event flow, PostgreSQL accounting data                                                          | Pod cũ `accounting-55b855b5f5-9w52k` có `CrashLoopBackOff`, last state `OOMKilled`, exit code `137`, restart count `89`, memory limit/request `120Mi`; pod mới đã Running restart `0`                        | Customer checkout có thể vẫn thành công nếu event đã publish vào Kafka, nhưng accounting consumer down có thể làm tăng lag, trì hoãn hoặc mất accounting records tùy offset/retention/error handling | Review memory usage, resource limit/request, consumer behavior, retry/offset handling; thêm alert cho restart/OOMKilled và consumer lag                                      | P1               | CDO08 runtime, CDO04 cost, accounting owner            |
| NAM-RUNTIME-010 | ClusterIP repair warning xuất hiện hàng loạt trong event history                                     | Reliability          | Kubernetes Services trong `techx-tf4`, gồm revenue path và dependencies                                                        | `kubectl get events` ghi nhận nhiều `ClusterIPNotAllocated ... repairing` cho service như `checkout`, `cart`, `frontend-proxy`, `postgresql`, `kafka`, `valkey-cart`                                         | Có thể là transient control-plane/service repair trong rollout; nếu lặp lại có thể ảnh hưởng service discovery hoặc làm nhiễu incident triage                                                        | Theo dõi xem warning có tái diễn; nếu lặp lại, phối hợp deploy/platform owner kiểm tra service recreation, controller events và cluster networking                           | P2               | Deploy/platform owner                                  |

## 5. Deploy/rollback evidence

### 5.1 Upgrade command/check cần có

Baseline command theo GETTING_STARTED/runbook:

```bash
helm upgrade --install techx-corp ./techx-corp-chart -n techx-tf4 --create-namespace \
  --set default.image.repository=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml
```

Pre-flight checks:

```bash
aws sts get-caller-identity
kubectl config current-context
kubectl -n techx-tf4 get pods
helm dependency build ./techx-corp-chart
helm -n techx-tf4 list
helm -n techx-tf4 history techx-corp
```

Post-upgrade checks:

```bash
helm -n techx-tf4 status techx-corp
kubectl -n techx-tf4 get pods
kubectl -n techx-tf4 get deploy,sts
kubectl -n techx-tf4 get svc
kubectl -n techx-tf4 get events --sort-by=.lastTimestamp
```

### 5.2 Rollback command/check cần có

Rollback command:

```bash
helm -n techx-tf4 history techx-corp
helm -n techx-tf4 rollback techx-corp <REVISION> --wait --timeout 10m
```

Runtime evidence hiện tại:

| Check                                  | Result                                                                                       |
| -------------------------------------- | -------------------------------------------------------------------------------------------- |
| `helm -n techx-tf4 list`               | Release `techx-corp` status `deployed`, revision `11`                                        |
| `helm -n techx-tf4 status techx-corp`  | `STATUS: deployed`, `DESCRIPTION: Upgrade complete`, related pods `Running`                  |
| `helm -n techx-tf4 history techx-corp` | Revision `11` deployed; revisions `2-10` superseded, có thể dùng làm rollback target nếu cần |

Post-rollback checks:

```bash
helm -n techx-tf4 status techx-corp
helm -n techx-tf4 history techx-corp
kubectl -n techx-tf4 get pods
kubectl -n techx-tf4 get deploy,sts
kubectl -n techx-tf4 get svc frontend-proxy
```

Nếu ALB có sẵn, kiểm tra thêm frontend/storefront URL và checkout smoke test theo checklist của owner checkout.

### 5.3 Gap hiện tại

| Gap                     | Evidence                                                                                                              | Impact                                                                                  | Next step                                                                                |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Chưa chạy rollback thật | Task không yêu cầu rollback live EKS runtime nếu chưa approve                                                         | Không xác minh được full rollback behavior end-to-end                                   | Chỉ chạy rollback khi có approval; hiện đã đủ metadata để chọn rollback revision nếu cần |
| Observability namespace | Grafana/Jaeger/Prometheus/OpenSearch không còn trong `techx-tf4`; deploy team đang migrate sang `techx-observability` | Runtime app scan vẫn đủ, nhưng SLO/log/trace verification phụ thuộc observability owner | Ghi nhận scope change; không tính là app runtime failure trong namespace `techx-tf4`     |

## 6. Backlog candidates

| Backlog candidate                                                                                                                | Priority draft | Source finding       | Why / business impact                                                                                       | Owner/dependency                                     |
| -------------------------------------------------------------------------------------------------------------------------------- | -------------- | -------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| Tăng replica + readiness + rollout smoke test cho `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `product-catalog` | P0             | NAM-RUNTIME-001, 003 | Giảm downtime/degrade trên customer traffic và checkout path                                                | CDO08 runtime reliability, Quân checkout, CDO04 cost |
| Thêm readiness/liveness probes cho revenue path theo protocol phù hợp                                                            | P0             | NAM-RUNTIME-003, 004 | Tránh traffic vào pod chưa ready và phát hiện unhealthy container                                           | CDO08 runtime reliability, service owners            |
| Thiết kế reliability cho `postgresql`: persistence, backup/restore, readiness, HA/migration path                                 | P0             | NAM-RUNTIME-002, 003 | DB là dependency nhiều service; single point có business impact cao                                         | Data owner, CDO04                                    |
| Thiết kế reliability cho `valkey-cart`: persistence/replication hoặc mitigation mất cart                                         | P0             | NAM-RUNTIME-002, 003 | Cart state ảnh hưởng trực tiếp checkout precondition                                                        | Data owner, CDO04, Quân                              |
| Review Kafka single broker/durability/consumer lag path                                                                          | P1             | NAM-RUNTIME-002, 009 | Accounting/fraud/post-order processing phụ thuộc Kafka; consumer down có thể gây lag hoặc record delay/loss | Kafka/accounting owner, CDO04                        |
| Review image tag/publish mismatch từng gây ImagePullBackOff cho critical app pods                                                | P1             | NAM-RUNTIME-008      | Entry point/frontend/checkout/cart từng `0/1`; cần tránh lặp lại trong rollout sau                          | Deploy owner, CDO04/ECR, Nguyên                      |
| Review accounting OOMKilled/restart behavior                                                                                     | P1             | NAM-RUNTIME-009      | Accounting từng CrashLoopBackOff/OOMKilled; ảnh hưởng post-order accounting/event processing                | Accounting owner, CDO04 cost                         |
| Chuẩn hóa deploy/rollback checklist bắt buộc cho runtime changes                                                                 | P1             | NAM-RUNTIME-005, 006 | Helm metadata đã verify; cần quy trình rollback/smoke test rõ khi có deploy lỗi                             | Nguyên/deploy owner, Thuỷ flagd                      |
| PDB cho revenue path sau khi có >=2 replicas và readiness                                                                        | P1/P2          | NAM-RUNTIME-007      | Giảm voluntary disruption khi node drain/maintenance                                                        | CDO08 runtime reliability, CDO04                     |
| Theo dõi ClusterIP repair warnings nếu tái diễn                                                                                  | P2             | NAM-RUNTIME-010      | Warning hàng loạt có thể làm nhiễu incident triage hoặc báo hiệu service recreation/networking issue        | Deploy/platform owner                                |

## 7. Summary

Tại evidence mới nhất ngày 2026-07-09, namespace `techx-tf4` đã recover về trạng thái healthy ở mức workload cơ bản: toàn bộ pods `Running`, restart `0`, deployments `READY 1/1`, Helm release `techx-corp` revision `11` đang `deployed`. RBAC blocker cho Helm release metadata đã được gỡ vì `helm list/status/history` đều chạy được.

Tuy vậy reliability baseline vẫn còn mỏng: toàn bộ service critical và stateful dependencies đang single-replica, app deployments không có readiness/liveness probes, namespace `techx-tf4` không có PDB, và event history ghi nhận các incident đã recover như ImagePullBackOff do image tag mismatch, accounting OOMKilled/CrashLoopBackOff, ClusterIP repair warnings, cùng rollout/redeploy toàn bộ workload. Các findings này vẫn đủ điều kiện đưa vào backlog Week 2-3 vì có static evidence từ chart/source và runtime evidence từ kubectl/Helm.

