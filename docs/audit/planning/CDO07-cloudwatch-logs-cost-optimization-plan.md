# CDO-07 - Kế hoạch đánh giá và tối ưu chi phí EKS CloudWatch Logs

- **Trạng thái:** Draft - chờ CDO-04, CDO-07 và CDO-08 phê duyệt
- **Ngày lập:** 2026-07-29
- **Phạm vi:** `techx-tf4-cluster`, log group `/aws/eks/techx-tf4-cluster/cluster`
- **Người lập:** Hoàng Kim Hùng
- **Owners:** CDO-04 (Cost/Performance), CDO-07 (Audit), CDO-08 (Security/Reliability)

## 0. Kết luận rà soát lần cuối

Tài liệu này đã được đối chiếu với ADR-005, AUDIT-001, Mandate #4 và cấu hình Terraform hiện tại. Hướng phê duyệt an toàn nhất là **PA1 + PA2 có điều kiện**. Không phê duyệt PA3 như phương án thay thế hoàn toàn cho EKS control-plane audit.

Các điểm cần nói rõ trong buổi phê duyệt:

- Số liệu billing month-to-date là 448.1 GB, tương đương `$224.05`; nếu tốc độ 2.1 GB/giờ duy trì 24x7 thì run-rate mới là khoảng `$756/tháng`. Không trộn hai cách tính này với nhau.
- `PA2` chỉ giảm CloudWatch hot storage và chi phí downstream Firehose/S3/Athena. Phương án này **không** giảm CloudWatch Logs ingestion vì EKS đã đẩy log vào CloudWatch trước khi subscription/Lambda xử lý.
- `PA1` là cách giảm ingestion thực tế cho dev/staging nếu tắt `audit` ở các môi trường đó. Production và drill vẫn phải giữ `audit` + `authenticator` nếu muốn bảo toàn khả năng forensic control plane đầy đủ.
- `PA3` Falco eBPF không thay thế được EKS managed control-plane audit/authenticator. Chỉ nên phê duyệt PA3 như một pilot runtime detection bổ sung, sau khi CDO-07 chấp nhận forensic equivalence bằng test.
- AUDIT-001 gốc có một số yêu cầu đã được ADR-005/Terraform cập nhật: 5 log types -> 2 log types, 14 ngày -> 7 ngày, CMK -> SSE-S3, WORM 1 năm -> Object Lock 90 ngày + lifecycle 365 ngày. Các deviation này phải được CDO-07/CDO-08 xác nhận lại khi phê duyệt Task 79.

## 1. Quyết định đề xuất

Khuyến nghị phê duyệt phương án kết hợp **PA1 + PA2**:

1. Dev/staging chỉ bật `authenticator`; production và drill bật `audit` + `authenticator`.
2. Giữ audit archive qua CloudWatch subscription -> Firehose -> S3 Object Lock WORM; giảm CloudWatch hot retention xuống 1 ngày sau khi xác nhận S3/Athena forensic pass.
3. Mở rộng bộ lọc Lambda `is_noise` bằng allowlist rõ ràng cho health checks, node heartbeats, lease polling và EBS CSI 404; không lọc các thay đổi, đọc secret, exec, RBAC/IAM và request của người dùng.
4. Không triển khai PA3 như một phương án thay thế duy nhất cho EKS control-plane audit. Falco eBPF có thể bổ sung runtime detection, nhưng không phải nguồn audit từ managed EKS control plane.

> **Cảnh báo chi phí:** Retention và filter ở subscription không làm giảm CloudWatch Logs ingestion. Ingestion phát sinh khi EKS gửi log vào CloudWatch Logs; subscription/Lambda chỉ xử lý đầu ra sau đó. Muốn cắt khoản lớn nhất (~$0.50/GB theo evidence billing hiện tại), phải giảm log type/phạm vi môi trường tại EKS (PA1) hoặc có kênh audit thay thế được AWS/CDO-07 chấp nhận. Không được coi PA2 là phương án giảm trực tiếp ingestion.

