# CDO08-REL-28 ADR: RTO/RPO Cho Kịch Bản Mất 1 AZ

**Task:** CDO08-REL-28  
**Mandate:** MANDATE-21 - DR Failover  
**Ngày quyết định:** 2026-07-28  
**Trạng thái:** Proposed - sẵn sàng để PM/Tech Lead ký trước REL-35  
**Scope đi kèm:** `docs/cdo08/week3/mandate21/adr/CDO08-REL-28-revenue-path-scope.md`

## 1. Bối cảnh

Mandate 21 yêu cầu hệ thống chịu được mất đột ngột 1 Availability Zone dưới tải thật. Đây không phải rolling restart hoặc node drain có kế hoạch. Mentor có thể gây mất một AZ bất kỳ, vào thời điểm bất kỳ, nên hệ thống phải sẵn sàng trước, không chuẩn bị riêng cho lúc demo.

Điểm chấm chính:

- RTO thực: mất bao lâu để luồng browse/cart/checkout phục hồi về ngưỡng chấp nhận.
- RPO thực: có mất confirmed order hay không.
- Bằng chứng phải lấy từ runtime/dashboard/reconcile, không chỉ từ cấu hình Multi-AZ.

## 2. Quyết định

CDO08 chọn mục tiêu Mandate 21 cho phạm vi TF4 như sau:

| Luồng/dữ liệu | Target | Lý do |
|---|---:|---|
| Browse success | RTO <= 5 phút hoặc không rớt dưới ngưỡng SLO 99.5% trong cửa sổ 5 phút | Browse là customer-facing nhưng không tạo transaction; 5 phút cho phép endpoint/controller/K8s phản ứng với AZ failure thật. |
| Cart API success | RTO <= 5 phút hoặc không rớt dưới ngưỡng SLO 99.5% trong cửa sổ 5 phút | Cart nằm trong funnel mua hàng, nhưng cart data đã được PM/owner xem là reconstructable. |
| Checkout success | RTO <= 5 phút hoặc không rớt dưới ngưỡng SLO 99.0% trong cửa sổ 5 phút | Checkout là revenue-critical SLO surface, dùng dashboard hiện có. |
| Confirmed orders | RPO = 0 lost confirmed orders | Đây là business-data bar bắt buộc. Đo bằng expected order count, MSK order event, accounting record và duplicate/missing check. |
| Cart state | Không cam kết RPO cart | Cart là reconstructable; không dùng mất cart để claim fail/pass RPO confirmed order. |
| Post-checkout async processing | Catch up <= 10 phút sau failure window, không lost/duplicate confirmed order | Accounting/fraud có thể single replica nếu MSK giữ event và consumer resume đúng. |

## 3. Cách đo RTO

RTO được tính theo một trong hai cách, chọn cách có bằng chứng rõ nhất trong drill:

1. Nếu mentor công bố timestamp bắt đầu gây AZ failure:
   - `RTO = thời điểm Checkout Success trở lại >= 99.0% ổn định trong 5 phút - timestamp bắt đầu failure`.

2. Nếu không có timestamp chính xác từ mentor:
   - `RTO = thời điểm Checkout Success trở lại >= 99.0% ổn định trong 5 phút - thời điểm dashboard bắt đầu SLO dip`.

Panel/query dùng để đo:

- `Checkout Success Rate` trong `checkout-revenue-dashboard`.
- `Business Flow Health Overview`: browse/cart/checkout success.
- `Checkout Error Rate`, p95/p99 latency, request volume để xác nhận không phải do không có traffic.
- Pod/node/AZ observer từ REL-33 để đối chiếu thời điểm endpoint/pod bị mất.

## 4. Cách đo RPO

RPO confirmed order được đo bằng đối soát:

```text
expected confirmed order count trong failure window
  == MSK orders event count
  == accounting persisted/reconciled order count
  không có missing order
  không có duplicate order gây double accounting
```

Nguồn evidence:

- MSK topic `orders` hoặc replay/reconcile tooling từ Mandate 20.
- Accounting schema trong RDS PostgreSQL.
- Application/checkout result trong load window.
- Consumer lag của `accounting` và `fraud-detection`.

Không dùng cart key count làm RPO target vì cart đã được phân loại reconstructable.

