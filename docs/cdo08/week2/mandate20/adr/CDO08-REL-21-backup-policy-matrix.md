# CDO08-REL-21 - Backup Policy Matrix (Draft)

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20, yêu cầu #2
**Subtask:** "Chọn tần suất và retention đáp ứng các mục tiêu đã cam kết"
**Trạng thái:** **Draft - đề xuất ban đầu.** Chờ Nguyên research thêm trước khi đưa vào ADR ký chính thức.
**Input:** [CDO08-REL-21-rpo-rto-matrix.md](CDO08-REL-21-rpo-rto-matrix.md) (số RPO/RTO đề xuất), [CDO08-REL-20-stateful-store-inventory.md](../scan/CDO08-REL-20-stateful-store-inventory.md) (cấu hình backup hiện có)

---

Retention chia 2 loại:
- **Ngắn hạn** - đủ để restore về một mốc gần khi phát hiện lỗi ngay (đáp ứng RPO thao tác hằng ngày).
- **Dài hạn** - phòng trường hợp phát hiện lỗi muộn (VD: audit phát hiện sau 2-3 tuần), không giữ vô tận.

## Matrix

| Store | RPO mục tiêu | Cơ chế đáp ứng | Cadence hiện tại | Retention ngắn hạn | Retention dài hạn (đề xuất thêm) | Có mâu thuẫn với RPO? | Giới hạn AWS cần lưu ý |
|---|---|---|---|---|---|---|---|
| RDS `accounting` | 15 phút | Automated backup + PITR (continuous transaction log, không phải chỉ snapshot ngày) | Daily snapshot window 18:00-19:00 UTC + continuous log backup | 7 ngày (đang có) | Đề xuất thêm: 1 snapshot thủ công/AWS Backup giữ 35 ngày, phòng lỗi phát hiện muộn | **Không** - PITR restore theo giây nên tần suất snapshot ngày không ảnh hưởng RPO | PITR chỉ restore trong đúng cửa sổ `backup_retention_period` (7 ngày) - muốn về mốc xa hơn phải có snapshot dài hạn riêng |
| MSK `orders` | Best-effort | Không có cơ chế backup nào | N/A (chỉ có retention topic mặc định + replication factor 2) | N/A | Không áp dụng trừ khi quyết định thêm MSK Connect sink ra S3 (ngoài scope task này) | **Có, nếu ADR tuyên bố RPO chặt mà không làm gì thêm** - phải ghi rõ đây là rủi ro chấp nhận, không phải "đã đạt" | MSK không có API snapshot/backup - đây là giới hạn dịch vụ, không phải thiếu cấu hình |
| ElastiCache `valkey-cart` | Không cam kết | Automated snapshot (đã bật) | Daily, window 18:00-19:00 UTC | 7 ngày (đang có) | Không cần - dữ liệu ephemeral, mất cũng không ảnh hưởng tính đúng của hệ thống | Không | Snapshot restore có thể mất vài phút tuỳ kích thước - chấp nhận được vì RTO ở đây không chặt |
| RDS `catalog` | N/A | Seed lại từ Helm/git, không dùng snapshot | N/A | N/A | N/A | Không áp dụng | Không |
| RDS `reviews` | 1 giờ | Chung PITR với `accounting` (cùng instance) | Chung window với `accounting` | 7 ngày (đang có, dùng chung) | Dùng chung retention dài hạn với `accounting` nếu thêm | Không | Vì chung instance, restore `accounting` sẽ kéo theo restore `reviews` cùng lúc - cần test rõ trong drill |

## Kiểm tra "cadence có mâu thuẫn với RPO không"

Nguyên tắc: **cadence backup phải nhỏ hơn hoặc bằng RPO**. Nếu RPO 1 giờ mà chỉ backup mỗi ngày → mâu thuẫn (mandate nêu rõ ví dụ này).

- RDS `accounting`/`reviews`: dùng PITR (continuous log), không phải chỉ snapshot ngày → RPO 15 phút/1 giờ đều đạt được, **không mâu thuẫn**.
- ElastiCache: chỉ có snapshot ngày, nhưng vì không cam kết RPO chặt (dữ liệu ephemeral) nên **không mâu thuẫn**.
- MSK: không có cơ chế nào để so sánh - đây là **gap cần ghi rõ trong ADR**, không phải mâu thuẫn cadence.

## Lý do từng mức retention

- **7 ngày (ngắn hạn, RDS/ElastiCache)**: đủ để bắt lỗi phát hiện trong tuần (case phổ biến nhất - migration lỗi, bug mới deploy), khớp với cấu hình đang chạy thật, không cần đổi gì thêm.
- **35 ngày (dài hạn, đề xuất thêm cho `accounting`)**: đủ để bắt lỗi phát hiện muộn hơn (VD: audit hàng tháng, khách khiếu nại trễ), nhưng không giữ vô tận để tránh phát sinh chi phí lưu trữ không cần thiết - đúng tinh thần "retention hợp lý, không giữ vô tận" của mandate.
