# CDO-07 - Hồ sơ điều tra chi phí EKS CloudWatch Logs và đánh giá các phương án

- **Trạng thái:** Investigation / Cost Review - Chưa phê duyệt thay đổi production
- **Ngày cập nhật:** 2026-07-29
- **Phạm vi:** EKS `techx-tf4-cluster`, Log Group `/aws/eks/techx-tf4-cluster/cluster`
- **Người lập :** Hoàng Kim Hùng, Bùi Thành Nghĩa
- **Owners:** CDO-04 (Cost/Performance), CDO-07 (Audit/Compliance), CDO-08 (Security/Reliability)
- **Bối cảnh:** Cụm hiện tại đang được xem là production/prod-like; không được giả định đây là môi trường Dev hoặc Staging.

---

## 0. Kết luận điều hành

Tech Lead yêu cầu ưu tiên **điều tra và định lượng chi phí**, sau đó mới chọn phương án. Vì vậy tài liệu này chưa đề nghị áp dụng ngay `cluster_enabled_log_types = ["authenticator"]`, chưa tắt EKS `audit` và chưa triển khai Falco.

Số liệu hiện có chỉ ra `audit` là cost driver, nhưng chưa đủ để kết luận rằng có thể bỏ audit khỏi Control Plane mà vẫn đáp ứng ADR-005, AUDIT-001 và MANDATE-04. Các phương án có thể giảm chi phí đều có giới hạn hoặc blocker trong trạng thái hiện tại:

1. **PA1 - Phân tách môi trường:** không giải quyết được chi phí của cụm prod-like hiện tại nếu chưa có cluster Dev/Staging độc lập.
2. **PA2 - Retention 1 ngày và lọc `is_noise`:** giảm chi phí lưu trữ và dữ liệu downstream, nhưng **không giảm CloudWatch Ingestion** vì log đã bị tính phí trước khi đi qua Subscription Filter/Lambda.
3. **PA3 - Falco eBPF + OTel -> S3:** là hướng dài hạn có tiềm năng giảm phần lớn ingestion, nhưng hiện chưa khả thi để rollout production do thiếu đường chứng minh tương đương EKS API audit, xung đột Admission Policy, rủi ro capacity, IAM/schema/GitOps chưa hoàn thiện và thời gian triển khai không đủ.
4. **PA4 - Tắt `audit`, giữ `authenticator`:** thao tác rẻ và đơn giản nhất nhưng hiện là **thay đổi compliance chưa được phê duyệt**, không phải một tối ưu hạ tầng đơn thuần.
5. **K8s Audit Webhook/direct-to-S3:** không khả thi trên EKS Managed Control Plane vì không được cấu hình API Server flag/webhook ở master node.

**Quyết định tạm thời:** giữ cấu hình hiện tại `audit + authenticator`; chỉ thực hiện các bước điều tra read-only và lập cost baseline. Chỉ chuyển sang design/PoC sau khi CDO-04, CDO-07, CDO-08 và Tech Lead xác nhận các cổng quyết định bên dưới.

---

## 1. Hiện trạng kỹ thuật và bằng chứng chi phí

### 1.1 Cấu hình đang chạy trong repo

| Thành phần             | Bằng chứng trong repo                             | Nhận xét                                                                                |
| ---------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------- |
| EKS Control Plane Logs | `infra/terraform/eks.tf`                          | `cluster_enabled_log_types = ["audit", "authenticator"]`                                |
| CloudWatch retention   | `infra/terraform/eks.tf`                          | 7 ngày                                                                                  |
| Downstream archive     | `infra/terraform/eks-audit-firehose.tf`           | CloudWatch Subscription Filter -> Firehose -> S3 Object Lock COMPLIANCE 90 ngày         |
| Lọc noise              | Lambda `is_noise()` trong `eks-audit-firehose.tf` | Chạy sau CloudWatch ingestion; hiện chỉ nhận diện `/healthz`, `/livez`, `system:node:*` |
| Forensic query         | `infra/terraform/athena-forensics.tf`             | Glue/Athena schema hiện khớp output Lambda EKS audit hiện tại                           |
| OTel AI audit          | `infra/terraform/ai-audit-logs.tf`                | Role hiện chỉ có quyền ghi CloudWatch; không phải đường direct-to-S3 cho Falco          |

### 1.2 Số liệu thực tế được cung cấp

