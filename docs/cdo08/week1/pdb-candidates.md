# PodDisruptionBudget Candidates

## 0. Task metadata

| Field            | Value                                                                         |
| ---------------- | ----------------------------------------------------------------------------- |
| Jira task        | `[Runtime] Xác định candidates cho PodDisruptionBudget`                       |
| Owner / Assignee | Hoàng Nam                                                                     |
| Area / Ownership | Kubernetes Runtime Reliability                                                |
| Pillar           | Reliability                                                                   |
| Priority         | P2                                                                            |
| Reviewer         | Nguyên                                                                        |
| Output artifact  | `docs/cdo08/week1/pdb-candidates.md`                                          |
| Current status   | Candidate analysis completed; no new PDB created by this task                 |
| Runtime blocker  | N/A; runtime replica/probe evidence already captured in namespace `techx-tf4` |
| Last updated     | 2026-07-08                                                                    |

## 1. Mục tiêu

Task này xác định các service nên được xem là candidates cho PodDisruptionBudget trong tuần 2-3, dựa trên replica coverage, checkout criticality và runtime evidence hiện tại.

Scope của task này là **candidate analysis**, không tạo PDB YAML và không thay đổi production runtime.

## 2. Nguyên tắc đánh giá PDB

PodDisruptionBudget chỉ bảo vệ trước **voluntary disruption** như node drain, maintenance hoặc cluster autoscaler eviction. PDB không cứu được pod crash, node mất đột ngột hoặc container unhealthy.

Nguyên tắc áp dụng cho hệ thống hiện tại:

- Service chỉ có 1 replica mà đặt `minAvailable: 1` sẽ có nguy cơ chặn node drain/maintenance.
- Service chỉ có 1 replica mà đặt `minAvailable: 0` thì gần như không giúp bảo vệ availability.
- Vì vậy PDB nên được tạo sau hoặc cùng lúc với việc tăng replica cho service critical.
- Với stateless service có 2 replicas, đề xuất baseline thường là `minAvailable: 1`.
- Với stateful dependency như PostgreSQL, Valkey, Kafka, không nên tạo PDB cơ học nếu chưa có thiết kế persistence, replication, backup/restore và readiness phù hợp.
- PDB nên đi cùng readiness probe. Nếu pod chưa có readiness, Kubernetes khó đánh giá chính xác pod nào thật sự sẵn sàng phục vụ traffic.

## 3. Nguồn evidence