## 2. Evidence và hiện trạng

Nguồn tham chiếu trong repo:

- `docs/audit/adr/005-eks-control-plane-logging-enabled.md` (ADR-005).
- `docs/audit/tickets/AUDIT-001-enable-eks-logs.md` (yêu cầu bật control-plane logging và lưu dài hạn).
- `docs/requirements/mandates/MANDATE-04-auditability-tf4.md` (forensic, tamper-evident, truy nguồn danh tính).
- `infra/terraform/eks.tf`.
- `infra/terraform/eks-audit-firehose.tf`.

### Runtime evidence do task cung cấp

| Nguồn | Events/giờ | Dung lượng/giờ | Tỷ trọng | Chi phí ingestion ước tính |
| ----- | ---------: | -------------: | -------: | -------------------------: |
| `authenticator` | 539 | 0.19 MB | không đáng kể | khoảng $0.07/tháng theo mẫu đo |
| `audit` | 124,878 | 2.10 GB | ~99.99% dung lượng | ~`$756/tháng` nếu duy trì 24x7 |
| Tổng log group MTD | - | 448.1 GB | >98% CloudWatch Logs | `$224.05` tại đơn giá $0.50/GB |

Số liệu 448.1 GB/$224.05 là chi phí month-to-date trong ảnh. Ngoài ra, 2.1 GB/giờ x 24 x 30 = 1,512 GB/tháng, tương đương run-rate khoảng $756/tháng. Khi trình phê duyệt, cần ghi rõ đây là hai cách nhìn khác nhau: chi phí đã phát sinh đến hiện tại và run-rate nếu lưu lượng duy trì liên tục.

### Cấu hình đang có trong repo

- EKS đang bật `cluster_enabled_log_types = ["audit", "authenticator"]`; `api`, `controllerManager`, `scheduler` đang tắt theo ADR-005.
- CloudWatch retention đang là 7 ngày, trong khi AUDIT-001 ban đầu khuyến nghị 14 ngày (tối đa 30 ngày). ADR-005 cập nhật sau đó đã chấp nhận 7 ngày và S3 WORM 90 ngày.
- Subscription filter đang là `filter_pattern = ""` để giữ cả audit và authenticator.
- Lambda `is_noise` hiện chỉ bỏ `/healthz`, `/livez`, và user `system:node:*`. Lease polling, EBS CSI controller 404 và một số internal periodic requests vẫn đi qua.
- S3 audit bucket đã có Object Lock COMPLIANCE 90 ngày, versioning, SSE-S3, public access block và lifecycle sang `GLACIER_IR` sau ngày 91, expire sau 365 ngày.
- `docs/audit/reports/cloudwatch-cost-optimization-report.md` mô tả một `filter_pattern` JSON lọc 80%, nhưng Terraform hiện tại đang dùng pattern rỗng và lọc trong Lambda. Báo cáo cũ cần được đánh dấu stale hoặc cập nhật sau khi có approval.

## 3. Đánh giá compliance

### ADR-005

ADR-005 yêu cầu giữ hai luồng cốt lõi: `audit` để truy vết Kubernetes API action và `authenticator` để map IAM -> Kubernetes identity. ADR đã chấp nhận tắt `api` để giảm verbose request/response, đồng thời không bật `controllerManager`/`scheduler` trong baseline. Vì vậy, tắt `audit` trong production sẽ là thay đổi ADR, không phải một tinh chỉnh cost thông thường.

### AUDIT-001 và Mandate #4

AUDIT-001 yêu cầu:

- bật control-plane logging;
- có hot query trên CloudWatch;
- stream sang lưu trữ dài hạn tamper-evident;
- forensic có thể dựng lại `ai - làm gì - khi nào`.

