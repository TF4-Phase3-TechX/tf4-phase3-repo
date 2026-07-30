> **TRẠNG THÁI: SIGNED - 2026-07-27.** ADR chốt RPO/RTO, backup cadence, retention và chiến lược restore cho Mandate 20 yêu cầu #2. Đây là baseline mục tiêu để REL-26 (RDS) và REL-25 (MSK) chạy drill thật kiểm chứng - kết quả drill được ghi nhận riêng trong evidence, không thuộc phạm vi ADR này.

# CDO08-REL-21 - ADR: RPO/RTO, Backup Cadence & Retention cho Mandate 20

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20
**Subtask:** "Hoàn thiện quyết định kiến trúc và cam kết trách nhiệm"
**Input:** [CDO08-REL-21-rpo-rto-matrix.md](CDO08-REL-21-rpo-rto-matrix.md), [CDO08-REL-21-backup-policy-matrix.md](CDO08-REL-21-backup-policy-matrix.md), [CDO08-REL-20-stateful-store-inventory.md](../scan/CDO08-REL-20-stateful-store-inventory.md), [CDO08-REL-20-gap-register.md](../scan/CDO08-REL-20-gap-register.md), [CDO08-REL-21-restore-isolation-rationale.md](CDO08-REL-21-restore-isolation-rationale.md)

---

## 1. Scope

ADR này chốt RPO/RTO, backup cadence, retention, và chiến lược restore cho từng tầng dữ liệu trên luồng browse -> cart -> checkout, theo yêu cầu #2 của Mandate 20. Không bao gồm: chịu mất AZ/region (Mandate 21), thực thi drill thật (task riêng - REL-26 cho RDS, REL-25 cho MSK), và hạ tầng observability (`opensearch`/`prometheus`) - không nằm trên luồng browse->cart->checkout nên không thuộc phạm vi Mandate 20, không xét trong ADR này.

## 2. Inventory reference

Toàn bộ store liên quan đã inventory tại [CDO08-REL-20-stateful-store-inventory.md](../scan/CDO08-REL-20-stateful-store-inventory.md). Không có store nào ngoài danh sách đó nằm trên luồng ra tiền.

## 3. RPO / RTO cam kết theo tầng dữ liệu

*(copy từ matrix, xem [CDO08-REL-21-rpo-rto-matrix.md](CDO08-REL-21-rpo-rto-matrix.md) để có rationale đầy đủ + nguồn tham khảo)*

| Store | RPO | RTO |
|---|---|---|
| RDS `accounting` | 15 phút | 1 giờ |
| MSK `orders` | 15 phút | 2 giờ |
| ElastiCache `valkey-cart` | Không cam kết | ~30 phút (best-effort) |

## 4. Backup cadence & retention

*(xem đầy đủ tại [CDO08-REL-21-backup-policy-matrix.md](CDO08-REL-21-backup-policy-matrix.md))*

- RDS: automated backup + PITR, retention ngắn hạn 7 ngày *(đã có)* + thêm AWS Backup recovery point retention 35 ngày cho `accounting`.
- ElastiCache: automated snapshot, retention 7 ngày *(đã có, giữ nguyên)*.
- MSK: archival liên tục topic `orders` ra S3 qua **self-managed Kafka Connect + S3 Sink connector chạy trên EKS** - **không dùng AWS MSK Connect managed service**, vì `CreateConnector` của dịch vụ managed bị AWS account/service-level block, không có ETA gỡ (xem `CDO08-REL-28-jira-description.md`). Cadence flush phải ≤ 15 phút để khớp RPO đã cam kết, retention 7 ngày trên S3 + đề xuất thêm 35 ngày dài hạn (GAP-02).
- RDS `accounting`: **không tách sang instance riêng** khỏi `catalog`/`reviews`. Quyết định GAP-06: giữ chung 1 instance, restore dùng runbook restore-theo-schema (PITR toàn instance ra instance tạm → `pg_dump -n accounting` → verify → merge đúng schema `accounting` vào production) - xem căn cứ đầy đủ tại [CDO08-REL-21-restore-isolation-rationale.md](CDO08-REL-21-restore-isolation-rationale.md). Cách này đạt isolation yêu cầu #3 mà không cần migrate hạ tầng, rẻ và ít rủi ro hơn tách instance.

## 5. Encryption & separation of duties