| Evidence                                                   | Kết luận dùng cho PDB candidates                                                                                                                    |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `techx-corp-chart/values.yaml:28`                          | `default.replicas: 1`; phần lớn app service kế thừa single replica                                                                                  |
| `techx-corp-chart/templates/_objects.tpl:13`               | Deployment render replica từ component hoặc default values                                                                                          |
| Runtime `kubectl -n techx-tf4 get deploy`                  | Tất cả deployment trong app/runtime đang `DESIRED=1`, `READY=1`, `AVAILABLE=1`                                                                      |
| Runtime `kubectl -n techx-tf4 get sts`                     | StatefulSet `opensearch` đang `DESIRED=1`, `READY=1`                                                                                                |
| Runtime `kubectl -n techx-tf4 get pdb`                     | Đã có `opensearch-pdb` với `MAX UNAVAILABLE=1`, `ALLOWED DISRUPTIONS=1`; chưa thấy PDB cho revenue path services trong scope CDO08                  |
| Runtime `kubectl -n techx-tf4 describe pdb opensearch-pdb` | `opensearch-pdb` có `Max unavailable: 1`, `Current: 1`, `Desired: 0`, `Total: 1`; PDB này cho phép voluntary disruption với pod OpenSearch duy nhất |
| Runtime probe evidence                                     | App service critical và stateful dependencies chưa có readiness/liveness probes; observability subcharts có probes riêng                            |
| Checkout criticality                                       | `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `product-catalog`, `shipping`, `quote`, `currency` nằm trong hoặc gần revenue path     |

Runtime evidence chính:

```bash
kubectl -n techx-tf4 get deploy -o custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas,AVAILABLE:.status.availableReplicas
kubectl -n techx-tf4 get sts -o custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas
kubectl -n techx-tf4 get pdb
```

Kết luận runtime: hiện tại chưa có service critical trong revenue path nào đủ replica để PDB có hiệu quả availability rõ ràng mà không làm tăng rủi ro chặn eviction. Runtime đã có `opensearch-pdb`, nhưng đây là observability/stateful workload ngoài nhóm revenue path chính. PDB này cần review riêng vì `opensearch` hiện chỉ có 1 replica và cấu hình `maxUnavailable: 1` đang cho phép voluntary disruption với pod duy nhất.

## 4. PDB candidate table

| Service           | Current replicas | Candidate decision                           | Proposed minAvailable                                   | Prerequisite trước khi tạo PDB                                                   | Risk nếu không có PDB                                              | Risk nếu tạo sai lúc còn 1 replica                                                                                         | Cost/perf dependency                                                       | Proposed follow-up                                                  |
| ----------------- | ---------------: | -------------------------------------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `frontend-proxy`  |                1 | Candidate P0 sau khi tăng replica            | `1` khi có >=2 replicas                                 | Tăng replicas tối thiểu 2; thêm readiness cho entrypoint; verify ALB route       | Node drain có thể làm public entrypoint unavailable                | `minAvailable: 1` có thể block drain vì chỉ có 1 pod                                                                       | CDO04 xác nhận resource cho thêm Envoy pod                                 | Tạo PDB cùng task tăng replica/probe cho entrypoint                 |
| `frontend`        |                1 | Candidate P0 sau khi tăng replica            | `1` khi có >=2 replicas                                 | Tăng replicas tối thiểu 2; thêm HTTP readiness hoặc health route                 | Storefront UI/API gián đoạn khi pod bị evict                       | PDB có thể block drain hoặc không tạo thêm availability thực tế                                                            | Tăng CPU/memory cho frontend pod                                           | Tăng replica + readiness + PDB baseline                             |
| `checkout`        |                1 | Candidate P0 sau khi tăng replica            | `1` khi có >=2 replicas                                 | Tăng replicas tối thiểu 2; readiness gRPC health; smoke test checkout            | Checkout success SLO có thể bị ảnh hưởng khi voluntary eviction    | PDB single-replica có thể làm maintenance kẹt                                                                              | Cost nhỏ hơn business impact; cần Quân confirm criticality                 | Tạo follow-up revenue path availability hardening                   |
| `cart`            |                1 | Candidate P0 sau khi tăng replica            | `1` khi có >=2 replicas                                 | Tăng replicas app tối thiểu 2; readiness kiểm tra app và Valkey nhẹ              | Cart API có thể gián đoạn khi pod bị evict                         | PDB không giải quyết Valkey single point of failure                                                                        | App cost thấp; Valkey dependency vẫn cần xử lý riêng                       | Tăng cart replicas + readiness, song song Valkey reliability        |
| `payment`         |                1 | Candidate P0 sau khi tăng replica            | `1` khi có >=2 replicas                                 | Tăng replicas tối thiểu 2; readiness/liveness phù hợp; graceful shutdown         | Payment path có thể fail khi voluntary eviction trúng pod duy nhất | PDB single-replica có thể block drain                                                                                      | Cost thấp-vừa; cần smoke test checkout payment path                        | Tăng replica + readiness + PDB candidate                            |
| `product-catalog` |                1 | Candidate P0 sau khi tăng replica            | `1` khi có >=2 replicas                                 | Tăng replicas tối thiểu 2; readiness có DB ping nhẹ; kiểm soát DB connection     | Browse và checkout lookup có thể degrade khi pod bị evict          | PDB có thể block drain, chưa giải quyết DB dependency                                                                      | Tăng replicas có thể tăng DB connection pressure; cần CDO04/data owner     | Tăng replica sau khi DB pool/readiness được review                  |
| `shipping`        |                1 | Candidate P0/P1 sau checkout confirmation    | `1` khi có >=2 replicas                                 | Xác nhận checkout dependency với Quân; tăng replicas; thêm probe                 | Checkout shipping step có thể fail khi pod bị evict                | PDB single-replica có thể block drain                                                                                      | Cost thấp                                                                  | Add PDB sau khi tăng replica nếu checkout smoke test phụ thuộc mạnh |
| `quote`           |                1 | Candidate P0/P1 sau checkout confirmation    | `1` khi có >=2 replicas                                 | Xác định health capability; tăng replicas; thêm probe                            | Quote/shipping cost flow có thể gián đoạn                          | PDB single-replica có thể block drain                                                                                      | Cost thấp                                                                  | Add PDB cùng probe/replica hardening                                |
| `currency`        |                1 | Candidate P0/P1 sau checkout confirmation    | `1` khi có >=2 replicas                                 | Tăng replicas; gRPC readiness nếu có probe support                               | Price conversion có thể gián đoạn                                  | PDB single-replica có thể block drain                                                                                      | Cost thấp                                                                  | Add PDB sau khi tăng replica và smoke test conversion               |
| `postgresql`      |                1 | Defer, không tạo PDB cơ học                  | N/A hiện tại                                            | Thiết kế persistence, backup/restore, readiness, HA hoặc migration path          | DB pod eviction có thể ảnh hưởng nhiều service                     | PDB có thể block maintenance nhưng không tạo HA; có thể che thiếu thiết kế DB                                              | HA DB cost/complexity cao; cần CDO04 và data owner                         | Follow-up PostgreSQL HA/backup/restore trước khi xét PDB            |
| `valkey-cart`     |                1 | Defer, không tạo PDB cơ học                  | N/A hiện tại                                            | Xác định persistence/replication hoặc mitigation mất cart; readiness `PING`      | Cart state có thể mất/gián đoạn khi pod bị evict                   | PDB single-replica block drain nhưng không giải quyết data loss                                                            | Stateful HA cost cao hơn app replica; cần CDO04/data owner                 | Follow-up Valkey persistence/HA trước khi xét PDB                   |
| `kafka`           |                1 | Defer, cần thiết kế Kafka reliability trước  | N/A hiện tại                                            | Broker HA/durability, readiness, consumer lag monitoring                         | Post-order events có thể lag/mất khi broker bị evict               | PDB single-broker có thể block drain nhưng không tạo quorum HA                                                             | Kafka HA tăng resource đáng kể; cần CDO04                                  | Follow-up Kafka durability/HA trước PDB                             |
| `flagd`           |                1 | Candidate P1 nhưng cần flagd safety review   | `1` khi có >=2 replicas và sync an toàn                 | Xác nhận flagd sync/source với Thuỷ; không phá incident mechanism                | Feature flag/incident mechanism có thể bị gián đoạn                | PDB có thể block drain hoặc che vấn đề sync nếu replica không an toàn                                                      | Cần Thuỷ review; cost thấp-vừa                                             | Review flagd replica safety trước khi tạo PDB                       |
| `opensearch`      |                1 | Existing PDB, review riêng với observability | Existing `maxUnavailable: 1`                            | Xác nhận owner/SLO observability; đánh giá lại khi tăng replica hoặc đổi storage | Telemetry/search có thể gián đoạn khi voluntary disruption         | Với 1 replica, `maxUnavailable: 1` cho phép voluntary disruption với pod duy nhất (`Desired: 0`, `Allowed disruptions: 1`) | Thuộc observability/storage cost; cần owner Quyết hoặc observability owner | Review existing `opensearch-pdb` ở task observability nếu cần       |
| `product-reviews` |                1 | Candidate P1/P2 sau AI dependency review     | `1` khi có >=2 replicas                                 | Xác nhận DB/LLM constraints; readiness phù hợp                                   | AI review UX có thể degrade khi pod bị evict                       | PDB single-replica không có lợi rõ                                                                                         | Tăng replicas có thể tăng DB/LLM call/cost                                 | Defer sau P0 checkout path                                          |
| `recommendation`  |                1 | Defer                                        | `1` nếu sau này có >=2 replicas và SLO yêu cầu          | Product/SLO yêu cầu rõ; thêm probe                                               | UX recommendation degrade khi eviction                             | PDB single-replica không có lợi rõ                                                                                         | Cost thấp-vừa                                                              | Defer sau P0/P1                                                     |
| `email`           |                1 | Defer                                        | `1` nếu sau này có >=2 replicas và delivery SLO yêu cầu | Review retry/queue semantics trước                                               | Email confirmation có thể delay/fail                               | PDB không giải quyết delivery guarantee                                                                                    | Replica/PDB không thay thế retry/queue                                     | Defer, ưu tiên reliability semantics                                |
| `ad`              |                1 | Defer                                        | N/A hiện tại                                            | Chỉ xét nếu UX/SLO yêu cầu                                                       | Ít ảnh hưởng checkout trực tiếp                                    | PDB single-replica không có lợi rõ                                                                                         | Cost thấp                                                                  | Defer                                                               |

## 5. Priority recommendation

### 5.1 P0 candidate group

Nên ưu tiên thiết kế PDB sau khi tăng replica cho:

- `frontend-proxy`
- `frontend`
- `checkout`
- `cart`
- `payment`
- `product-catalog`
- `shipping`
- `quote`
- `currency`

Đề xuất baseline sau khi có 2 replicas và readiness phù hợp:

```yaml
minAvailable: 1
```

Không dùng `maxUnavailable: 0` mặc định cho nhóm này vì dễ gây hiểu nhầm vận hành; với 2 replicas, `minAvailable: 1` rõ ràng hơn và cho phép một pod bị voluntary eviction trong khi vẫn giữ một pod available.

### 5.2 Stateful dependency group

`postgresql`, `valkey-cart`, `kafka` là dependency quan trọng nhưng chưa nên tạo PDB chỉ dựa trên single replica hiện tại. Runtime cũng đang có `opensearch-pdb`; PDB này nên được review bởi observability owner vì `opensearch` hiện vẫn chỉ có 1 replica.

Đề xuất tuần 2-3:

- PostgreSQL: ưu tiên persistence, backup/restore, readiness và HA/migration path.
- Valkey: ưu tiên persistence/replication hoặc mitigation mất cart.
- Kafka: ưu tiên durability, broker readiness, producer/consumer reliability và consumer lag evidence.

### 5.3 P1/P2 defer group

`flagd`, `product-reviews`, `recommendation`, `email`, `ad` nên được review sau P0 hoặc khi owner/SLO yêu cầu. Riêng `flagd` cần phối hợp Thuỷ vì không được phá flagd sync hoặc incident mechanism của BTC.

## 6. Follow-up tasks tuần 2-3

| Follow-up                                                                                                          | Priority draft | Dependency                                                    | Test/verification                                                                                           |
| ------------------------------------------------------------------------------------------------------------------ | -------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Tăng replicas + readiness + PDB cho `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `product-catalog` | P0             | CDO04 cost/resource; Quân checkout criticality; Nguyên review | Helm upgrade; `kubectl get deploy`; smoke test browse/cart/checkout; node drain simulation nếu được approve |
| Review PDB cho `shipping`, `quote`, `currency` sau khi confirm checkout dependency                                 | P0/P1          | Quân checkout path; CDO04 cost                                | Checkout smoke test qua shipping/quote/currency path                                                        |
| Thiết kế PostgreSQL reliability trước PDB                                                                          | P0             | Data owner; CDO04 cost                                        | DB restart/drain scenario, backup/restore evidence                                                          |
| Thiết kế Valkey cart persistence/replication trước PDB                                                             | P0             | Data owner; CDO04 cost                                        | Cart survives pod restart nếu có persistence; cart smoke test                                               |
| Thiết kế Kafka reliability trước PDB                                                                               | P1             | Data/event owner; CDO04 cost                                  | Produce/consume test, consumer lag, broker restart behavior                                                 |
| Review flagd replica/PDB safety                                                                                    | P1             | Thuỷ flagd owner                                              | Verify flagd source/sync không đổi sau rollout                                                              |

