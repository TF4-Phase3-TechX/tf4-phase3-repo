# CDO08-REL-28 Revenue Path Scope Cho Mandate 21

**Task:** CDO08-REL-28  
**Mandate:** MANDATE-21 - DR Failover  
**Ngày scan:** 2026-07-28  
**Cluster:** `techx-tf4-cluster`  
**Namespace chính:** `techx-tf4`  
**Kết luận:** scope đã đủ rõ để REL-29/REL-32/REL-35 tiếp tục, nhưng hệ thống hiện chưa đủ điều kiện GO drill vì còn runtime blocker ở `frontend` và `product-reviews`.

## 1. Mục tiêu scope

Mandate 21 không chấm việc bật Multi-AZ trên giấy. Scope này định nghĩa rõ khi mất 1 AZ thì luồng nào phải sống, dữ liệu nào không được mất, và workload nào chỉ là tooling hoặc async để tránh scale bừa.

Luồng cần bảo vệ:

```text
Browser / ALB
  -> frontend-proxy
  -> frontend
  -> product-catalog / cart
  -> checkout
  -> payment / shipping / currency / quote / email
  -> MSK orders
  -> accounting / fraud-detection
  -> RDS PostgreSQL
```

## 2. Phân loại workload

| Nhóm | Workload | Vai trò | Yêu cầu khi mất 1 AZ |
|---|---|---|---|
| Customer synchronous path | `frontend-proxy`, `frontend`, `product-catalog`, `cart`, `checkout`, `payment`, `shipping`, `currency`, `quote` | Trực tiếp ảnh hưởng browse/cart/checkout | Phải còn endpoint Ready ở AZ lành hoặc phục hồi trong RTO cam kết. |
| Post-checkout notification | `email` | Gửi email sau checkout | Không được làm fail confirmed order; có thể recover async nếu không mất event. |
| Data correctness path | `accounting`, `fraud-detection` | Consume order event từ MSK, ghi nhận/truy vết sau checkout | Không được mất confirmed order; nếu single replica thì phải chứng minh consumer resume, lag hồi phục và không duplicate/lost event. |
| AI/review supporting path | `product-reviews`, `llm`, `aiops` | Không nằm trong checkout core, nhưng có thể ảnh hưởng browse/review UX | Không phải điều kiện pass chính cho checkout, nhưng không được làm hỏng homepage/browse nếu frontend phụ thuộc cứng. |
| Platform data stores | RDS PostgreSQL, ElastiCache Valkey, MSK | Lưu dữ liệu/order/session/event | Phải Multi-AZ/managed failover hoặc có recovery path đã đo. |
| Observability/load tooling | `load-generator`, Grafana, Prometheus, Jaeger, `kafka-connect-orders-archive` | Tạo tải, đo và lưu evidence/archive | Không phải customer SLO path; nếu mất thì ảnh hưởng khả năng chứng minh hoặc RPO archive, không tự động tính là customer outage. |
| Feature/config supporting | `flagd` | Feature flag provider | Không thuộc app-owned image path; nếu frontend/checkout phụ thuộc cứng thì phải có fallback hoặc runbook riêng. |

## 3. Dữ liệu cần bảo vệ

| Dữ liệu | Nguồn hiện tại | RPO target | Ghi chú |
|---|---|---:|---|
| Confirmed order event | MSK `orders` | 0 lost confirmed orders | Đây là dữ liệu chính để chứng minh RPO. |
| Accounting records | RDS PostgreSQL database `otel`, schema accounting | 0 lost confirmed orders sau reconcile | RDS đang Multi-AZ, backup retention 7 ngày. |
| Cart state | ElastiCache Valkey | Không claim RPO cart | Cart được coi là reconstructable theo quyết định PM/owner trước đó. Không dùng cart loss để claim fail/pass RPO confirmed order. |
| Telemetry/evidence | Prometheus/Grafana/Jaeger/S3 archive | Best effort cho drill evidence | Không phải business data, nhưng cần sẵn sàng trước REL-35 để đo RTO/RPO. |

## 4. Runtime scan hiện tại

### 4.1 Node/AZ

`kubectl get nodes -L topology.kubernetes.io/zone -o wide` ghi nhận 5 worker `Ready` trải 2 AZ:

| AZ | Node |
|---|---|
| `us-east-1a` | `ip-10-0-10-182`, `ip-10-0-10-19` |
| `us-east-1b` | `ip-10-0-11-17`, `ip-10-0-11-192`, `ip-10-0-11-82` |

### 4.2 Customer synchronous path

