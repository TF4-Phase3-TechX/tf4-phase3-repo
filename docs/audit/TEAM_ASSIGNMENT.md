# Kế hoạch Phân công Team Audit (8 Thành viên CD007) - Chỉ Audit & Evidence

Tài liệu này xác định rõ **Ranh giới trách nhiệm**: Team Audit (CD007) CHỈ làm nhiệm vụ kiểm toán, truy vết thay đổi (Audit/Evidence/Change Trace). Các vấn đề về thiết lập Security, Network, Reliability thuộc về team CD008.

Team Audit chỉ sử dụng các quyền: `CloudTrail read, IAM read, Access Analyzer read, Config read, CloudWatch Logs read, S3 read`.

Dưới đây là bảng phân công cho 8 thành viên trong team:

## Nhóm 1: Kiểm toán Truy cập & Tuân thủ (4 thành viên)
| Thành viên | Nhiệm vụ (Audit) | Tài liệu/Công việc |
|------------|-------------------|--------------------|
| **Member 1 (IAM Auditor)** | Đọc IAM & Access Analyzer. Soát xét xem ai đang có quyền gì, có over-privileged không. | `IAM_AUDIT_DOC.md` |
| **Member 2 (Config Auditor)** | Sử dụng AWS Config (Read) để xem lịch sử thay đổi cấu hình hạ tầng. | `AUDIT_CHECKLIST.md` |
| **Member 3 (ADR/Change Tracer)** | Quản lý folder ghi chép lại *lý do* thay đổi kiến trúc (Architecture Decision Records). | Quản lý folder `/adr` |
| **Member 4 (Evidence Collector)** | Tổng hợp các log, ảnh chụp (Evidence) từ các thành viên khác thành báo cáo hàng tuần. | Báo cáo Audit hàng tuần |

## Nhóm 2: Lên Yêu cầu & Nghiệm thu Task P0 (4 thành viên)
Nhóm này yêu cầu DevOps bật các tool lưu vết và kiểm tra kết quả (Không tự tay cấu hình).

| Thành viên | Nhiệm vụ Uỷ quyền (DevOps làm) | Công việc của Audit (Bạn làm) |
|------------|--------------------------------|-------------------------------|
| **Member 5 (CloudTrail Tracker)** | [Task 1.1] Bật CloudTrail + S3 Versioning | Đưa requirement. Đọc S3 để verify có log CloudTrail. |
| **Member 6 (CloudWatch Tracker)** | [Task 1.2] Bật CloudWatch Logs cho EKS | Đưa requirement. Mở CloudWatch đọc log Control Plane. |
| **Member 7 (Log Retention Tracker)**| [Task 3.1] Cấu hình OpenSearch ISM | Đưa requirement. Review file policy JSON giới hạn thời gian lưu log. |
| **Member 8 (Dashboard Tracker)** | [Task 3.2] Xây dựng Grafana Audit Dash. | Cung cấp logic mã lỗi (401/403) cho DevOps. Mở Grafana để soi log audit. |
