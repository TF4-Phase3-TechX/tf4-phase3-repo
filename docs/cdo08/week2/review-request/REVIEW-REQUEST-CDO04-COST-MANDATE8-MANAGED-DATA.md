# Review request — CDO04 duyệt chi phí managed data services cho Mandate 8

| Thuộc tính | Giá trị |
|---|---|
| Requester | Phương / CDO08-REL-13 |
| Reviewer | CDO04 |
| Trạng thái | Pending CDO04 approval |
| Thời điểm cần quyết định | Trước khi REL-14 provision bất kỳ managed resource nào |
| Budget constraint | Khoảng $300/tuần cho toàn bộ AWS infrastructure của TF |

## 1. CDO04 cần quyết định gì?

CDO04 vui lòng xác nhận năm quyết định chính:

1. Có approve Amazon RDS for PostgreSQL không? Nếu có, dùng Multi-AZ hay Single-AZ?
2. Có approve Amazon ElastiCache for Valkey không? Nếu có, dùng một primary + một replica hay chỉ một node?
3. Có approve Amazon MSK không? Nếu có, chọn Serverless hay Provisioned?
4. Nếu MSK làm tổng chi phí vượt budget, team phải tuning, xin budget exception, defer có waiver hay dùng managed alternative có mandate waiver?
5. Có cần giảm sizing hoặc defer component nào không? Nếu có, CDO04 phải ghi rõ rủi ro được chấp nhận.

**Approval gate:** REL-14 không được provision khi một service còn `Pending`, chưa có Calculator evidence, hoặc tổng projected spend vượt $300/tuần mà chưa có written exception.

## 2. Vì sao cần review này?

Mandate 8 yêu cầu chuyển:

- PostgreSQL đang chạy trong EKS sang RDS for PostgreSQL.
- Valkey của Cart sang ElastiCache for Valkey.
- Kafka sang Amazon MSK.

Review này chỉ xin duyệt sizing và ngân sách. Nó không cho phép tạo resource, đổi application endpoint hoặc xóa data store hiện tại.

Các con số bên dưới là planning estimate để so sánh phương án, không phải báo giá. Trước khi approve, CDO04 cần:

- Chọn đúng AWS region và thời gian chạy thực tế.
- Lấy current weekly run-rate của toàn bộ TF từ Cost Explorer.
- Tạo AWS Pricing Calculator export/permalink cho từng option được chọn.
- Cộng chi phí steady-state, dual-run migration và các chi phí dùng chung.
- Xác nhận tổng chi phí nằm trong budget hoặc ghi nhận exception bằng văn bản.

## 3. Sizing option đề xuất

Runtime metrics chưa đầy đủ, vì vậy đây là starting size. REL-14 phải dùng inventory thực tế để xác nhận lại trước khi provision.

| Service | Option khuyến nghị cho production | Option tiết kiệm hơn | Trade-off cần chấp nhận |
|---|---|---|---|
| RDS for PostgreSQL | PostgreSQL major tương thích source; `db.t4g.micro`; gp3 20 GiB và autoscaling; Multi-AZ; automated backup 7 ngày | Single-AZ, cùng instance/storage size | Single-AZ giảm chi phí HA nhưng instance hoặc AZ failure có thể làm Product Catalog, Product Reviews và Accounting ngừng hoạt động. Không phù hợp system of record nếu chưa có explicit risk acceptance |
| ElastiCache for Valkey | Cluster mode disabled; một primary + một replica `cache.t4g.micro` ở hai AZ; automatic failover; snapshot 7 ngày | Một node Single-AZ | Một node không có failover. Maintenance hoặc node/AZ failure có thể làm Cart unavailable và mất active cart chưa được phục hồi |
| Amazon MSK | MSK Serverless; private access; TLS + IAM | So sánh với MSK Provisioned ba broker ở size nhỏ nhất được region/client hỗ trợ; dùng SCRAM nếu IAM client không tương thích | Serverless giảm công việc sizing/vận hành nhưng có cluster-hour cost ngay cả khi traffic thấp. Provisioned có minimum multi-broker fixed cost và chưa chắc rẻ hơn với workload nhỏ |

Khuyến nghị production vẫn là Multi-AZ cho RDS và ElastiCache. Nếu budget không đủ, team không tự động bỏ HA. CDO04 + PM phải chấp nhận rủi ro hoặc điều chỉnh budget/scope bằng văn bản.

## 4. Planning cost estimate

