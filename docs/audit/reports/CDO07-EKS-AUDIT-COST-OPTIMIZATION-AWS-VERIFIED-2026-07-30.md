# CDO-07 — Báo cáo tối ưu chi phí EKS Audit Logs từ số liệu AWS thực tế

- **Ngày kiểm tra:** 2026-07-30
- **AWS account:** `511825856493`
- **Region:** `us-east-1`
- **Cluster:** `techx-tf4-cluster`
- **Log group:** `/aws/eks/techx-tf4-cluster/cluster`
- **Phạm vi:** điều tra read-only và đề xuất tối ưu; chưa thay đổi production
- **Owners:** CDO-04 (Cost/Performance), CDO-07 (Audit/Compliance), CDO-08 (Security/Reliability)

---

## 1. Kết luận điều hành

Chi phí CloudWatch Logs cao không phải do số lượng người dùng ứng dụng và cũng không thể xử lý hiệu quả bằng cách giảm retention hoặc lọc tại Lambda. Nguyên nhân chính là một vòng lặp reconcile bất thường giữa Argo CD và các Kyverno CustomResourceDefinition (CRD).

Trong mẫu 24 giờ được truy vấn trực tiếp từ CloudWatch Logs Insights:

- Tổng audit data được scan: **51.03 GB**.
- `argocd-application-controller` tạo **47.36 GB**, tương đương **92.8%** audit bytes.
- Argo CD liên tục `update` các Kyverno CRD, xấp xỉ **8,640 lần/ngày cho mỗi URI** — gần một lần mỗi 10 giây.
- Mỗi update CRD có kích thước từ khoảng **80 KB đến 485 KB**.
- Mỗi CRD thường nhận một cặp request: `?dryRun=All` và update thật.

Với run-rate 7 ngày gần nhất, CloudWatch nhận trung bình **48.73 GB/ngày**, tương đương khoảng **1,461.83 GB/tháng** và **$730.92/tháng** ở mức giả định `$0.50/GB`.

Nếu loại bỏ vòng lặp Argo CD–Kyverno, chi phí ingestion dự kiến giảm còn **$52.61–$146.18/tháng**, tương ứng tiết kiệm **$584.74–$678.30/tháng**. Pipeline `CloudWatch Logs → Subscription Filter → Firehose → S3 Object Lock → Athena` vẫn được giữ nguyên.

**Khuyến nghị:** không chuyển log group sang Infrequent Access (IA), không tắt EKS audit log và không coi Lambda filtering là giải pháp ingestion. Ưu tiên sửa cấu hình đồng bộ ứng dụng Kyverno của Argo CD bằng GitOps, triển khai canary và xác nhận mức giảm bằng `IncomingBytes`.

---

## 2. Hiện trạng được xác nhận trực tiếp trên AWS

### 2.1 EKS và CloudWatch Logs

| Hạng mục | Trạng thái thực tế |
|---|---|
| EKS cluster | `techx-tf4-cluster`, trạng thái `ACTIVE`, Kubernetes `1.34` |
| Control-plane log types | `audit`, `authenticator` đang bật |
| Log group class | `STANDARD` |
| CloudWatch retention | 7 ngày |
| Stored bytes tại thời điểm kiểm tra | 40,436,163,158 bytes, khoảng 40.44 GB decimal |
| KMS key riêng trên log group | Không cấu hình |
| Subscription Filter | `tf4-eks-audit-logs-subscription` |
| Filter pattern | Rỗng — chuyển toàn bộ audit và authenticator |
| Destination | `tf4-eks-audit-logs-firehose` |

### 2.2 Firehose và S3 WORM

| Hạng mục | Trạng thái thực tế |
|---|---|
| Firehose stream | `tf4-eks-audit-logs-firehose`, trạng thái `ACTIVE` |
| Processing | Lambda `tf4-firehose-cwl-processor:$LATEST` |
| Firehose buffering | 5 MB hoặc 60 giây |
| Lambda processor buffering | 1 MB hoặc 60 giây |
| S3 destination | `tf4-eks-audit-logs-511825856493` |
| Compression | `UNCOMPRESSED` |
| Firehose stream encryption | Disabled; S3 áp dụng SSE-S3 (`AES256`) |
| S3 Object Lock | Enabled, `COMPLIANCE`, 90 ngày |
| S3 versioning | Enabled |
| Lifecycle | Chuyển `GLACIER_IR` ngày 91; expire ngày 365 |
| S3 size ngày 2026-07-29 | Khoảng 77.42 GB |
| S3 object count ngày 2026-07-29 | 22,492 objects |