Mandate #4 yêu cầu log integrity và không để operator tự xóa vết. S3 WORM hiện tại đáp ứng phần archive, nhưng nếu lọc noise thì phải có allowlist, test regression và evidence cho thấy các hành vi nhạy cảm vẫn còn đủ.

### Deviation cần owner approve

| Hạng mục | AUDIT-001 gốc | ADR/Terraform hiện tại | Kết luận approve |
| -------- | ------------- | ---------------------- | ---------------- |
| Log types | Đề xuất bật 5 loại log | Bật `audit`, `authenticator`; tắt `api`, `controllerManager`, `scheduler` | Chấp nhận nếu CDO-07 xác nhận `audit` + `authenticator` đủ để forensic |
| CloudWatch retention | 14 ngày ưu tiên, tối đa 30 ngày | 7 ngày | Có thể giảm 1 ngày chỉ sau khi S3/Athena forensic pass |
| Long-term retention | Lưu 1 năm | Lifecycle expire 365 ngày, Object Lock COMPLIANCE 90 ngày | Cần CDO-07/CDO-08 chấp nhận WORM 90 ngày là compliance floor |
| Encryption | DoD cũ ghi CMK `tf4-cdo07-audit-cmk` | Terraform dùng SSE-S3 AES256 để tránh KMS API cost | Cần approve rõ nếu không bắt buộc CMK |
| Bucket name | AUDIT-001 ghi `tf4-cdo07-audit-log` | Terraform tạo `tf4-eks-audit-logs-${account_id}` | Cần evidence bucket thực tế khi nghiệm thu |

## 4. So sánh phương án

| Tiêu chí | PA1 - tách môi trường | PA2 - retention + noise filter | PA3 - Falco eBPF + OTel -> S3 |
| -------- | --------------------- | ------------------------------- | ------------------------------ |
| Giảm CloudWatch ingestion | Cao ở dev/staging; không giảm production nếu vẫn bật audit | **Không giảm** ingestion; chỉ giảm storage/Firehose/S3/Athena | Lý thuyết cao nhưng repo chưa có kênh thay thế EKS control-plane audit được AWS/CDO-07 xác nhận |
| Bao phủ forensic control plane | Prod đầy đủ; nonprod có chủ ý giảm audit | Prod đầy đủ nếu allowlist đúng | Falco không thay managed control-plane API audit/IAM authenticator |
| Compliance risk | Trung bình, cần phân loại môi trường và drill riêng | Thấp-trung bình nếu archive S3 và test đầy đủ | Cao nếu dùng độc lập; không nên dùng để thay ADR-005/AUDIT-001 |
| Độ phức tạp | Thấp | Thấp-trung bình | Cao, thêm DaemonSet/OTel/S3 pipeline và vận hành mới |
| Rủi ro tài nguyên | Thấp | Lambda nhỏ, có thể benchmark | Falco/OTel có overhead trên mỗi node; cần tránh tranh chấp tài nguyên |
| Khuyến nghị | **Nên làm** | **Nên làm ngay sau validation** | Chỉ xem xét như detection bổ sung, không thay audit |

### Đánh giá tải tài nguyên

Ở mức 124,878 events/giờ (~34.7 events/giây, 2.1 GB/giờ), nếu đưa raw event vào OTel/Falco:

- OTel Collector phải parse, batch, retry và export trung bình khoảng 35 event/s nhưng payload rất lớn (~16.8 KB/event theo mẫu đo). Burst/retry có thể làm tăng heap, queue và disk queue.
- Falco eBPF phân tích syscall trên mỗi worker, không phải pipeline lọc EKS audit. Overhead phụ thuộc rule và số process; cần canary trên một node, đặt CPU/memory limit và theo dõi drop/backpressure.
- Không được đưa raw 2.1 GB/giờ vào collector dùng chung với telemetry storefront nếu chưa có queue isolation, memory limiter, batch và alert cho exporter failure.
- PA2 xử lý ở Firehose Lambda sau khi CloudWatch đã nhận log; Lambda 256 MB/60 s hiện tại cần load test và theo dõi các metric `Throttles`, `Errors`, duration, Firehose delivery lag.