## 5. Điều kiện GO trước drill

Không bắt đầu REL-35 nếu còn một trong các trạng thái sau:

- Workload trong customer synchronous path có pod `Pending`, `CreateContainerConfigError`, `CrashLoopBackOff`, `ImagePullBackOff` hoặc rollout chưa ổn định.
- `frontend-proxy`, `frontend`, `product-catalog`, `cart`, `checkout`, `payment`, `shipping`, `currency`, `quote` không có đủ endpoint Ready theo scope đã chốt.
- RDS, Valkey hoặc MSK không ở trạng thái `available`/`ACTIVE`.
- Prometheus/Grafana không đủ ổn định để đo SLO.
- Không có load đang chạy hoặc không có request volume đủ để tính SLO/RTO.
- Không có cách reconcile expected/actual confirmed orders.

Scan ngày 2026-07-28 cho thấy hiện **chưa GO drill** vì:

- `frontend` có 2 pod mới kẹt `CreateContainerConfigError` do thiếu Secret `ai-state-hmac-secret`; deployment chỉ còn 1 available.
- `product-reviews` có 1 pod `Pending` do nodepool/placement constraints. Đây không phải checkout core blocker nếu frontend không phụ thuộc cứng, nhưng vẫn cần owner xác nhận hoặc xử lý trước witnessed drill.

## 6. Trạng thái nền tảng hiện tại

| Thành phần | Scan result | Ý nghĩa |
|---|---|---|
| EKS nodes | 5 worker Ready, trải `us-east-1a` và `us-east-1b` | Đủ nền tảng 2-AZ để tiếp tục baseline; REL-29 cần chụp chi tiết capacity. |
| RDS PostgreSQL | `available`, `MultiAZ=true`, primary `us-east-1a`, standby `us-east-1b`, backup retention 7 ngày | Phù hợp target RPO confirmed orders, cần drill/validation để đo RTO thật. |
| ElastiCache Valkey | MultiAZ enabled, automatic failover enabled, TLS/AUTH enabled, primary/replica ở 2 AZ | Phù hợp availability cho cart path; không claim RPO cart. |
| MSK orders | `ACTIVE`, private, TLS/SASL enabled, 2 client subnets/AZ | Phù hợp để tiếp tục REL-31; cần broker/node-level evidence. |
| ResourceQuota | `limits.cpu` hard 14 cores, used 10.1 cores; pods hard 50, used 38 | Còn headroom quota ở snapshot, nhưng REL-29 phải tính lại với surge/failover. |

## 7. Quyết định về single-replica workload

Không tự động scale mọi workload 1 replica.

- `load-generator`: tooling tạo tải/evidence, không phải production SLO. Nếu mất, drill có thể mất nguồn tải nhưng customer path không outage. REL-34/REL-35 quyết định có cần chạy 2 nguồn tải để giữ evidence liên tục.
- `kafka-connect-orders-archive`: archive/RPO-supporting tooling, không nằm trong request path. Cần chứng minh resume/offset recovery nếu muốn dùng làm evidence RPO.
- `accounting` và `fraud-detection`: data correctness path. Có thể tạm giữ 1 replica nếu chứng minh MSK giữ event, consumer resume và lag hồi phục không mất/duplicate confirmed orders. Nếu không chứng minh được, REL-32 phải đề xuất scale/partition/consumer-group strategy phù hợp.

## 8. Hành động tiếp theo

1. PM/Tech Lead ký target RTO/RPO trong ADR này.
2. REL-29 chụp baseline đầy đủ node/pod/HPA/PDB/quota theo scope.
3. REL-30/REL-31 hoàn thiện managed-store failover readiness.
4. REL-32 xử lý các gap về replica/topology/PDB, đặc biệt `frontend` blocker và cart placement.
5. REL-33/REL-34 chuẩn bị runbook/observer/dashboard trước khi REL-35 chạy witnessed drill.

## 9. Kết luận REL-28

REL-28 hoàn tất phần phân tích và chốt đề xuất scope/RTO/RPO. Hệ thống có nền tảng đúng hướng cho Mandate 21, nhưng chưa được phép chạy drill cuối cho đến khi các runtime blocker và evidence gap đã được xử lý ở REL-29 đến REL-34.
