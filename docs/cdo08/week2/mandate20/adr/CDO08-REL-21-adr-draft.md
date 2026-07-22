> **TRẠNG THÁI: DRAFT - CHƯA KÝ.** Nguyên sẽ research thêm và điền/chỉnh số liệu trước khi ký chính thức. Không dùng file này làm căn cứ nộp mentor cho tới khi có chữ ký ở mục cuối.

# CDO08-REL-21 - ADR: RPO/RTO, Backup Cadence & Retention cho Mandate 20

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20
**Subtask:** "Hoàn thiện quyết định kiến trúc và cam kết trách nhiệm"
**Input:** [CDO08-REL-21-rpo-rto-matrix.md](CDO08-REL-21-rpo-rto-matrix.md), [CDO08-REL-21-backup-policy-matrix.md](CDO08-REL-21-backup-policy-matrix.md), [CDO08-REL-20-stateful-store-inventory.md](../scan/CDO08-REL-20-stateful-store-inventory.md), [CDO08-REL-20-gap-register.md](../scan/CDO08-REL-20-gap-register.md)

---

## 1. Scope

ADR này chốt RPO/RTO, backup cadence, retention, và chiến lược restore cho từng tầng dữ liệu trên luồng browse -> cart -> checkout, theo yêu cầu #2 của Mandate 20. Không bao gồm: chịu mất AZ/region (Mandate 21), thực thi drill thật (task riêng, xem gap register REL-26).

## 2. Inventory reference

Toàn bộ store liên quan đã inventory tại [CDO08-REL-20-stateful-store-inventory.md](../scan/CDO08-REL-20-stateful-store-inventory.md). Không có store nào ngoài danh sách đó nằm trên luồng ra tiền.

## 3. RPO / RTO cam kết theo tầng dữ liệu

*(copy từ matrix - điền số cuối cùng sau khi research xong, xem [CDO08-REL-21-rpo-rto-matrix.md](CDO08-REL-21-rpo-rto-matrix.md) để có bản đầy đủ + rationale)*

| Store | RPO | RTO |
|---|---|---|
| RDS `accounting` | *(đề xuất: 15 phút)* | *(đề xuất: 1 giờ)* |
| MSK `orders` | *(đề xuất: best-effort, ghi rõ rủi ro)* | *(đề xuất: 2 giờ)* |
| ElastiCache `valkey-cart` | *(đề xuất: không cam kết)* | *(đề xuất: 30 phút)* |
| RDS `catalog` | N/A | *(đề xuất: ~10-15 phút)* |
| RDS `reviews` | *(đề xuất: 1 giờ)* | *(đề xuất: 2 giờ)* |

## 4. Backup cadence & retention

*(xem đầy đủ tại [CDO08-REL-21-backup-policy-matrix.md](CDO08-REL-21-backup-policy-matrix.md))*

- RDS: automated backup + PITR, retention ngắn hạn 7 ngày *(đã có)* + đề xuất thêm retention dài hạn 35 ngày cho `accounting`.
- ElastiCache: automated snapshot, retention 7 ngày *(đã có, giữ nguyên)*.
- MSK: không có cơ chế backup - ghi nhận là giới hạn dịch vụ, không phải thiếu cấu hình.

## 5. Encryption & separation of duties

- RDS, ElastiCache, MSK: đã mã hoá at-rest bằng KMS + in-transit TLS (xác nhận tại inventory §3) - **đạt yêu cầu #5 phần mã hoá**.
- Xoá backup: **chưa đạt** - role CI `tf4-github-actions-terraform-apply` hiện có `PowerUserAccess`, xoá được snapshot/backup không giới hạn (GAP-01 trong gap register, task REL-24). ADR này **không** tự đóng gap đó - chỉ ghi nhận và trỏ sang task xử lý.
- *(Cần điền: ai được phép approve xoá backup thủ công sau khi GAP-01 được xử lý - Nguyên research thêm)*

## 6. Restore isolation

Restore luôn thực hiện ra môi trường tách biệt (RDS point-in-time restore tạo instance mới, ElastiCache restore tạo replication group mới), không ghi đè lên production đang chạy - đúng ràng buộc của mandate.

## 7. Drill scenario (kế hoạch, chưa chạy)

- **RDS `accounting`**: giả lập mất dữ liệu bằng cách xoá/sửa 1 số bản ghi trong bảng `order` ở môi trường test, restore về mốc trước đó bằng PITR, so sánh dữ liệu khôi phục với snapshot kỳ vọng, đo thời gian từ lúc bắt đầu restore tới lúc `accounting` đọc lại đúng.
- **ElastiCache `valkey-cart`**: giả lập mất cache, xác nhận cart service tự phục hồi (rỗng, không lỗi), đo thời gian tạo lại cluster.
- *(Cần điền chi tiết drill cho MSK sau khi có quyết định về archival hoặc chấp nhận rủi ro)*
- Rollback/safety: toàn bộ drill chạy trên môi trường tách biệt/snapshot restore ra instance mới - không đụng production, không cần rollback plan riêng cho chính thao tác drill.

## 8. Người phê duyệt

| Vai trò | Tên | Ngày ký |
|---|---|---|
| Techlead - chốt RPO/RTO & cadence | *(chưa ký)* | |
| PM - xác nhận mức chấp nhận rủi ro (đặc biệt MSK) | Hải *(chưa ký)* | |

---

**Việc còn lại trước khi ký chính thức:**
1. Nguyên research thêm để xác nhận/điều chỉnh số RPO/RTO ở mục 3 (đặc biệt MSK - chấp nhận rủi ro hay đầu tư thêm archival).
2. Điền tên người approve xoá backup ở mục 5 sau khi GAP-01 (REL-24) có hướng xử lý.
3. Sau khi 2 mục trên xong, chuyển trạng thái đầu file từ DRAFT sang SIGNED kèm ngày ký.