- RDS, ElastiCache, MSK: đã mã hoá at-rest bằng KMS + in-transit TLS (xác nhận tại inventory §3) - **đạt yêu cầu #5 phần mã hoá**.
- Xoá backup: role CI `tf4-github-actions-terraform-apply` bị ràng buộc bởi permissions boundary + explicit deny (GAP-01, xử lý ở REL-24) - không xoá được RDS snapshot, ElastiCache snapshot, S3 archive object, hay MSK cluster dù vẫn giữ `PowerUserAccess`/`IAMFullAccess` để tương thích CI.
- **Ai được phép approve xoá backup** (theo [CDO08-REL-24-backup-deletion-separation-of-duties.md](CDO08-REL-24-backup-deletion-separation-of-duties.md)):
  - Người **request** xoá: Incident commander (không phải operator thường).
  - Người **approve**: PM **và** Tech Lead (bắt buộc cả hai).
  - Người **thực thi**: chỉ role `tf4-rel24-backup-delete-break-glass`, và chỉ trong một assume-role session có tag bắt buộc `Rel24DeletionApproved=true` cùng `ChangeId=<ticket/incident id>` - không có tag thì role này cũng không xoá được.
  - Mọi lần xoá đều để lại CloudTrail event, audit bởi CDO07.

## 6. Restore isolation

Restore luôn thực hiện ra môi trường tách biệt (RDS point-in-time restore tạo instance mới, ElastiCache restore tạo replication group mới), không ghi đè lên production đang chạy - đúng ràng buộc của mandate. RDS không có API restore-tại-chỗ (`restore-db-instance-to-point-in-time` bắt buộc target instance khác/mới), nên đây vừa là ràng buộc kỹ thuật vừa là lựa chọn quy trình - xem căn cứ đầy đủ tại [CDO08-REL-21-restore-isolation-rationale.md](CDO08-REL-21-restore-isolation-rationale.md). Chính rationale này là lý do GAP-06 không cần migrate `accounting` sang instance riêng: restore luôn ra instance tạm trước, rồi mới dump đúng schema `accounting` để merge vào production - `catalog`/`reviews` trên production không bị đụng dù restore chung 1 instance.

## 7. Drill scenario (kế hoạch, chưa chạy)

- **RDS `accounting`** (task REL-26): giả lập mất dữ liệu bằng cách xoá/sửa một số bản ghi trong bảng `order` ở một RDS temp source (dựng từ production PITR, không đụng production), restore về mốc trước đó ra một RDS drill riêng bằng PITR, verify dữ liệu khôi phục đúng, rồi merge đúng phần dữ liệu đã mất về RDS temp source - theo đúng runbook restore-theo-schema ở mục 4/6. Đo thời gian từ lúc xác nhận mất dữ liệu tới lúc dữ liệu đọc lại đúng.
- **MSK `orders`** (task REL-25): giả lập cần khôi phục dữ liệu order đã archive, đọc lại archive từ S3 theo time window, replay vào một topic drill cô lập (không đụng topic production `orders`), consume lại và đối chiếu số lượng/nội dung record với kỳ vọng - xác nhận không thiếu đơn hàng nào. Đo thời gian từ lúc bắt đầu replay tới lúc validate xong.
- **ElastiCache `valkey-cart`**: không cần restore drill riêng - cart được chốt là `Reconstructable` (dữ liệu tạm, TTL ngắn, khách tự thêm lại), một restore drill không cải thiện outcome thực tế so với để cache tự rebuild rỗng. Backup baseline (snapshot 7 ngày, encryption, Multi-AZ) vẫn giữ nguyên.
- Rollback/safety: toàn bộ drill chạy trên tài nguyên tạm/topic cô lập, không đụng production - đúng ràng buộc "không đè/không phá production khi drill" của mandate. Không cần rollback plan riêng cho chính thao tác drill vì tài nguyên drill bị xoá ở bước cleanup, không tác động production.

## 8. Người phê duyệt

| Vai trò | Tên | Ngày ký |
|---|---|---|
| Techlead - chốt RPO/RTO & cadence, quyết định archival MSK + runbook restore-theo-schema cho `accounting` | Nguyên | 2026-07-27 |
| PM - xác nhận chi phí/effort cho MSK archival + xác nhận cart là Reconstructable | Hải | 2026-07-27 |

---
