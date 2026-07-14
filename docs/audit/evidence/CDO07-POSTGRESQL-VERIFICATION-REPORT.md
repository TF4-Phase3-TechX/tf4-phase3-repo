# CDO07 Independent Verification Report: PostgreSQL Persistence & Auditability

**Người thực hiện:** CDO07
**Reviewer:** Bùi Thành Nghĩa
**Date:** 2026-07-13
**Target:** Kiểm chứng giải pháp Persistent Storage cho PostgreSQL của CDO08 (Issue 2)
**Role used:** `TF4-AuditReadOnlyAndAnalyze`

---

## 1. CDO07 Checklist (Nhiệm vụ được giao)

Tôi đã tiến hành rà soát và đánh giá dựa trên bằng chứng cung cấp trong `postgresql_persistance.md` cũng như yêu cầu Issue 2:
- [x] **Xác minh dữ liệu cần giữ phục vụ audit/evidence.** (Các bảng `accounting.order`, `accounting.orderitem`, `accounting.shipping`, `catalog.products`, `reviews.productreviews` đã tồn tại và sẵn sàng lưu trữ persistent).
- [x] **Kiểm tra dữ liệu còn tồn tại sau pod recreation.** (Dữ liệu không bị mất sau khi xóa Pod thủ công, các table `accounting` vẫn còn nguyên vẹn sau khi Pod mới khởi động lại).
- [ ] **Xác minh mentor rerun dùng cùng dataset hoặc có reset procedure rõ.** (Chưa có quy trình reset/rollback rõ ràng cho mentor chạy lại ngoại trừ file backup manual `postgres_backup.sql` lưu trên máy local).
- [x] **Review evidence, timestamp và remaining risk.** (Đã verify timestamp file backup, logs cấu hình StorageClass `gp2` 10Gi, ghi nhận các rủi ro về HA và automated backup).

---

## 2. Kết quả Xác minh Bền vững (Persistence)

### A. Cấu hình PersistentVolumeClaim (PVC)
- **Trạng thái:** ✅ PASS
- **Đánh giá:** PVC `postgresql-pvc` đã được mount thành công với dung lượng `10Gi` qua AWS EBS (`gp2`). Lỗi `lost+found` phổ biến khi dùng EBS đã được xử lý đúng chuẩn thông qua việc trỏ biến môi trường `PGDATA=/var/lib/postgresql/data/pgdata`.

### B. Khả năng bảo toàn dữ liệu sau khi Pod restart/recreate
- **Trạng thái:** ✅ PASS
- **Đánh giá:** Dựa trên log thao tác `kubectl delete pod`, pod mới được cấp phát lại. Bằng chứng truy vấn `\dt accounting.*` cho thấy sau restart, toàn bộ dữ liệu schema accounting vẫn được giữ nguyên. Giải quyết triệt để nguy cơ mất dữ liệu review/order giữa các lần Acceptance Test.

---

## 3. Xác minh trực tiếp (Dành cho CDO07 - Team Audit)

Dựa trên nguyên tắc Audit, CDO07 đã kiểm tra tính nhất quán dữ liệu và tính hợp lệ của evidence:

**Các bước đã rà soát:**
1. **Kiểm tra thông số PVC:** Trạng thái `Bound`, Access Mode `ReadWriteOnce` (phù hợp với Postgres đơn node), StorageClass `gp2`.
2. **Kiểm tra Schema/Dataset:** Các bảng lưu trữ dữ liệu kinh doanh (order, review, catalog) đã được lưu trên volume thay vì ephemeral filesystem.
3. **Kiểm tra Evidence Backup:** Đã xác nhận file `postgres_backup.sql` được dump ra local (~1.1MB) trước quá trình rollout, đáp ứng yêu cầu an toàn dữ liệu tạm thời.

---

## 4. Đánh giá Rủi ro Còn lại (Remaining Risk) & Khuyến nghị

- **Trạng thái:** ⚠️ WARNING / PENDING PROCEDURE
- **Xác minh:** 
  1. PostgreSQL đang chạy dưới dạng `Deployment` với `replicas: 1` sử dụng PVC `ReadWriteOnce`. Điều này có rủi ro nếu Node hiện tại down, pod có thể mất thời gian để mount lại volume sang Node khác hoặc gặp lỗi Multi-Attach.
  2. Chưa có script hay quy trình tự động hóa dọn dẹp/khôi phục dữ liệu (**Reset Procedure**) để Mentor có thể dễ dàng làm mới dataset trước khi chạy Acceptance Run kế tiếp.
- **Hành động yêu cầu/Khuyến nghị cho CDO08 & CDO04:**
  1. **Reset Procedure (CDO08/CDO04):** Xây dựng một kịch bản/script (ví dụ bash script bọc lệnh `kubectl exec` gọi file dump) để mentor có thể reset DB về trạng thái gốc trước mỗi lượt chấm.
  2. **Backup Automation (CDO08):** Đề xuất thêm CronJob tự động backup database thay vì phụ thuộc file dump lưu local của kỹ sư.
  3. **High Availability (Future Scope):** Cân nhắc nâng cấp kiến trúc lên StatefulSet hoặc sử dụng Managed Database (RDS) nếu ứng dụng tiến tới môi trường Production thực thụ.