| Nguồn               |         Dung lượng | Events/giờ |           Chi phí ingestion quy đổi |
| ------------------- | -----------------: | ---------: | ----------------------------------: |
| EKS `audit`         | khoảng 2.10 GB/giờ |    124,878 | khoảng **$756/tháng** nếu chạy 24x7 |
| EKS `authenticator` | khoảng 0.19 MB/giờ |        539 |              khoảng **$0.07/tháng** |
| Log Group EKS, MTD  |           448.1 GB |          - |              khoảng **$224.05 MTD** |

Hai con số trên phải được tách rõ: `$224.05` là **Month-to-Date actual**, còn `$756/tháng` là **monthly run-rate** suy ra từ một giờ đo được. Run-rate không được dùng làm hóa đơn xác nhận hoặc cam kết ngân sách trước khi đối chiếu Cost Explorer.

### 1.3 Phần chi phí còn thiếu dữ liệu

Chưa được phép điền các con số cố định cho CloudWatch storage, Logs Insights, Firehose, Lambda, S3, Athena, KMS, NAT/data transfer hoặc chi phí node phát sinh. Cần lấy actual usage trong cùng kỳ 30 ngày và tách theo service, account, region, usage type, tag/cost allocation.

---

## 2. Phạm vi điều tra chi phí bắt buộc

CDO-04/Tech Lead cần nhận một baseline có thể tái lập, gồm:

1. **CloudWatch Logs:** `IncomingBytes`, `IncomingLogEvents`, stored bytes, retention, Logs Insights scanned bytes; đối chiếu với Cost Explorer theo `AmazonCloudWatch`, `us-east-1` và usage type thực tế.
2. **Downstream hiện tại:** Firehose delivery bytes/records, Lambda invocations/duration/errors, S3 Standard storage/requests, Athena bytes scanned và chi phí query.
3. **Nguồn log:** phân bổ `audit` theo `requestURI`, `verb`, `user.username`, `objectRef.resource`, response code; xác nhận tỷ lệ `/readyz`, `/healthz`, leases, EBS-CSI polling 404 và các mẫu noise khác trước khi loại bỏ.
4. **Đường lưu giữ:** retention nóng 7 ngày, S3 Object Lock 90 ngày, lifecycle và chi phí lưu trữ dài hạn.
5. **Capacity:** CPU/memory request/usage theo node, Karpenter NodePool limit (`cpu = "8"`), queue/backlog và headroom trước khi thử Falco/OTel.

### 2.1 Công thức tính thống nhất

```text
CloudWatch ingestion = GB thực nhận x đơn giá CloudWatch Logs Ingestion
CloudWatch storage   = GB-month lưu nóng x đơn giá storage theo region
S3 total             = storage + PUT/request + lifecycle/transition + data transfer
Athena total         = bytes scanned x đơn giá query
Node impact          = tài nguyên request/usage tăng thêm + node-hours nếu phải scale
Net saving           = chi phí baseline - (chi phí còn lại + chi phí phương án)
```

Kết quả phải ghi cả `actual`, `run-rate`, giả định, khoảng sai số và nguồn truy vấn; không dùng bảng ước tính cũ trong ADR-005 (2-5 GB/tháng) làm baseline mới.

### 2.2 Cách thu thập evidence (read-only)

Các lệnh dưới đây chỉ đọc số liệu. Thay `START_DATE`, `END_DATE` và `REGION` bằng cùng một kỳ đo; không chạy `update-cluster-config` trong giai đoạn điều tra.

```bash
# CloudWatch volume theo ngày của Log Group
aws cloudwatch get-metric-data \
  --region REGION \
  --metric-data-queries '[{"Id":"incomingbytes","MetricStat":{"Metric":{"Namespace":"AWS/Logs","MetricName":"IncomingBytes","Dimensions":[{"Name":"LogGroupName","Value":"/aws/eks/techx-tf4-cluster/cluster"}]},"Period":86400,"Stat":"Sum"},"ReturnData":true}]' \
  --start-time START_DATE --end-time END_DATE

# Cost Explorer: trước tiên group theo USAGE_TYPE để thấy mã usage thực tế
aws ce get-cost-and-usage \
  --time-period Start=START_DATE,End=END_DATE \
  --granularity DAILY --metrics UnblendedCost UsageQuantity \
  --group-by Type=DIMENSION,Key=USAGE_TYPE
```