Pipeline đã đáp ứng mục tiêu lưu giữ bằng chứng WORM. Vì Subscription Filter là mắt xích bắt buộc, log group phải tiếp tục sử dụng class `STANDARD` trong kiến trúc hiện tại.

### 2.3 Health của pipeline

Metric Firehose `DeliveryToS3.Success` có giá trị trung bình `1.0` trong các ngày được kiểm tra. Tuy nhiên, error log có các sự kiện `Lambda.FunctionError` liên quan delivery stream version cũ. Stream hiện ở version 4, nhưng cần bổ sung alarm và xác nhận không còn lỗi mới trước khi thay đổi retention hoặc coi S3 là bản sao forensic duy nhất.

---

## 3. Baseline chi phí trước tối ưu

### 3.1 CloudWatch ingestion

CloudWatch metric `AWS/Logs:IncomingBytes` trong 7 ngày gần nhất:

```text
Tổng 7 ngày       = 341,094,773,115 bytes
Trung bình/ngày   = 48.7278 GB decimal
Run-rate 30 ngày  = 1,461.8347 GB
```

Ước tính ingestion:

```text
1,461.8347 GB × $0.50/GB = $730.92/tháng
```

Đây là run-rate kỹ thuật từ CloudWatch metrics, chưa phải hóa đơn đã đối soát. Role audit hiện không có `ce:GetCostAndUsage`, vì vậy Cost Explorer chưa thể được dùng để xác nhận discount, free tier, credit, tax hoặc blended allocation.

### 3.2 Event volume

Trong 23 ngày có dữ liệu của kỳ truy vấn 30 ngày:

| Chỉ tiêu | Giá trị |
|---|---:|
| Tổng incoming bytes | 518,209,987,264 bytes |
| Tổng incoming events | 44,358,810 events |
| Trung bình events/ngày có dữ liệu | 1,928,644 |
| Events trong mẫu 24 giờ mới nhất | 3,009,688 audit events |

Việc dùng run-rate 7 ngày thay cho trung bình toàn kỳ là cần thiết vì volume tăng mạnh từ khoảng 1–2.5 GB/ngày lên khoảng 47–51 GB/ngày trong giai đoạn gần nhất.

---

## 4. Root cause: Argo CD liên tục thay thế Kyverno CRD

### 4.1 Phân bổ audit bytes theo actor

CloudWatch Logs Insights query 24 giờ cho thấy:

| Actor | Events | Audit bytes | Tỷ lệ bytes |
|---|---:|---:|---:|
| `system:serviceaccount:argocd:argocd-application-controller` | 1,013,968 | 47,361,065,381 | **92.8%** |
| Tất cả actor còn lại | 1,995,720 | 3,673,664,881 | 7.2% |
| **Tổng** | **3,009,688** | **51,034,730,262** | **100%** |

Argo CD chỉ chiếm khoảng 33.7% số event nhưng chiếm 92.8% số byte vì request update CRD rất lớn.

### 4.2 Các request lớn nhất

| Resource | Loại request | Events/ngày | Kích thước trung bình |
|---|---|---:|---:|
| `mutatingpolicies.policies.kyverno.io` | update + dry-run | khoảng 17,289 | khoảng 485 KB |
| `imagevalidatingpolicies.policies.kyverno.io` | update + dry-run | khoảng 17,289 | khoảng 473 KB |
| `validatingpolicies.policies.kyverno.io` | update + dry-run | khoảng 17,284 | khoảng 361 KB |
| `namespacedmutatingpolicies.policies.kyverno.io` | update + dry-run | khoảng 17,287 | khoảng 325 KB |
| `namespacedimagevalidatingpolicies.policies.kyverno.io` | update + dry-run | khoảng 17,288 | khoảng 317 KB |
| `namespacedvalidatingpolicies.policies.kyverno.io` | update + dry-run | khoảng 17,283 | khoảng 242 KB |

