# Replica Coverage Matrix - Service Critical

## 0. Task metadata

| Field            | Value                                                                     |
| ---------------- | ------------------------------------------------------------------------- |
| Jira task        | `[Runtime] Audit replica coverage cho service critical`                   |
| Owner / Assignee | Hoàng Nam                                                                 |
| Area / Ownership | Kubernetes Runtime Reliability                                            |
| Pillar           | Reliability                                                               |
| Priority         | P0                                                                        |
| Reviewer         | Nguyên                                                                    |
| Output artifact  | `docs/cdo08/week1/replica-coverage-matrix.md`                             |
| Current status   | Static analysis completed; runtime verification pending                   |
| Runtime blocker  | CDO08 chưa có EKS access/kubeconfig hợp lệ để chạy `kubectl` verification |
| Last updated     | 2026-07-07                                                                |

## 1. Mục tiêu

Task này audit replica coverage hiện tại của các service critical trong chart Phase 3 để xác định service nào đang chạy single-replica và cần được ưu tiên hardening availability trong tuần 2-3.

Scope của task này là **static analysis từ source/chart**, chưa thay đổi replica count.

## 2. Nguồn evidence

### 2.1 Quy tắc replica trong chart

| File                                      | Line | Evidence                                                       | Ý nghĩa                                                                        |
| ----------------------------------------- | ---: | -------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `techx-corp-chart/values.yaml`            |   28 | `default.replicas: 1`                                          | Nếu component không khai báo replica riêng thì mặc định chạy 1 replica         |
| `techx-corp-chart/templates/_objects.tpl` |   13 | `replicas: {{ .replicas \| default .defaultValues.replicas }}` | Deployment dùng replica riêng của component nếu có, nếu không thì dùng default |

### 2.2 Component evidence trong `values.yaml`

| Component         | Component line | Replica line | Kết luận                                                    |
| ----------------- | -------------: | -----------: | ----------------------------------------------------------- |
| `ad`              |            195 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `cart`            |            218 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `checkout`        |            247 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `currency`        |            288 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `email`           |            309 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `frontend`        |            359 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `frontend-proxy`  |            412 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `payment`         |            538 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `product-catalog` |            565 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `product-reviews` |            592 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `quote`           |            633 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `recommendation`  |            660 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `shipping`        |            687 |          N/A | Không khai báo replica riêng, kế thừa `default.replicas: 1` |
| `flagd`           |            708 |          715 | Khai báo explicit `replicas: 1`                             |
| `kafka`           |            783 |          787 | Khai báo explicit `replicas: 1`                             |
| `postgresql`      |            830 |          837 | Khai báo explicit `replicas: 1`                             |
| `valkey-cart`     |            881 |          888 | Khai báo explicit `replicas: 1`                             |

Kết luận evidence: phần lớn app service **không khai báo `replicas` riêng**, nên kế thừa `default.replicas: 1`. Các component `flagd`, `kafka`, `postgresql`, `valkey-cart` khai báo explicit `replicas: 1`.

## 3. Criticality scale

| Criticality | Ý nghĩa                                                                                                 |
| ----------- | ------------------------------------------------------------------------------------------------------- |
| P0          | Entry point, checkout/revenue path, hoặc dependency stateful nếu down sẽ ảnh hưởng lớn tới SLO/business |
| P1          | Quan trọng cho trải nghiệm, observability hoặc post-order flow; nên harden sau P0                       |
| P2          | Có thể degrade tạm thời hoặc ít ảnh hưởng trực tiếp tới checkout                                        |

## 4. Replica coverage matrix