### 4.1 Giả định

- Workload nhỏ, khoảng 168 giờ/tuần.
- Chưa có runtime inventory hoàn chỉnh về TPS, throughput, storage growth và retention.
- Chưa gồm tax, NAT, data transfer/cross-AZ, CloudWatch ingestion, KMS requests và migration dual-run.
- Giá thực tế phụ thuộc region và giá tại ngày provision.

| Component | Estimated monthly | Estimated weekly |
|---|---:|---:|
| RDS Multi-AZ + 20 GiB gp3 | $40–70 | $9–16 |
| ElastiCache hai node Multi-AZ | $22–43 | $5–10 |
| MSK Serverless với traffic thấp | $545–800 | $126–185 |
| Backup, log và KMS headroom | $15–40 | $4–9 |
| **Managed steady-state subtotal** | **$622–953** | **$144–220** |

Khoảng trống lý thuyết so với trần $300/tuần là **$80–156/tuần**. Đây chưa phải budget headroom thật vì khoảng đó còn phải trả EKS, NAT, ALB, observability và các resource TF hiện hữu.

Công thức approval:

```text
current TF weekly run-rate
+ managed steady-state
+ migration dual-run headroom
+ shared/usage cost chưa nằm trong estimate
<= $300/week
```

Nếu công thức trên không đạt, trạng thái phải là `Rejected` hoặc `Approved with written budget exception`; không được ghi `Approved` thông thường.

## 5. Single-AZ và Multi-AZ hiểu đơn giản như thế nào?

| Phương án | Lợi ích | Rủi ro |
|---|---|---|
| Multi-AZ / có replica | Có bản sao và failover, giảm downtime khi instance/AZ gặp sự cố hoặc maintenance | Chi phí cao hơn; vẫn cần backup và restore test |
| Single-AZ / một node | Chi phí thấp hơn | Không có khả năng chịu lỗi AZ tương đương; downtime và data recovery impact cao hơn |

Single-AZ chỉ được chọn khi CDO04 + PM ghi rõ:

- Environment nào được áp dụng.
- Downtime/data-loss risk nào được chấp nhận.
- Thời hạn áp dụng và thời điểm review lại.
- Ai là risk owner.

## 6. Backup retention và chi phí liên quan

Đề xuất retention tối thiểu:

- RDS automated backup: 7 ngày.
- ElastiCache snapshot: 7 ngày.
- MSK retention: chốt theo runtime topic inventory và rollback window, không chọn tùy ý chỉ để giảm giá.

Các khoản CDO04 cần đưa vào Calculator hoặc cost headroom:

- RDS backup vượt free allocation, manual snapshot và snapshot giữ sau khi xóa instance.
- ElastiCache snapshot storage.
- MSK broker/storage hoặc Serverless capacity/data processing.
- CloudWatch log, custom metric và alarm.
- KMS request/key cost nếu dùng customer-managed key.
- Cross-AZ/data transfer và NAT nếu traffic path đi qua NAT ngoài dự kiến.
- Chi phí chạy source và target song song trong migration/rollback window.

REL-14 phải gắn cost allocation tag, tạo budget alert ở 80% và 100%, rồi review Cost Explorer sau 7 và 14 ngày.

## 7. MSK là cost risk lớn nhất

Trong planning range hiện tại, MSK chiếm khoảng **84–88%** managed steady-state subtotal. MSK có cluster-hour/fixed capacity cost ngay cả khi traffic thấp, nên có thể đắt hơn nhiều so với Kafka một broker đang dùng chung EKS capacity.

Kafka in-cluster có direct cost thấp hơn nhưng không đáp ứng Mandate 8 vì mandate yêu cầu MSK. Vì vậy không được giữ Kafka self-hosted rồi đánh dấu task Done chỉ để tránh chi phí.

Trước khi CDO04 chọn MSK option, Quân/REL-17 phải cung cấp:

- Số topic và partition.
- Retention và storage thực tế.
- Bytes in/out và message-size p95.
- Consumer group và lag.
- Client compatibility với IAM/SCRAM.
- Calculator comparison giữa Serverless và Provisioned tại đúng region.

Nếu MSK vượt budget, CDO04/PM phải chọn một phương án theo thứ tự ưu tiên:

1. So sánh lại Serverless và Provisioned; tuning retention, log verbosity hoặc capacity dựa trên metrics, không giảm durability một cách mù quáng.
2. Xin budget exception vì Directive #8 bắt buộc dùng managed service.
3. Defer MSK chỉ khi mandate owner cấp waiver bằng văn bản; Kafka self-hosted khi đó vẫn là open gap.
4. Chỉ chọn managed Kafka alternative khi mandate owner xác nhận bằng văn bản rằng phương án đó đáp ứng yêu cầu “MSK”. Team không tự thay đổi scope.

## 8. Checklist CDO04 phải trả lời

CDO04 điền `Approved`, `Approved with conditions`, `Rejected` hoặc `Deferred with waiver` cho từng dòng.

| Câu hỏi | Decision | Điều kiện/risk acceptance | Evidence |
|---|---|---|---|
| Approve RDS? Chọn Multi-AZ hay Single-AZ? | Pending | `<điền>` | `<Calculator/export>` |
| Approve ElastiCache? Chọn hai node Multi-AZ hay một node? | Pending | `<điền>` | `<Calculator/export>` |
| Approve MSK? Chọn Serverless hay Provisioned? | Pending | `<điền>` | `<Calculator comparison>` |
| Nếu MSK vượt budget, chọn tuning, exception, defer có waiver hay alternative có waiver? | Pending | `<điền>` | `<decision/waiver link>` |
| Có giảm sizing hoặc defer component nào không? | Pending | `<nêu component và risk>` | `<approval link>` |
| Approve backup retention 7 ngày và MSK retention đã tính? | Pending | `<điền>` | `<cost breakdown>` |
| Approve migration dual-run headroom và rollback window cost? | Pending | `<điền>` | `<cost breakdown>` |
| Calculator + current TF run-rate có ≤ $300/tuần không? | Pending | `<projected total>` | `<Cost Explorer + Calculator>` |

## 9. Decision record để ký duyệt

| Item | Selected option | Monthly | Weekly | Decision/condition | Reviewer/date |
|---|---|---:|---:|---|---|
| RDS | `<Multi-AZ / Single-AZ / reject>` | `<USD>` | `<USD>` | Pending | `<CDO04 / date>` |
| ElastiCache | `<2-node / 1-node / reject>` | `<USD>` | `<USD>` | Pending | `<CDO04 / date>` |
| MSK | `<Serverless / Provisioned / waiver>` | `<USD>` | `<USD>` | Pending | `<CDO04 / date>` |
| Backup/log/KMS | `<retention và assumptions>` | `<USD>` | `<USD>` | Pending | `<CDO04 / date>` |
| Migration dual-run | `<số ngày/tuần>` | `<USD>` | `<USD>` | Pending | `<CDO04 / date>` |
| Existing TF run-rate | `<Cost Explorer period>` | `<USD>` | `<USD>` | Pending | `<CDO04 / date>` |
| **Overall projected spend** | `<Calculator + actual>` | **`<USD>`** | **`<USD>`** | **Pending** | `<CDO04 / date>` |

### Final decision

- [ ] **Approved:** Tất cả service được approve và overall projected spend ≤ $300/tuần.
- [ ] **Approved with conditions:** Ghi rõ điều kiện, deadline, risk owner và evidence còn thiếu; điều kiện phải hoàn tất trước REL-14.
- [ ] **Approved with budget exception:** Có written exception link và approver hợp lệ.
- [ ] **Rejected:** Không provision; trả lại CDO08 để đổi option/scope.
- [ ] **Deferred with mandate waiver:** Có waiver link; component vẫn là open gap, chưa được tính Done.

- **CDO04 reviewer:** `<name>`
- **Decision date:** `<YYYY-MM-DD>`
- **Approval/waiver link:** `<link>`
- **Comment:** `<conditions hoặc lý do>`

## 10. Điều kiện mở REL-14

REL-14 chỉ được bắt đầu khi đồng thời thỏa mãn:

- [ ] Runtime sizing input đã được attach.
- [ ] Calculator export/permalink đúng region đã được attach cho RDS, ElastiCache và MSK option được chọn.
- [ ] Current TF weekly run-rate từ Cost Explorer đã được attach.
- [ ] Backup, logging, KMS, data transfer và dual-run headroom đã được tính.
- [ ] Tất cả dòng bắt buộc trong Decision record không còn `Pending`.
- [ ] Overall projected spend nằm trong budget hoặc có written exception.
- [ ] Risk acceptance/waiver có PM và mandate owner khi cần.

Nếu thiếu một điều kiện, REL-14 giữ trạng thái **Blocked by cost approval** và không provision resource.