## 5. Implementation Plan

### Phase 0 - Freeze baseline và approval (P0)

1. CDO-04 xác nhận billing evidence: log group, UsageType, region, timeframe và đơn giá; tách MTD với run-rate.
2. CDO-07 lập forensic canary cases: `kubectl` delete/patch, RBAC change, secret read, `kubectl exec`, IAM authentication và một lease/health request.
3. CDO-08 review retention, Object Lock, IAM least privilege, rollback và incident impact.
4. Không thay đổi `cluster_enabled_log_types` production trước khi có approval bằng văn bản.

### Phase 1 - PA2 safe filter và retention

1. Viết unit test cho `is_noise` bằng audit fixtures. Noise chỉ được drop khi khớp cả verb/resource/username/requestURI/responseStatus đã được phân loại.
2. Thêm explicit patterns cho `/readyz`, `/healthz`, `/livez`, node heartbeat, lease polling và EBS CSI controller 404; ghi rõ những pattern không được drop.
3. Không drop bất kỳ event nào có `responseStatus.code` là `401`, `403`, hoặc `>=500`; không drop `secrets`, RBAC, `pods/exec`, create/update/patch/delete, IAM/user request, admission deny và escalation-related verb/resource.
4. Giữ nguyên `filter_pattern = ""` để authenticator không bị mất do khác schema. Lọc tại Lambda, sau CloudWatch ingestion.
5. Giảm retention CloudWatch từ 7 ngày xuống 1 ngày chỉ sau khi S3 có object mới trong 24 giờ, Object Lock/versioning/policy được verify, Athena query đọc được forensic canary, và Firehose/Lambda error rate cùng delivery lag bằng 0 trong cửa sổ quan sát.
6. Theo dõi 7 ngày: CloudWatch incoming bytes, Firehose processed/delivered bytes, Lambda errors/throttles, S3 object count/size, Athena queryability.

### Phase 2 - PA1 environment separation

1. Xác định cluster tags/account classification: dev, staging, prod/drill.
2. Dev/staging: `cluster_enabled_log_types = ["authenticator"]` nếu CDO-07 chấp nhận không forensic Kubernetes API đầy đủ ở các môi trường này.
3. Prod/drill: giữ `["audit", "authenticator"]`, không bật `api`.
4. Mọi thay đổi phải có Terraform plan, approval CDO-04 + CDO-07, rollback và evidence `aws eks describe-cluster`.
5. Tạo dashboard cost theo cluster/environment để đảm bảo cost saving đến từ giảm ingestion, không chỉ từ retention.

### Phase 3 - PA3 research gate, không phải implementation mặc định

Chỉ tiếp tục nếu AWS/EKS owner xác nhận có kênh audit control-plane thay thế và CDO-07 chấp nhận equivalence. Nếu thử nghiệm Falco:

- canary 1 node, rule allowlist chỉ bắt security-relevant syscall;
- OTel Collector riêng, queue/memory limiter, resource requests/limits, drop counter và S3 encryption/Object Lock;
- chaos test collector down, S3 deny, node pressure và retry storm;
- đối chiếu forensic cases với audit log gốc.

Nếu không đạt được equivalence, hủy PA3 và giữ Falco như detection bổ sung.

## 6. Cost Model và KPI

- Baseline ingestion: `$224.05` cho 448.1 GB MTD theo evidence; run-rate nếu 2.1 GB/giờ liên tục: khoảng `$756/tháng`.
- Authenticator: gần như không đáng kể so với audit.
- PA2 tiết kiệm chủ yếu storage và downstream processing; không ghi nhận saving ingestion trong business case.
- PA1 tiết kiệm ingestion của môi trường chỉ tắt `audit`; phải đo trước/sau bằng CloudWatch usage data.

