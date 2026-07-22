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
| MSK `orders` | 15 phút | MSK Connect + S3 Sink Connector, archival liên tục topic `orders` ra S3 (GAP-02) | Sink flush liên tục (chu kỳ ~5-15 phút tuỳ cấu hình connector) | 7 ngày trên S3 (khớp retention RDS) | Đề xuất thêm 35 ngày trên S3 (rẻ) | **Không** - miễn cadence flush ≤ 15 phút | MSK bản thân không có API snapshot/backup - lý do phải archival ra ngoài (S3) |
| ElastiCache `valkey-cart` | Không cam kết | Automated snapshot (đã bật) | Daily, window 18:00-19:00 UTC | 7 ngày (đang có) | Không cần - dữ liệu ephemeral, mất cũng không ảnh hưởng tính đúng của hệ thống | Không | Snapshot restore có thể mất vài phút tuỳ kích thước - chấp nhận được vì RTO ở đây không chặt |
| RDS `catalog` | N/A | Seed lại từ Helm/git, không dùng snapshot | N/A | N/A | N/A | Không áp dụng | Không |
| RDS `reviews` | 1 giờ | PITR chung instance với `catalog` (đã tách khỏi `accounting`, xem GAP-06) | Chung window với `catalog` | 7 ngày (đang có, dùng chung với `catalog`) | Dùng chung retention dài hạn với `catalog` nếu cần | Không | Instance `catalog`+`reviews` restore chung không sao vì cả 2 đều không critical |

## Kiểm tra "cadence có mâu thuẫn với RPO không"

Nguyên tắc: **cadence backup phải nhỏ hơn hoặc bằng RPO**. Nếu RPO 1 giờ mà chỉ backup mỗi ngày → mâu thuẫn (mandate nêu rõ ví dụ này).

- RDS `accounting`/`reviews`: dùng PITR (continuous log), không phải chỉ snapshot ngày → RPO 15 phút/1 giờ đều đạt được, **không mâu thuẫn**.
- ElastiCache: chỉ có snapshot ngày, nhưng vì không cam kết RPO chặt (dữ liệu ephemeral) nên **không mâu thuẫn**.
- MSK: sau khi thêm MSK Connect + S3 Sink Connector, cadence flush của connector phải ≤ 15 phút để khớp RPO đã cam kết - cần cấu hình rõ khi triển khai (REL-25), không được để mặc định lỏng hơn 15 phút.

## Lý do từng mức retention

- **7 ngày (ngắn hạn, RDS/ElastiCache)**: đủ để bắt lỗi phát hiện trong tuần (case phổ biến nhất - migration lỗi, bug mới deploy), khớp với cấu hình đang chạy thật, không cần đổi gì thêm.
- **35 ngày (dài hạn, đề xuất thêm cho `accounting`)**: đủ để bắt lỗi phát hiện muộn hơn (VD: audit hàng tháng, khách khiếu nại trễ), nhưng không giữ vô tận để tránh phát sinh chi phí lưu trữ không cần thiết - đúng tinh thần "retention hợp lý, không giữ vô tận" của mandate.

## Nguồn tham khảo

> Đã tự vào đọc trực tiếp trang bên dưới để xác minh câu trích, không chỉ tin công cụ search.

**Nguồn 1 - AWS Well-Architected Framework, "Back up data"**
Link: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/back-up-data.html

Nguyên văn tiếng Anh: *"Back up data, applications, and configuration to meet requirements for recovery time objectives (RTO) and recovery point objectives (RPO)."*

Dịch: *"Backup dữ liệu, ứng dụng và cấu hình để đáp ứng yêu cầu RTO/RPO."*

Ý nghĩa cho bảng này: cadence/retention **không được chọn tuỳ ý trước rồi mới xem có đạt RPO không** - phải làm ngược lại, chốt RPO trước rồi mới chọn cadence để đáp ứng đúng RPO đó. Bảng ở trên đang làm đúng thứ tự này (cột "RPO mục tiêu" đứng trước, "Cơ chế đáp ứng"/"Cadence" đứng sau).

**Nguồn 2 - chính văn bản Mandate 20 (nội bộ)**
Link: [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md), yêu cầu #2

Nguyên văn: *"tần suất backup phải đủ để đạt RPO đã cam kết (RPO 1 giờ mà backup mỗi ngày là mâu thuẫn)"*

Đây là nguyên tắc "cadence backup phải nhỏ hơn hoặc bằng RPO" - lấy thẳng từ mandate, không phải suy diễn.