Tần suất khoảng 8,640 request/ngày cho mỗi URI tương ứng một lần mỗi 10 giây. Đây là reconcile/sync loop, không phải lưu lượng hoạt động bình thường của người dùng.

### 4.3 Cấu hình GitOps liên quan

Ứng dụng Kyverno hiện có:

```yaml
syncPolicy:
  automated:
    prune: false
    selfHeal: true
  syncOptions:
    - CreateNamespace=true
    - ServerSideApply=true
    - Replace=true
```

Argo CD quy định `Replace=true` có ưu tiên cao hơn `ServerSideApply=true`. Vì vậy cấu hình hiện tại thực tế dùng `kubectl replace/create` thay vì server-side apply. Tùy chọn replace gửi toàn bộ resource trong request và có thể gây cập nhật lặp lại nếu CRD luôn bị đánh dấu OutOfSync do defaulted/generated fields hoặc field ownership.

Ứng dụng cũng chưa bật `ApplyOutOfSyncOnly=true`, nên một lần sync có thể apply lại mọi resource thay vì chỉ resource thực sự OutOfSync.

---

## 5. Ước tính chi phí trước và sau

### 5.1 Công thức

```text
Baseline monthly GB = 48.727824731 × 30
                    = 1,461.834742 GB

Baseline cost       = 1,461.834742 × $0.50
                    = $730.92/tháng
```

### 5.2 Ba kịch bản

| Kịch bản | Mức giảm ingestion | Volume sau tối ưu | Cost sau tối ưu | Tiết kiệm/tháng |
|---|---:|---:|---:|---:|
| Thận trọng | 80% | 292.37 GB/tháng | **$146.18** | **$584.74** |
| Kỳ vọng | 90% | 146.18 GB/tháng | **$73.09** | **$657.83** |
| Theo tỷ lệ actor đo được | 92.8% | 105.23 GB/tháng | **$52.61** | **$678.30** |

**Khoảng dự báo phù hợp để lập ngân sách:** CloudWatch ingestion còn **$53–$146/tháng**, tiết kiệm **$585–$678/tháng**.

Mức 92.8% không phải cam kết. Argo CD vẫn cần thực hiện legitimate reconciliation sau khi sửa cấu hình và tỷ lệ workload có thể thay đổi.

### 5.3 Downstream cost

Firehose hiện nhận khoảng 6.4–6.9 GB/ngày và S3 tăng khoảng 10 GB/ngày trong các điểm đo gần nhất. Khi loại bỏ vòng lặp CRD, Firehose processing, Lambda duration/invocations, S3 PUT/storage và Athena scanned bytes cũng sẽ giảm đáng kể.

Các khoản này chưa được cộng vào bảng tiết kiệm vì:

- Role hiện tại không có quyền Cost Explorer.
- Role không có `lambda:GetFunctionConfiguration`.
- Chưa có Athena workgroup usage cùng kỳ.
- S3 đang lưu `UNCOMPRESSED`, nên tỷ lệ bytes giữa CloudWatch, Firehose và S3 không hoàn toàn tuyến tính.

Sau khi ổn định ingestion, có thể đánh giá GZIP cho Firehose/S3 như tối ưu P2. Đây không phải đòn bẩy chính vì CloudWatch ingestion vẫn được tính trước Firehose.

---

## 6. Thay đổi được đề xuất

Thực hiện qua GitOps, không patch trực tiếp live Application:

```diff
 syncOptions:
   - CreateNamespace=true
   - ServerSideApply=true
-  - Replace=true
+  - ApplyOutOfSyncOnly=true
```

Mục tiêu của thay đổi:

1. Loại bỏ `Replace=true` để `ServerSideApply=true` thực sự có hiệu lực.
2. Chỉ đồng bộ resource được xác định OutOfSync.
3. Giữ `selfHeal=true`, `prune=false`, Kyverno admission enforcement và toàn bộ audit pipeline.

Nếu CRD vẫn OutOfSync sau khi bỏ `Replace=true`, không thêm ignore rule rộng cho toàn bộ CRD. Trước tiên phải lấy Argo CD diff và xác định chính xác field bị mutate/default. Chỉ thêm `ignoreDifferences` cho field được chứng minh là do Kubernetes/Kyverno sở hữu và phải dùng `RespectIgnoreDifferences=true` nếu cần áp dụng ignore rule trong sync.