Ước tính để so sánh (đơn giá trong evidence/pricing tham chiếu, chưa bao gồm free tier, tax, Firehose request, Lambda, S3 request và Athena; CDO-04 phải đối chiếu Cost Explorer theo region/account thực tế):

| Khoản | Cách tính | Ước tính |
| ----- | --------- | -------: |
| CloudWatch ingestion run-rate | 1,512 GB/tháng x $0.50 | ~$756/tháng |
| CloudWatch hot storage 7 ngày | 2.1 GB/giờ x 24 x 7 x $0.03/GB-tháng | ~$10.58/tháng |
| CloudWatch hot storage 1 ngày | 2.1 GB/giờ x 24 x 1 x $0.03/GB-tháng | ~$1.51/tháng |
| Storage saving 7 ngày -> 1 ngày | chênh lệch hai dòng trên | ~$9.07/tháng |

Bảng này cho thấy PA2 không thể giải quyết driver $224 MTD/$756 run-rate nếu audit vẫn được bật trong cùng môi trường. PA1 mới có khả năng giảm ingestion trực tiếp, còn PA2 chủ yếu giảm hot storage và chi phí downstream sau subscription.

KPI bắt buộc:

| KPI | Mục tiêu |
| --- | -------- |
| Forensic canary recall | 100% event nhạy cảm tìm thấy trong S3/Athena |
| Authenticator retention | 100% event cần thiết được giữ |
| False-drop rate | 0 cho RBAC, Secret, exec, create/update/delete, IAM identity |
| Firehose/Lambda processing failure | 0 trong cửa sổ acceptance |
| S3 Object Lock | COMPLIANCE 90 ngày, operator không delete được |
| Cost | Tách rõ ingestion saving (PA1) và storage/downstream saving (PA2) |
| Collector resource, nếu PA3 pilot | Không OOM, không tranh CPU với checkout/telemetry |

## 7. Rollback và incident controls

- PA2 filter: revert Lambda code/zip và Terraform plan; giữ raw subscription trong thời gian rollback.
- Retention: tăng lại 7 ngày nếu CloudWatch hot query cần thiết; không ảnh hưởng S3 WORM archive.
- PA1: bật lại `audit` cho cluster đã tắt qua Terraform; không xóa log group/archive.
- PA3 pilot: xóa DaemonSet/OTel route nếu node pressure, exporter backlog, missing forensic event hoặc S3 delivery failure.
- Mọi rollback phải có change ticket, actor identity, timestamp, Terraform plan/apply output và sau đó re-run forensic canary.

## 8. Approval Record

| Owner | Quyết định cần phê duyệt | Trạng thái |
| ----- | ------------------------ | ---------- |
| CDO-04 | Cost model, PA1/PA2 rollout, billing/KPI và budget guardrail | Pending |
| CDO-07 | ADR-005/AUDIT-001 compliance, noise allowlist, forensic evidence và acceptance | Pending |
| CDO-08 | Security, IAM, WORM, resource isolation, rollback và PA3 risk gate | Pending |

**Acceptance của Task 79:** tài liệu này là implementation plan để trình ba owner. Task chỉ được đóng sau khi có approval của CDO-04 (và review CDO-07/CDO-08), có evidence baseline, test filter, và rollout/rollback record.

## 9. References

- `docs/audit/adr/005-eks-control-plane-logging-enabled.md`
- `docs/audit/tickets/AUDIT-001-enable-eks-logs.md`
- `docs/requirements/mandates/MANDATE-04-auditability-tf4.md`
- `infra/terraform/eks.tf`
- `infra/terraform/eks-audit-firehose.tf`
- `infra/terraform/d18-storage-lifecycle.tf`
- AWS EKS docs: `https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html`
- AWS CloudWatch Logs subscription docs: `https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/SubscriptionFilters.html`
- AWS CloudWatch pricing: `https://aws.amazon.com/cloudwatch/pricing/`