Khi đã xác định đúng `USAGE_TYPE`, truy vấn lại theo service `AmazonCloudWatch` và region; lưu JSON gốc, thời gian truy vấn và account vào thư mục evidence của task. Các chi phí S3/Firehose/Athena/Lambda phải được truy vấn riêng, không gộp vào `$0.50/GB` của CloudWatch ingestion.

---

## 3. Danh sách phương án và đánh giá khả thi

### PA1 - Phân tách môi trường

**Mô hình:** Dev/Staging chỉ bật `authenticator`; Prod/Diễn tập bật `audit`.

**Lợi ích:** phù hợp nếu thực sự có nhiều cluster và workload không production được loại khỏi audit nặng.

**Vì sao chưa khả thi hiện tại:**

- Cụm trong phạm vi task đang vận hành theo mô hình prod-like; repo không cung cấp bằng chứng về một cluster Dev/Staging độc lập để chuyển workload.
- Không làm giảm ingestion của chính cluster production hiện tại.
- Nếu tắt audit ở một môi trường đang chứa dữ liệu production, phải mở lại đánh giá ADR-005/AUDIT-001 và chứng minh phạm vi audit được phân tách.

**Điều kiện để xem xét lại:** inventory cluster và workload, mapping dữ liệu không chứa production, cost baseline riêng từng cluster, cùng CDO-07 approval.

### PA2 - Retention 1 ngày và cập nhật `is_noise`

**Mô hình:** giảm retention CloudWatch còn 1 ngày và lọc các request noise trong Lambda Processor.

**Lợi ích:** giảm CloudWatch hot storage, Firehose/Lambda/S3 downstream volume và Athena scanned bytes nếu bộ lọc đúng.

**Vì sao chưa đủ/ chưa khả thi như giải pháp cost chính:**

- CloudWatch tính ingestion khi event vào Log Group; Subscription Filter và Lambda chạy sau đó. PA2 **không giảm** khoản `$0.50/GB` đang tạo ra cost driver.
- `filter_pattern = ""` hiện chuyển toàn bộ log sang Firehose; chỉnh `is_noise` có nguy cơ loại nhầm evidence và cần test forensic trước khi thay đổi.
- Retention 1 ngày có thể không đáp ứng nhu cầu điều tra nóng của AUDIT-001 nếu S3 delivery bị trễ hoặc Athena/S3 chưa được xác nhận khôi phục.

**Điều kiện để dùng như guardrail tạm thời:** xác nhận S3 WORM delivery liên tục, kiểm thử query/restore, danh sách noise được CDO-07 ký, và đo riêng storage/downstream saving. Không gọi PA2 là giải pháp giảm ingestion.

### PA3 - Falco eBPF DaemonSet + dedicated OTel Collector -> S3

**Mô hình mục tiêu:** Falco chỉ phát hiện sự kiện runtime security cần thiết -> dedicated OTel Collector -> S3 prefix `falco-audit/` trong bucket `tf4-eks-audit-logs-${account_id}` hiện có -> Glue/Athena schema riêng.

**Lợi ích tiềm năng:** không đưa raw EKS audit 2.1 GB/giờ qua CloudWatch; chi phí còn lại phụ thuộc event Falco thực tế và S3/Athena, không thể mặc định là `$0`.

**Vì sao chưa khả thi để triển khai ngay:**

1. **Không tương đương EKS audit:** Falco quan sát syscall/runtime trên worker, không ghi mọi request tới Kubernetes API Server. Không thể tự chứng minh các case `get/list/watch Secret`, RBAC hoặc request bị từ chối nếu không có nguồn bổ sung.
2. **EKS Managed Control Plane:** Audit Webhook/direct-to-S3 ở API Server không phải đường thay thế khả dụng vì không chỉnh được `--audit-webhook-config-file` trên master node.
3. **Admission blocker:** các policy `require-run-as-nonroot`, `require-drop-all-capabilities`, `disallow-privileged-and-host-access`, `disallow-hostpath-volumes` đang áp dụng với `Deny`; Falco có thể cần root/capability/host access. Exception namespace phải được CDO-08 phê duyệt và kiểm thử.
4. **Capacity risk:** DaemonSet thêm pod trên worker; NodePool `techx-general` giới hạn `cpu = "8"` và cần đo headroom thực tế. Nếu OTel xử lý raw 124,878 events/giờ sẽ có nguy cơ queue tăng, CPU/RAM pressure hoặc OOM; PA3 chỉ hợp lý khi lọc tại nguồn.
5. **IAM và pipeline chưa sẵn sàng:** OTel role trong `ai-audit-logs.tf` chỉ có `logs:PutLogEvents`, chưa có `s3:PutObject`. Không được dùng chung collector observability hiện tại nếu chưa tách resource/queue/retry.
6. **Data model/GitOps chưa sẵn sàng:** Glue table `eks_audit_events` đang khớp output Lambda hiện tại, không khớp Falco fields (`time`, `priority`, `rule`, `output_fields`); repo hiện chưa có Falco Application/values trong GitOps.
7. **Compliance và thời gian:** cần canary, load test, chaos/failure test, forensic equivalence review và cập nhật ADR/DoD. Tech Lead xác nhận không phù hợp để hoàn thành trong thời gian hiện tại.