### 6.1 Trade-off và biện pháp khắc phục

Thay đổi này không loại bỏ rủi ro; nó chuyển từ cơ chế replace toàn bộ resource sang cơ chế quản lý field có chọn lọc. Các trade-off phải được xử lý trong cùng change plan như sau:

| Trade-off | Tác động có thể xảy ra | Giải pháp khắc phục | Tín hiệu/điều kiện kiểm soát |
|---|---|---|---|
| Server-side apply phát hiện field ownership conflict | Argo CD sync thất bại; CRD giữ phiên bản cũ | Lấy live diff và `managedFields` trước rollout; xác định field manager đang sở hữu field; chuyển ownership có kiểm soát theo từng field/resource. Không bật force-conflicts toàn Application | Argo condition `ComparisonError`/`SyncError`; API response `409 Conflict`; sync operation failed |
| Bỏ `Replace=true` làm lộ vấn đề mà replace trước đây che giấu | Một số CRD không thể apply bằng SSA ngay lần đầu | Canary một Application/CRD, giữ manifest rollback; nếu cần migration, thực hiện một lần trong change window rồi quay lại SSA | Kyverno Application phải `Synced` và `Healthy`; CRD Established condition phải `True` |
| `ApplyOutOfSyncOnly=true` không apply lại resource đang được Argo coi là Synced | Một resource có drift không được sửa nếu diff customization vô tình che field đó | Giữ `selfHeal=true`; không thêm ignore rule rộng; review toàn bộ `ignoreDifferences`; chạy periodic audit so sánh Git/rendered manifest với live state | Drift test có chủ đích phải làm Application chuyển `OutOfSync` và được self-heal |
| CRD vẫn luôn OutOfSync do defaulted/generated fields | Reconcile loop và chi phí không giảm dù đã bỏ Replace | Lấy diff chính xác; ignore duy nhất JSON pointer/JQ field do API server hoặc Kyverno sinh; thêm `RespectIgnoreDifferences=true` chỉ sau review ownership | Sau 30–60 phút, CRD update frequency phải giảm ít nhất 80%; nếu không đạt thì dừng rollout và điều tra diff |
| SSA làm thay đổi `managedFields` và có thể tăng object metadata | etcd/object metadata tăng nhẹ; diff khó đọc hơn | Theo dõi kích thước CRD và số lượng manager; loại bỏ manager cũ bằng quy trình migration được kiểm thử, không chỉnh `managedFields` thủ công | Không có tăng trưởng liên tục của CRD object size hoặc số field manager |
| Selective sync giảm số lần apply toàn bộ chart | Một thay đổi phụ thuộc thứ tự có thể không được re-apply nếu resource đó vẫn Synced | Giữ sync waves và health checks; khi nâng version Kyverno, chạy full manual sync trong maintenance window thay vì dựa hoàn toàn vào selective sync | Upgrade test phải xác nhận CRD trước controller và admission webhook healthy |
| Thay đổi CRD trong lúc Kyverno đang phục vụ admission | Webhook/policy có thể gián đoạn hoặc reject workload nếu CRD/controller không tương thích | Không restart admission controller cùng change; kiểm tra webhook endpoints, PDB và hai replicas; thực hiện synthetic allowed/denied admission tests trước và sau | Webhook endpoints đủ replicas; không tăng admission timeout/5xx; test allow/deny đều đúng |
| Mức tiết kiệm 92.8% không đạt do actor hoặc workload thay đổi | Budget sau tối ưu cao hơn dự báo | Dùng SLO chi phí theo metric thay vì cam kết một con số: P0 ≥80% giảm `IncomingBytes`; P1 ≥90%. Đo 1 giờ, 24 giờ và 7 ngày | Nếu giảm dưới 80%, không đóng task; chạy lại top actor/top URI và mở remediation tiếp theo |
| Rollback khôi phục `Replace=true` | Khôi phục availability/sync nhưng đồng thời khôi phục reconcile loop và cost cao | Chỉ dùng rollback như biện pháp phục hồi tạm thời; gắn thời hạn, alert cost và incident owner; tiếp tục root-cause analysis thay vì coi rollback là trạng thái cuối | `IncomingBytes` có thể trở lại khoảng 2 GB/giờ; phải có ticket follow-up và owner |