| Service           | Current replicas | Replica source                 | Criticality | Single-replica risk                                                                                     | Desired direction                                                                              | Proposed follow-up                                                                 | Cost/perf note                                                                  |
| ----------------- | ---------------: | ------------------------------ | ----------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `frontend-proxy`  |                1 | Inherits `default.replicas: 1` | P0          | Public entrypoint single pod; pod crash/rollout/node drain có thể làm toàn storefront unavailable       | Tối thiểu 2 replicas cho baseline availability                                                 | Tạo task tuần 2-3 tăng replicas + readiness + PDB candidate                        | Tăng pod Envoy, cost thấp-vừa; cần CDO04 xác nhận resource                      |
| `frontend`        |                1 | Inherits `default.replicas: 1` | P0          | Storefront UI/API layer single pod; ảnh hưởng browse/cart/checkout UX                                   | Tối thiểu 2 replicas                                                                           | Tăng replicas sau khi có resource requests và smoke test                           | Tăng CPU/memory runtime, cần CDO04 nếu node pressure                            |
| `checkout`        |                1 | Inherits `default.replicas: 1` | P0          | Revenue path single pod; crash/rollout có thể làm checkout fail hoàn toàn                               | Tối thiểu 2 replicas                                                                           | Tăng replicas + validate idempotency/timeout/readiness trước rollout               | Rất đáng ưu tiên; cost nhỏ hơn business impact                                  |
| `cart`            |                1 | Inherits `default.replicas: 1` | P0          | Cart API single pod; ảnh hưởng add/remove/get cart và checkout precondition                             | Tối thiểu 2 replicas nếu Valkey ổn định                                                        | Tăng replicas + readiness ping Valkey                                              | App replicas tăng ít cost; dependency Valkey vẫn là bottleneck                  |
| `product-catalog` |                1 | Inherits `default.replicas: 1` | P0          | Product browse và checkout item lookup phụ thuộc service này; crash gây browse/checkout degradation     | Tối thiểu 2 replicas                                                                           | Tăng replicas + DB pool limit/readiness DB                                         | Tăng replicas có thể tăng DB connection pressure; cần phối hợp data owner/CDO04 |
| `payment`         |                1 | Inherits `default.replicas: 1` | P0          | Payment là bước revenue-critical; single pod dễ gây checkout failure khi rollout/crash                  | Tối thiểu 2 replicas                                                                           | Tăng replicas + readiness/shutdown graceful                                        | Cost thấp-vừa; cần test deploy không route vào pod chưa ready                   |
| `shipping`        |                1 | Inherits `default.replicas: 1` | P0          | Checkout gọi shipping; single pod crash có thể làm checkout fail sau payment/quote                      | Tối thiểu 2 replicas                                                                           | Tăng replicas + probe coverage                                                     | Cost thấp                                                                       |
| `quote`           |                1 | Inherits `default.replicas: 1` | P0          | Checkout cần quote shipping; single pod crash làm checkout không hoàn tất                               | Tối thiểu 2 replicas                                                                           | Tăng replicas + probe coverage                                                     | Cost thấp                                                                       |
| `currency`        |                1 | Inherits `default.replicas: 1` | P0          | Checkout/product price conversion phụ thuộc currency; crash có thể ảnh hưởng checkout                   | Tối thiểu 2 replicas                                                                           | Tăng replicas + probe coverage                                                     | Cost thấp                                                                       |
| `postgresql`      |                1 | Explicit `replicas: 1`         | P0          | Stateful DB single point of failure; ảnh hưởng product-catalog, product-reviews, accounting             | Giữ baseline in-cluster theo yêu cầu Week 1; đánh giá persistence/HA/backup/migration path sau | Tạo follow-up cho PostgreSQL HA/backup/restore gap, chưa chỉ tăng replica đơn giản | HA DB tốn cost/complexity cao; cần CDO04 và data owner                          |
| `valkey-cart`     |                1 | Explicit `replicas: 1`         | P0          | Cart state single point of failure; khớp incident cart lost after reschedule                            | Giữ baseline in-cluster theo yêu cầu Week 1; đánh giá persistence/replication sau              | Tạo follow-up Valkey persistence/HA và cart readiness                              | Stateful HA/cost cao hơn app replicas; cần CDO04                                |
| `kafka`           |                1 | Explicit `replicas: 1`         | P1          | Order events/accounting/fraud phụ thuộc Kafka; single broker restart có thể mất/lag event               | Giữ baseline in-cluster theo yêu cầu Week 1; đánh giá reliability sau baseline                 | Follow-up Kafka durability/acks/consumer lag; HA Kafka cần thiết kế riêng          | Kafka HA tăng resource đáng kể; cần CDO04                                       |
| `flagd`           |                1 | Explicit `replicas: 1`         | P1          | Feature flag/incident mechanism phụ thuộc flagd; nếu down có thể làm behavior/incident control khó đoán | Cân nhắc 2 replicas nếu chart/flagd sync hỗ trợ an toàn                                        | Follow-up kiểm tra flagd sync + replica safety với Thuỷ                            | Không được phá flagd sync; phối hợp Secrets/flagd owner                         |
| `product-reviews` |                1 | Inherits `default.replicas: 1` | P1          | AI review feature single pod; không trực tiếp checkout nhưng ảnh hưởng AI UX/SLO best-effort            | 2 replicas nếu LLM/API/DB constraints cho phép                                                 | Follow-up sau khi AIO xác nhận LLM timeout/cache/readiness                         | Tăng replicas có thể tăng DB/LLM calls/cost                                     |
| `recommendation`  |                1 | Inherits `default.replicas: 1` | P2          | Recommendation degrade ảnh hưởng UX nhưng có thể không block checkout                                   | Defer hoặc 2 replicas sau P0/P1                                                                | Follow-up nếu SLO/product UX yêu cầu                                               | Cost thấp-vừa                                                                   |
| `email`           |                1 | Inherits `default.replicas: 1` | P2          | Email confirmation fail thường có thể warning/degrade, không nên block order nếu thiết kế đúng          | Defer; cân nhắc retry/queue hơn là chỉ replica                                                 | Follow-up sau checkout reliability review                                          | Replica tăng không giải quyết delivery guarantee                                |
| `ad`              |                1 | Inherits `default.replicas: 1` | P2          | Ad service failure ít ảnh hưởng revenue checkout trực tiếp                                              | Defer                                                                                          | Chỉ harden nếu observability cho thấy ảnh hưởng UX                                 | Cost thấp                                                                       |

## 5. P0/P1 single-replica risks ranked