## 7. Runtime verification status

Status hiện tại: **Completed for candidate analysis**.

Runtime evidence đã đủ cho task này:

- `kubectl -n techx-tf4 get deploy` xác nhận service critical hiện đều `DESIRED=1`, `READY=1`, `AVAILABLE=1`.
- `kubectl -n techx-tf4 get sts` xác nhận `opensearch` hiện `DESIRED=1`, `READY=1`.
- `kubectl -n techx-tf4 get pdb` xác nhận đang có `opensearch-pdb` với `MAX UNAVAILABLE=1`, `ALLOWED DISRUPTIONS=1`.
- `kubectl -n techx-tf4 describe pdb opensearch-pdb` xác nhận `Max unavailable: 1`, `Current: 1`, `Desired: 0`, `Total: 1`, nghĩa là PDB hiện cho phép voluntary disruption với pod OpenSearch duy nhất.
- Probe evidence xác nhận app services chưa có readiness/liveness probes, nên PDB nên đi sau probe hardening.

Task này không yêu cầu apply PDB hay test node drain thật. Node drain/eviction test chỉ nên làm ở follow-up khi có approval.

## 8. Definition of Done checklist

- [x] Candidate table completed.
- [x] Prerequisites documented.
- [x] Cost dependency marked.
- [x] Follow-up tasks proposed.
- [x] Minimum coverage includes revenue path and stateful dependencies.
- [x] No production PDB YAML created by this task.