### 6.2 Guardrails bắt buộc

1. **Không dùng `Force=true` hoặc force-conflicts ở cấp Application.** Hai tùy chọn này có thể giành ownership hoặc recreate resource ngoài phạm vi cần thiết.
2. **Không ignore toàn bộ `/spec`, `/metadata` hoặc toàn bộ CRD.** Điều đó làm Argo CD mất khả năng phát hiện thay đổi schema và security policy.
3. **Không thay đổi đồng thời audit pipeline.** EKS log types, log class, retention, Subscription Filter, Firehose và Object Lock phải giữ nguyên trong change window để cô lập nguyên nhân.
4. **Không gộp với nâng version Kyverno.** Sửa sync behavior trước; upgrade chart là change riêng sau khi baseline ổn định.
5. **Giữ đường break-glass có kiểm soát.** Rollback commit phải được chuẩn bị trước, nhưng chỉ thực hiện khi tiêu chí health/security thất bại.

### 6.3 Kiểm thử bù cho từng trade-off

| Nhóm kiểm thử | Cách thực hiện | Kết quả bắt buộc |
|---|---|---|
| SSA dry-run | Render chart version hiện tại và chạy server-side dry-run trên các Kyverno CRD | Không có field conflict hoặc validation error chưa được xử lý |
| Drift/self-heal | Thay đổi một field test an toàn do Git sở hữu trong phạm vi canary | Argo phát hiện `OutOfSync` và tự khôi phục field |
| Generated field | Quan sát field do API server/Kyverno mutate sau sync | Chỉ field đã chứng minh ownership mới được đưa vào ignore rule |
| Admission allow | Apply một workload đáp ứng policy | Request được chấp nhận |
| Admission deny | Apply một workload vi phạm policy đã chọn | Request bị từ chối với policy mong đợi |
| Pipeline audit | Query CloudWatch, S3 và Athena cho các request test | Vẫn dựng lại được actor, verb, resource, response và timeline |
| Cost regression | So sánh `IncomingBytes` trước/sau ở cửa sổ 60 phút và 24 giờ | Giảm tối thiểu 80%; không có actor mới thay thế cost driver cũ |

---

## 7. Kế hoạch rollout, nghiệm thu và rollback

### 7.1 Pre-change

- Xác nhận Firehose không còn `Lambda.FunctionError` mới trong ít nhất 60 phút.
- Lưu baseline `IncomingBytes`, `IncomingLogEvents`, top actor và top requestURI của 60 phút trước thay đổi.
- Lấy live Argo CD diff của Application `kyverno` sau khi bổ sung Kubernetes RBAC đọc Application.
- Xác nhận Kyverno admission controller đang healthy và admission policies vẫn enforce.

### 7.2 Rollout

1. Merge thay đổi GitOps cho Application `kyverno`.
2. Quan sát một chu kỳ sync hoàn chỉnh.
3. Không thay đổi EKS log types, CloudWatch retention, subscription filter hoặc Firehose trong cùng change window.
4. Theo dõi trong 60 phút đầu, sau đó 24 giờ.

### 7.3 Tiêu chí đạt

| Metric/kiểm tra | Baseline | Điều kiện đạt |
|---|---:|---:|
| CloudWatch `IncomingBytes` | khoảng 2.03 GB/giờ | Giảm ít nhất 80% sau thời gian ổn định |
| Argo CRD update frequency | khoảng 1 lần/10 giây/URI | Không còn update lặp liên tục |
| Argo Application health | Chưa đọc được do RBAC | `Healthy` |
| Argo sync status | Chưa đọc được do RBAC | `Synced` |
| Kyverno admission | Đang vận hành | Không tăng deny/error ngoài dự kiến |
| Firehose delivery | `DeliveryToS3.Success = 1.0` | Duy trì và không có lỗi mới |
| S3 Object Lock | COMPLIANCE 90 ngày | Không thay đổi |

### 7.4 Rollback

Rollback Git commit để khôi phục `Replace=true` nếu:

- Argo CD không thể sync Kyverno;
- CRD ownership conflict làm sync thất bại;
- Kyverno webhook/admission bị gián đoạn;
- policy enforcement không còn đúng;
- có tác động production ngoài phạm vi dự kiến.

Rollback chỉ khôi phục cơ chế đồng bộ Argo CD. Không tắt audit log và không thay đổi S3 Object Lock.

---

## 8. Các phương án không được chọn

### 8.1 Chuyển CloudWatch Logs sang IA

Không khả thi trong kiến trúc hiện tại. CloudWatch Logs Infrequent Access không hỗ trợ Subscription Filters. Chuyển log group sang IA sẽ làm mất đường realtime tới Firehose và S3 WORM. Ngoài ra, log class không thể đổi sau khi log group được tạo; việc chuyển class đòi hỏi log group mới và thay đổi pipeline.

### 8.2 Giảm retention từ 7 ngày xuống 1 ngày

Chỉ giảm hot storage, không giảm ingestion. Chỉ cân nhắc sau khi chứng minh S3 delivery/restore SLO và không còn lỗi Lambda/Firehose.

### 8.3 Lọc noise trong Lambda

Lambda chạy sau CloudWatch ingestion nên không giảm khoản `$730.92/tháng` đang là cost driver. Nó chỉ giảm downstream storage/query cost và có nguy cơ loại bỏ forensic evidence nếu filter sai.

### 8.4 Tắt EKS audit log

Có thể giảm ingestion nhưng làm mất bằng chứng Kubernetes API quan trọng. Không cần chấp nhận rủi ro compliance này vì root cause có thể xử lý tại Argo CD mà vẫn giữ audit đầy đủ.

---

## 9. Permission gaps

Role `TF4-AuditReadOnlyAndAnalyze` thiếu các quyền sau:

| Quyền | Ảnh hưởng |
|---|---|
| `ce:GetCostAndUsage` | Không đối chiếu được run-rate với hóa đơn Cost Explorer |
| `lambda:GetFunctionConfiguration` | Không kiểm tra được runtime/memory/timeout/config processor trực tiếp |
| Kubernetes RBAC `get` cho `applications.argoproj.io` trong `argocd` | Không lấy được live sync status, health và diff của Application `kyverno` |

Nên cấp read-only tối thiểu cho các thao tác trên trước change window; không cần cấp quyền mutate production cho giai đoạn xác minh.

---

## 10. Approval matrix

| Owner | Quyết định | Trạng thái |
|---|---|---|
| CDO-04 | Chấp nhận baseline, đơn giá và khoảng tiết kiệm | Pending |
| CDO-07 | Xác nhận giữ nguyên audit evidence và WORM pipeline | Pending |
| CDO-08 | Review rủi ro Kyverno/Argo CD và rollback | Pending |
| GitOps owner | Merge và giám sát thay đổi sync options | Pending |
| Tech Lead | Phê duyệt change window | Pending |

---

## 11. Nguồn và bằng chứng

### AWS runtime evidence

- `aws eks describe-cluster`
- `aws logs describe-log-groups`
- `aws logs describe-subscription-filters`
- `aws cloudwatch get-metric-statistics` cho `AWS/Logs:IncomingBytes` và `IncomingLogEvents`
- CloudWatch Logs Insights query theo `user.username`, `verb`, `requestURI` và `strlen(@message)`
- `aws firehose describe-delivery-stream`
- `aws s3api get-object-lock-configuration`
- `aws s3api get-bucket-versioning`
- `aws s3api get-bucket-encryption`
- `aws s3api get-bucket-lifecycle-configuration`

### Repository evidence

- `tf4-phase3-gitops-manifests/argocd/root-resources/applications.yaml`
- `tf4-phase3-repo/infra/terraform/eks.tf`
- `tf4-phase3-repo/infra/terraform/eks-audit-firehose.tf`

### Vendor documentation

- AWS CloudWatch Logs log classes: <https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CloudWatch_Logs_Log_Classes.html>
- AWS CloudWatch Logs subscriptions: <https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Subscriptions.html>
- AWS CloudWatch pricing: <https://aws.amazon.com/cloudwatch/pricing/>
- Argo CD sync options: <https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/>
