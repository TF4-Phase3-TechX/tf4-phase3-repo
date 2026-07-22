# Mandate 20 - DR / Backup & Restore - Giai đoạn Inventory (T1-T3)

**Directive:** [MANDATE-20-dr-backup-restore.md](../../../../mandates/MANDATE-20-dr-backup-restore.md)
**Owner:** Nguyên (Techlead) / phối hợp PM Hải và các owner dữ liệu
**Giai đoạn:** Chỉ mới làm phần inventory (subtask T1-T3). ADR RPO/RTO và restore drill thật (yêu cầu #2-#4 của mandate) là việc tiếp theo, chưa nằm trong tài liệu này - xem gap register để biết task ID theo dõi.

Toàn bộ research đều read-only: `kubectl get/describe`, `aws ...describe-*/list-*`, đọc `infra/terraform/`, `techx-corp-chart/`, `techx-corp-platform/src/`. Không có tài nguyên nào bị tạo/sửa/xoá.

## Danh sách tài liệu

| Tài liệu | Nội dung | Ứng với |
|---|---|---|
| [CDO08-REL-20-revenue-path-dependency-trace.md](scan/CDO08-REL-20-revenue-path-dependency-trace.md) | Trace service -> dependency -> dữ liệu -> mức độ quan trọng của luồng browse -> cart -> checkout -> payment -> order -> async event. Xác nhận store nào thực sự tồn tại. | Subtask T1 |
| [CDO08-REL-20-stateful-store-inventory.md](scan/CDO08-REL-20-stateful-store-inventory.md) | Inventory đầy đủ RDS, ElastiCache, MSK, Terraform state, ArgoCD, ExternalSecrets, và quyền IAM liên quan xoá backup. Mỗi dòng có owner, cơ chế backup, trạng thái, phương thức restore, tình trạng mã hoá. | Subtask T2 |
| [CDO08-REL-20-gap-register.md](scan/CDO08-REL-20-gap-register.md) | 6 gap xếp theo severity, mỗi gap có evidence, impact, owner, deadline, task theo dõi. | Subtask T3 |

## Phát hiện chính

- Hệ thống đã cutover xong sang managed service: `product-catalog`/`accounting` dùng **RDS PostgreSQL**, `cart` dùng **ElastiCache Valkey**, `checkout`/`accounting`/`fraud-detection` dùng **MSK Kafka**. Không còn service self-hosted nào chạy trong cluster.
- **DynamoDB không mang dữ liệu ứng dụng nào** - xác nhận qua rà soát Terraform/chart/source.
- **Repo GitOps riêng (`tf4-phase3-gitops-manifests`) đã được kiểm tra trực tiếp** - host trên GitHub thật, có branch/lịch sử riêng, khai báo đúng các Application/ExternalSecret khớp với cluster đang chạy - không phải single point of failure.
- 3 gap Critical: role CI apply có thể xoá bất kỳ backup RDS/DynamoDB/EC2/ElastiCache nào hoặc cả cluster MSK (GAP-01), MSK không có cơ chế backup nào cho topic `orders` (GAP-02), và chưa từng chạy restore drill nào (GAP-03).
- Các khu vực đã đạt chuẩn (RDS automated backup/PITR, ElastiCache automated snapshot, Terraform state, ExternalSecrets) được ghi rõ để không lên kế hoạch làm trùng.

## Checklist Definition of Done (để mentor kiểm tra)

- [x] Không sót thành phần stateful trên revenue path - trace §6 + inventory §2.
- [x] Mỗi store có owner và phương thức khôi phục dự kiến - inventory §2, cột "Owner" và "Phương thức restore".
- [x] Inventory đối chiếu với runtime, IaC/GitOps và cấu hình ứng dụng - trace dẫn evidence từ source/manifest/kubectl live; inventory dẫn output `aws`/`kubectl` thật, đối chiếu `infra/terraform/*.tf`.
- [x] Gap register: mỗi gap có evidence, impact, owner, task xử lý; không có "TBD" - xem gap register.
- [ ] ADR RPO/RTO, restore drill thật, xử lý phân quyền backup - chưa làm, theo dõi ở REL-24 đến REL-29 trong gap register.