**Kết luận PA3:** giữ là **ứng viên dài hạn / PoC sau**, không đánh dấu `Approved` hoặc `Ready for Production`.

### PA4 - Tắt `audit`, chỉ giữ `authenticator`

**Mô hình:** đổi `infra/terraform/eks.tf` thành `cluster_enabled_log_types = ["authenticator"]`.

**Chi phí lý thuyết:** có thể giảm phần ingestion audit từ run-rate khoảng `$756/tháng` xuống mức authenticator khoảng `$0.07/tháng`.

**Vì sao chưa khả thi hiện tại:**

- Đây là thay đổi làm mất bản ghi Kubernetes API request, trong khi ADR-005 hiện coi `audit + authenticator` là hai log cốt lõi; AUDIT-001 và MANDATE-04 yêu cầu dựng lại hành động ở tầng cluster.
- CloudTrail, Git/ArgoCD và authenticator không tự động thay thế đầy đủ raw API audit; đặc biệt các thao tác đọc Secret, `exec`, RBAC và request bị từ chối cần được chứng minh bằng test case.
- Chưa có biên bản CDO-07/08 chấp nhận khoảng trống bằng chứng và chưa có rollback window/runbook.

**Kết luận PA4:** chỉ là phương án sau khi có compliance waiver và evidence matrix được ký; tuyệt đối không apply chỉ vì “sửa một dòng Terraform”.

### PA5 - Lọc ở Control Plane / Audit Webhook để bỏ CloudWatch

**Mô hình:** yêu cầu EKS gửi audit trực tiếp tới webhook/S3 hoặc lọc trước khi CloudWatch nhận.

**Kết luận:** không khả thi với EKS Managed Control Plane trong kiến trúc hiện tại; AWS không cho quản trị master/API Server flags. Không đưa vào PoC triển khai.

---

## 4. Ma trận quyết định sơ bộ

| Phương án                   |                   Giảm ingestion? |        Giữ đủ K8s API audit? | Blocker hiện tại                                     | Trạng thái             |
| --------------------------- | --------------------------------: | ---------------------------: | ---------------------------------------------------- | ---------------------- |
| Giữ `audit + authenticator` |                             Không |                           Có | Cost cao                                             | Baseline/rollback      |
| PA1 phân tách môi trường    | Có, nhưng chỉ ở cluster được tách |  Có ở prod nếu vẫn bật audit | Chưa có cluster mapping                              | Chưa khả thi           |
| PA2 retention + `is_noise`  |                             Không | Có thể mất event nếu lọc sai | Lọc sau ingestion, risk evidence                     | Guardrail có điều kiện |
| PA3 Falco + OTel -> S3      |                      Có tiềm năng |  Chưa chứng minh tương đương | Admission, capacity, IAM, schema, GitOps, compliance | PoC dài hạn            |
| PA4 chỉ `authenticator`     |                                Có | Không đủ bằng chứng hiện tại | ADR/AUDIT waiver và forensic gap                     | Chưa được phép apply   |
| PA5 webhook/direct-to-S3    |                                Có |     Có nếu API Server hỗ trợ | EKS Managed Control Plane                            | Loại bỏ                |

---

## 5. Kế hoạch điều tra và cổng phê duyệt

### Giai đoạn 0 - Cost baseline (read-only)