| Workload | Desired/ready hiện tại | Placement quan sát | Nhận xét |
|---|---:|---|---|
| `frontend-proxy` | 2/2 | `us-east-1a`, `us-east-1b` | Đạt baseline HA theo AZ. |
| `frontend` | 1/2 available, 2 pod mới lỗi config | Running pod chỉ ở `us-east-1a`; 2 pod mới kẹt `CreateContainerConfigError` | **Blocker trước drill**: thiếu Secret `ai-state-hmac-secret`. |
| `product-catalog` | 2/2 | `us-east-1a`, `us-east-1b` | Đạt baseline HA theo AZ. |
| `cart` | 2/2 | Cả 2 pod đang ở `us-east-1a` | Cần REL-32 xử lý topology/placement nếu cart được giữ trong customer path. |
| `checkout` | 2/2 | `us-east-1a`, `us-east-1b` | Đạt baseline HA theo AZ. |
| `payment` | 2/2 | `us-east-1a`, `us-east-1b` | Đạt baseline HA theo AZ. |
| `shipping` | 2/2 | `us-east-1a`, `us-east-1b` | Đạt baseline HA theo AZ. |
| `currency` | 2/2 | `us-east-1a`, `us-east-1b` | Đạt baseline HA theo AZ. |
| `quote` | 2/2 | `us-east-1a`, `us-east-1b` | Đạt baseline HA theo AZ. |

### 4.3 Async/data correctness path

| Workload | Desired/ready hiện tại | Strategy | Nhận xét |
|---|---:|---|---|
| `accounting` | 1/1 | `Recreate` | Single replica có chủ ý để tránh double-process Kafka. Không được xem là AZ-HA cho compute; phải chứng minh MSK durability + consumer resume + reconcile. |
| `fraud-detection` | 1/1 | `Recreate` | Tương tự accounting. |
| `email` | 2/2 | RollingUpdate | Async notification, không được làm fail confirmed order. |
| `kafka-connect-orders-archive` | 1/1 | RollingUpdate | Archive tooling; nếu mất tạm thời phải chứng minh connector resume hoặc có retry/offset recovery. |
| `load-generator` | 1/1 | RollingUpdate | Chỉ phục vụ drill/load evidence, không ảnh hưởng customer SLO. |

## 5. Managed store scan hiện tại

| Store | Live state | Kết luận cho scope REL-28 |
|---|---|---|
| RDS PostgreSQL `techx-tf4-postgresql` | `available`, `MultiAZ=true`, primary `us-east-1a`, standby `us-east-1b`, private endpoint, deletion protection on, backup retention 7 ngày | Đủ đưa vào RPO confirmed order; REL-30 cần giữ command output làm evidence. |
| ElastiCache Valkey `techx-tf4-valkey-cart` | `available`, MultiAZ enabled, automatic failover enabled, TLS enabled, AUTH enabled, primary `us-east-1b`, replica `us-east-1a` | Đủ cho availability cart path; không claim RPO cart vì cart reconstructable. |
| MSK `techx-tf4-orders` | `ACTIVE`, provisioned, private, 2 client subnets/AZ, TLS/SASL enabled | Đủ để REL-31 tiếp tục. Broker-level node placement cần thêm quyền `kafka:ListNodes` hoặc evidence thay thế. |

## 6. Scope PASS/FAIL cho Mandate 21

### PASS nếu

- Browse/cart/checkout vẫn đạt ngưỡng SLO đã chốt hoặc phục hồi trong RTO cam kết sau khi mất 1 AZ.
- Confirmed orders trong cửa sổ drill không bị mất: expected order count khớp với accounting/MSK reconciliation.
- Không có duplicate order gây sai lệch business result.
- RDS/Valkey/MSK tự failover hoặc client reconnect mà không cần sửa tay từng service.
- Các pod thuộc customer synchronous path có endpoint Ready ở AZ lành hoặc được Kubernetes reschedule tự động.

### FAIL nếu

- Mất 1 AZ làm `frontend-proxy`, `frontend`, `cart`, `checkout`, `payment`, `shipping`, `currency`, `product-catalog` không còn endpoint phục vụ trong RTO.
- Có confirmed order bị mất khỏi MSK/accounting.
- Cần direct patch thủ công live workload mới phục hồi được luồng chính.
- Runtime đang có hard blocker trước drill như `CreateContainerConfigError`, `Pending`, `ImagePullBackOff`, `CrashLoopBackOff` trên workload trong scope.

## 7. Handoff cho các task sau

- REL-29: dùng danh sách workload trong mục 2 để chụp baseline pod/node/PDB/HPA/quota.
- REL-30: giữ evidence RDS/Valkey Multi-AZ và endpoint/secret không hard-code IP.
- REL-31: hoàn thiện MSK broker placement, topic/order lag và client reconnect evidence.
- REL-32: chỉ scale/spread những workload thuộc customer synchronous path hoặc data correctness path đã được phân loại; không scale `load-generator` chỉ vì đang 1 replica.
- REL-33/REL-34: build observer/dashboard theo PASS/FAIL ở mục 6.
- REL-35: chỉ chạy drill khi các blocker runtime ở mục 4 đã được xử lý hoặc có owner ký chấp nhận rõ.
