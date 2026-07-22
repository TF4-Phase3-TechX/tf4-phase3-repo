# CDO08-REL-20 (T3) - Gap Register

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20
**Subtask:** T3 - so sánh inventory ([CDO08-REL-20-revenue-path-dependency-trace.md](CDO08-REL-20-revenue-path-dependency-trace.md), [CDO08-REL-20-stateful-store-inventory.md](CDO08-REL-20-stateful-store-inventory.md)) với yêu cầu Mandate 20, gắn owner + deadline cho từng gap
**Owner:** Nguyên (Techlead)

Severity: **Critical** = mất dữ liệu thật hoặc backup có thể bị xoá không rào chắn · **High** = khôi phục được nhưng chậm/thiếu hơn mandate yêu cầu · **Medium** = ngoài luồng ra tiền hoặc ảnh hưởng thấp.

| ID | Gap | Evidence | Impact | Severity | Owner | Deadline | Task xử lý |
|---|---|---|---|---|---|---|---|
| GAP-01 | Role CI `tf4-github-actions-terraform-apply` có `PowerUserAccess` + `IAMFullAccess` - xoá được mọi snapshot/backup của RDS, DynamoDB, EC2, ElastiCache, và cả cluster MSK | `aws iam get-policy-version` trên `PowerUserAccess`: `Allow: * on Resource:*` | Ai cầm CI token hoặc lỡ tay apply sai là xoá sạch backup, không có rào chắn - vi phạm thẳng yêu cầu #5 của mandate | **Critical** | Chưa chốt | 2026-07-27 | REL-24: tách policy least-privilege cho role apply, cấm `Delete*Snapshot`/`DeleteBackup`/`DeleteCluster` |
| GAP-02 | MSK `techx-tf4-orders` (đang chạy thật) không có cơ chế backup nào - chỉ có retention/replication factor 2 | `infra/terraform/msk.tf`; MSK không có API snapshot/backup | Order event chưa kịp consume mà mất cluster là mất luôn, không restore lại được | **Critical** | Nguyên | 2026-07-27 | REL-25: chốt chiến lược lưu trữ lâu dài cho topic `orders` trong ADR RPO/RTO |
| GAP-03 | Chưa từng chạy restore drill nào (drop/xoá dữ liệu rồi restore lại) | Không có evidence drill nào trong repo | Chưa chứng minh được backup thật sự dùng được - đúng lỗi mandate cảnh báo | **Critical** | Chưa chốt | 2026-07-27 | REL-26: chạy drill thật, đo RTO, nộp evidence |
| GAP-04 | Chưa chốt RPO/RTO cho tầng dữ liệu nào | Chưa có ADR nào trong `mandate20/adr/` | Không có con số cam kết thì không biết cadence backup hiện tại (RDS/ElastiCache 7 ngày) là đủ hay thiếu | **High** | Nguyên | 2026-07-27 | REL-27: viết ADR RPO/RTO cho từng tầng dữ liệu |
| GAP-05 | Không có lịch snapshot tự động (AWS Backup/DLM) cho volume `opensearch`, `prometheus` | `grep` `infra/terraform/`: không có `aws_dlm_lifecycle_policy`/`aws_backup_plan` nào | Backup phụ thuộc vào việc ai đó nhớ chạy tay - dễ bị bỏ quên | **High** | Chưa chốt | 2026-07-27 | REL-28: tạo DLM/Backup plan cho volume observability |
| GAP-06 | PVC `opensearch-opensearch-0` chưa mã hoá + snapshot cũ hơn 7 ngày; PVC `prometheus` chưa có snapshot nào | Inventory §2 dòng 10-11 (CDO08-REL-20-stateful-store-inventory.md) | Ngoài luồng ra tiền, nhưng mất volume là mất log/trace/metric, không khôi phục được | **Medium** | Chưa chốt | 2026-07-27 | REL-29: bật mã hoá volume mới + gắn vào lịch backup ở GAP-05 |

Deadline lấy theo hạn chót của chính Mandate 20 (`MANDATE-20-dr-backup-restore.md`: "hoàn tất & nộp trước hết ngày 27/07/2026") - không tự đặt hạn riêng cho từng gap.

**Xác nhận:** 6 gap, mỗi gap có evidence/impact/deadline/task - không còn dòng "TBD" ở deadline/task. Owner nào chưa xác nhận được người cụ thể thì ghi "Chưa chốt" (vẫn có deadline/task đi kèm, không bỏ trôi). Toàn bộ store trong inventory ([CDO08-REL-20-stateful-store-inventory.md](CDO08-REL-20-stateful-store-inventory.md)) đã được phân loại (in-scope revenue path / out-of-scope / không tồn tại) - không có store nào bỏ ngỏ.

**Không lập gap cho các phần đã đạt chuẩn** (không cần sửa gì): RDS automated backup + PITR, ElastiCache automated snapshot, Terraform state (S3 + DynamoDB lock), ExternalSecrets/Secrets Manager, và repo GitOps (`tf4-phase3-gitops-manifests`, đã xác minh host trên GitHub, không phải single point of failure) - chi tiết ở inventory §3 (CDO08-REL-20-stateful-store-inventory.md).

**Thứ tự làm:** GAP-04 làm trước (chốt RPO/RTO), vì GAP-02/GAP-03 cần con số đó để biết "đủ" hay "thiếu". GAP-01 độc lập, làm ngay được.