| Rank | Priority | Service/group                    | Vì sao ưu tiên                                                                                           |
| ---: | -------- | -------------------------------- | -------------------------------------------------------------------------------------------------------- |
|    1 | P0       | `frontend-proxy`                 | Entry point duy nhất; nếu pod down thì nhiều route public bị ảnh hưởng                                   |
|    2 | P0       | `checkout`                       | Revenue-critical, trực tiếp ảnh hưởng checkout success SLO                                               |
|    3 | P0       | `payment`                        | Bước thanh toán trong checkout; deploy/crash có thể gây lỗi business nghiêm trọng                        |
|    4 | P0       | `cart` + `valkey-cart`           | Cart success SLO và checkout precondition; Valkey single point of failure                                |
|    5 | P0       | `product-catalog` + `postgresql` | Browse và checkout item lookup; DB pressure/single point ảnh hưởng nhiều service                         |
|    6 | P0       | `shipping`, `quote`, `currency`  | Downstream trực tiếp trong checkout path                                                                 |
|    7 | P1       | `kafka`                          | Post-order event durability/accounting/fraud; không luôn block checkout nhưng ảnh hưởng audit và backlog |
|    8 | P1       | `flagd`                          | Incident/feature flag mechanism; cần giữ an toàn sync                                                    |
|    9 | P1       | `product-reviews`                | AI feature có SLO riêng, nhưng không phải checkout-critical                                              |

## 6. Proposed follow-up tasks tuần 2-3

| Follow-up                                                                                                        | Priority draft | Dependency                                           | Test/verification                                 |
| ---------------------------------------------------------------------------------------------------------------- | -------------- | ---------------------------------------------------- | ------------------------------------------------- |
| Tăng replicas cho `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `product-catalog` lên tối thiểu 2 | P0             | CDO04 cost/resource; Quân xác nhận checkout-critical | Helm upgrade + smoke test browse/cart/checkout    |
| Tăng replicas cho `shipping`, `quote`, `currency` lên tối thiểu 2 nếu checkout smoke test phụ thuộc mạnh         | P0/P1          | Quân checkout path; CDO04 cost                       | Checkout smoke test và rollout test               |
| Đánh giá PostgreSQL in-cluster persistence/backup/restore/HA gap                                                 | P0             | Phương data owner; CDO04 cost                        | DB pod restart/drain scenario, backup evidence    |
| Đánh giá Valkey cart persistence/replication hoặc mitigation mất cart                                            | P0             | Phương data owner; CDO04 cost                        | Cart survives pod/node restart nếu có persistence |
| Đánh giá Kafka reliability: broker HA, producer ack, consumer lag                                                | P1             | Phương/Quân; CDO04 cost                              | Publish/consume order event test                  |
| Xác nhận flagd replica/sync safety trước khi tăng replica                                                        | P1             | Thuỷ flagd/secrets owner                             | Verify flagd sync source vẫn đúng sau upgrade     |

## 7. Cost/performance note cho CDO04

- Tăng replicas cho stateless service làm tăng pod count và CPU/memory footprint, nhưng thường là cách rẻ nhất để giảm downtime do pod crash/rollout.
- Với checkout path, cost tăng thêm thường dễ bảo vệ vì liên quan trực tiếp checkout success SLO và business impact.
- Với stateful services (`postgresql`, `valkey-cart`, `kafka`), không nên chỉ tăng replica một cách cơ học. Cần thiết kế persistence/replication/backup/restore đúng, vì tăng sai có thể gây split-brain, data inconsistency hoặc chi phí cao.
- PDB chỉ có ý nghĩa khi service có đủ replicas. Các service hiện single-replica cần tăng replica trước hoặc song song với PDB candidate review.

## 8. Runtime verification

Status hiện tại: **Blocked / Pending runtime verification**.

Static analysis từ chart đã hoàn thành, nhưng chưa thể chạy runtime verification bằng `kubectl` vì chưa có quyền truy cập hợp lệ vào EKS cluster của Phase 3 / TF4.

Blocker:

- Cần AWS account/role hoặc kubeconfig có quyền truy cập vào EKS cluster của TF4.
- Cần biết EKS cluster name, region, namespace deploy app, hoặc nhận kubeconfig đã cấu hình sẵn từ team deploy.
- Nếu CDO08 chưa được cấp quyền trực tiếp, có thể nhờ deploy owner chạy lệnh `kubectl` bên dưới và gửi output làm runtime evidence.

Khi environment sẵn sàng, cần chạy lại verification trong vòng 24h:

```bash
kubectl -n <namespace> get deploy,sts
kubectl -n <namespace> get deploy,sts -o custom-columns=KIND:.kind,NAME:.metadata.name,READY:.status.readyReplicas,DESIRED:.spec.replicas
```

Kết quả cần được paste/chụp vào phần này hoặc evidence pack chung của CDO08.

## 9. Definition of Done checklist

- [x] Matrix đủ service critical trong scope task.
- [x] Current replicas captured từ static chart values.
- [x] P0/P1 single-replica risks ranked.
- [x] Cost/perf note included.
- [x] Affected service/file/evidence/proposed follow-up có trong matrix.
- [ ] Runtime verification bằng `kubectl` sau khi có kubeconfig/context EKS TF4 hợp lệ.