- Trích xuất 30 ngày Cost Explorer theo service/region/usage type cho CloudWatch Logs, Firehose, Lambda, S3, Athena và network.
- Lấy CloudWatch `IncomingBytes`, `IncomingLogEvents`, stored bytes và Insights scanned bytes theo ngày; lưu query/output làm evidence.
- Đối chiếu 1 giờ đo mẫu với ít nhất 7 ngày và phân tách audit/authenticator.
- Lập danh sách top request noise và top request có giá trị forensic; chưa đổi filter.

### Giai đoạn 1 - Feasibility review

- CDO-04 xác nhận baseline, run-rate, khoảng sai số và budget ceiling.
- CDO-07 lập evidence matrix cho các case bắt buộc: `get Secret`, RBAC change, `exec`, deployment change, denied request, IAM identity và timeline.
- CDO-08 review exception cho Falco, node headroom, network, IAM least privilege và rollback.
- Tech Lead xác nhận thời gian, owner và khả năng triển khai trong release window.

### Giai đoạn 2 - PoC có kiểm soát (chỉ khi được duyệt)

- Falco canary trên phạm vi hẹp; dedicated OTel Collector có queue/backpressure và S3 prefix riêng.
- Không đưa raw 2.1 GB/giờ vào OTel. Đo event rate sau filtering, CPU/memory p95, dropped events, queue depth và S3 delivery latency.
- Kiểm thử restart, S3 AccessDenied, network loss, node pressure và duplicate/retry.
- Chỉ xem PA3 đạt nếu mọi case trong evidence matrix truy vấn được và CDO-07 ký chấp nhận khoảng trống còn lại.

### Giai đoạn 3 - Quyết định và triển khai

- Nếu PA3 không chứng minh tương đương: giữ `audit + authenticator`; xem PA2 như guardrail storage/downstream có điều kiện.
- Nếu PA3 được phê duyệt: cập nhật ADR mới, DoD của AUDIT-001, IAM, Falco/OTel GitOps manifests, Glue/Athena schema và rollback plan trước khi tắt audit.
- PA4 chỉ được apply sau compliance waiver bằng văn bản; thời điểm apply phải có canary, monitoring `IncomingBytes` và rollback window.

---

## 6. Tiêu chí nghiệm thu của hồ sơ điều tra

- Có bảng actual cost 30 ngày và run-rate được ghi rõ nguồn, kỳ đo và giả định.
- Có cost model riêng cho CloudWatch, Firehose/Lambda, S3, Athena, network và worker capacity.
- Có danh sách option, lợi ích, chi phí, rủi ro, blocker và điều kiện mở khóa; không gắn `Approved` khi chưa có chữ ký.
- Có evidence matrix chứng minh phần audit nào được giữ, phần nào mất hoặc được thay thế.
- Có biên bản quyết định của CDO-04 (cost), CDO-07 (audit), CDO-08 (security) và Tech Lead (feasibility).
- Không có thay đổi production trong task điều tra này; mọi Terraform/Helm change là task triển khai riêng sau approval.

---

## 7. Approval matrix

| Owner     | Quyết định cần xác nhận                                      | Trạng thái |
| --------- | ------------------------------------------------------------ | ---------- |
| CDO-04    | Cost baseline, run-rate, budget ceiling và phương án chi phí | Pending    |
| CDO-07    | Mức độ audit bắt buộc, evidence matrix và compliance gap     | Pending    |
| CDO-08    | Admission exception, capacity, IAM, reliability và rollback  | Pending    |
| Tech Lead | Tính khả thi, thời gian và thứ tự triển khai                 | Pending    |

---

## 8. Tài liệu tham chiếu

- `infra/terraform/eks.tf`
- `infra/terraform/eks-audit-firehose.tf`
- `infra/terraform/ai-audit-logs.tf`
- `infra/terraform/athena-forensics.tf`
- `techx-corp-chart/templates/admission-hardening.yaml`
- `techx-corp-chart/templates/admission-hardening-bindings.yaml`
- `docs/audit/adr/005-eks-control-plane-logging-enabled.md`
- `docs/audit/tickets/AUDIT-001-enable-eks-logs.md`
- `docs/requirements/mandates/MANDATE-04-auditability-tf4.md`
- AWS EKS Control Plane Logs: <https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html>
- AWS EKS Auditing and Logging Best Practices: <https://docs.aws.amazon.com/eks/latest/best-practices/auditing-and-logging.html>
