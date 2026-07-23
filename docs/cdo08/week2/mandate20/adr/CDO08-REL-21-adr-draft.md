> **TRẠNG THÁI: DRAFT - CHƯA KÝ.** Nguyên sẽ research thêm và điền/chỉnh số liệu trước khi ký chính thức. Không dùng file này làm căn cứ nộp mentor cho tới khi có chữ ký ở mục cuối.

# CDO08-REL-21 - ADR: RPO/RTO, Backup Cadence & Retention cho Mandate 20

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20
**Subtask:** "Hoàn thiện quyết định kiến trúc và cam kết trách nhiệm"
**Input:** [CDO08-REL-21-rpo-rto-matrix.md](CDO08-REL-21-rpo-rto-matrix.md), [CDO08-REL-21-backup-policy-matrix.md](CDO08-REL-21-backup-policy-matrix.md), [CDO08-REL-20-stateful-store-inventory.md](../scan/CDO08-REL-20-stateful-store-inventory.md), [CDO08-REL-20-gap-register.md](../scan/CDO08-REL-20-gap-register.md)

---

## 1. Scope

ADR này chốt RPO/RTO, backup cadence, retention, và chiến lược restore cho từng tầng dữ liệu trên luồng browse -> cart -> checkout, theo yêu cầu #2 của Mandate 20. Không bao gồm: chịu mất AZ/region (Mandate 21), thực thi drill thật (task riêng, xem gap register REL-26), và hạ tầng observability (`opensearch`/`prometheus`) - không nằm trên luồng browse->cart->checkout nên không thuộc phạm vi Mandate 20, không xét trong ADR này.

## 2. Inventory reference

Toàn bộ store liên quan đã inventory tại [CDO08-REL-20-stateful-store-inventory.md](../scan/CDO08-REL-20-stateful-store-inventory.md). Không có store nào ngoài danh sách đó nằm trên luồng ra tiền.

## 3. RPO / RTO cam kết theo tầng dữ liệu

*(copy từ matrix - điền số cuối cùng sau khi research xong, xem [CDO08-REL-21-rpo-rto-matrix.md](CDO08-REL-21-rpo-rto-matrix.md) để có bản đầy đủ + rationale)*

| Store | RPO | RTO |
|---|---|---|
| RDS `accounting` | *(đề xuất: 15 phút)* | *(đề xuất: 1 giờ)* |
| MSK `orders` | *(đề xuất: 15 phút)* | *(đề xuất: 2 giờ)* |
| ElastiCache `valkey-cart` | *(đề xuất: không cam kết)* | *(đề xuất: 30 phút)* |
| RDS `catalog` | N/A | *(đề xuất: ~10-15 phút)* |
| RDS `reviews` | *(đề xuất: 1 giờ)* | *(đề xuất: 2 giờ)* |

## 4. Backup cadence & retention

*(xem đầy đủ tại [CDO08-REL-21-backup-policy-matrix.md](CDO08-REL-21-backup-policy-matrix.md))*

- RDS: automated backup + PITR, retention ngắn hạn 7 ngày *(đã có)* + đề xuất thêm retention dài hạn 35 ngày cho `accounting`.
- ElastiCache: automated snapshot, retention 7 ngày *(đã có, giữ nguyên)*.
- MSK: MSK Connect + S3 Sink Connector, cadence flush ≤ 15 phút, retention 7 ngày trên S3 + đề xuất 35 ngày dài hạn (GAP-02).
- RDS `accounting`: tách sang instance riêng (`db.t4g.micro`), tách khỏi `catalog`/`reviews` (GAP-06).

## 5. Encryption & separation of duties

- RDS, ElastiCache, MSK: đã mã hoá at-rest bằng KMS + in-transit TLS (xác nhận tại inventory §3) - **đạt yêu cầu #5 phần mã hoá**.
- Xoá backup: **chưa đạt** - role CI `tf4-github-actions-terraform-apply` hiện có `PowerUserAccess`, xoá được snapshot/backup không giới hạn (GAP-01 trong gap register, task REL-24). ADR này **không** tự đóng gap đó - chỉ ghi nhận và trỏ sang task xử lý.
- *(Cần điền: ai được phép approve xoá backup thủ công sau khi GAP-01 được xử lý - Nguyên research thêm)*

## 6. Restore isolation

Restore luôn thực hiện ra môi trường tách biệt (RDS point-in-time restore tạo instance mới, ElastiCache restore tạo replication group mới), không ghi đè lên production đang chạy - đúng ràng buộc của mandate.

## 7. Drill scenario (kế hoạch, chưa chạy)

- **RDS `accounting`**: giả lập mất dữ liệu bằng cách xoá/sửa 1 số bản ghi trong bảng `order` ở môi trường test, restore về mốc trước đó bằng PITR, so sánh dữ liệu khôi phục với snapshot kỳ vọng, đo thời gian từ lúc bắt đầu restore tới lúc `accounting` đọc lại đúng.
- **ElastiCache `valkey-cart`**: giả lập mất cache, xác nhận cart service tự phục hồi (rỗng, không lỗi), đo thời gian tạo lại cluster.
- **MSK `orders`** (sau khi có S3 Sink Connector): giả lập mất cluster/topic, dựng lại MSK mới, replay message từ S3 archive vào `accounting`, đối chiếu số lượng order nhận được với số lượng order thật đã checkout trong khoảng thời gian đó - xác nhận không thiếu đơn hàng nào, đo thời gian từ lúc mất tới lúc replay xong.
- Rollback/safety: toàn bộ drill chạy trên môi trường tách biệt/snapshot restore ra instance mới - không đụng production, không cần rollback plan riêng cho chính thao tác drill.

## 8. Người phê duyệt

| Vai trò | Tên | Ngày ký |
|---|---|---|
| Techlead - chốt RPO/RTO & cadence, quyết định đầu tư MSK archival + tách RDS instance | Nguyên *(chưa ký)* | |
| PM - xác nhận chi phí/effort thêm cho MSK Connect + S3 Sink và RDS instance mới | Hải *(chưa ký)* | |

---

**Việc còn lại trước khi ký chính thức:**
1. Triển khai MSK Connect + S3 Sink Connector (GAP-02) và tách RDS instance cho `accounting` (GAP-06) - 2 quyết định đã chốt, cần thực hiện trước khi drill.
2. Điền tên người approve xoá backup ở mục 5 sau khi GAP-01 (REL-24) có hướng xử lý.
3. Chạy drill thật (REL-26) để đo số thật, đối chiếu với target đã đề xuất.
4. Sau khi các mục trên xong, chuyển trạng thái đầu file từ DRAFT sang SIGNED kèm ngày ký.

**Quy trình chốt số (draft → sửa gap → test → điều chỉnh → ký)** được trình bày đầy đủ, kèm nguồn tham khảo (AWS Well-Architected, Google DiRT), tại [CDO08-REL-21-REVIEW-REQUEST-RPO-RTO-PROCESS.md](../review-requests/CDO08-REL-21-REVIEW-REQUEST-RPO-RTO-PROCESS.md) - dùng file đó để trình PM trước khi chạy drill.
