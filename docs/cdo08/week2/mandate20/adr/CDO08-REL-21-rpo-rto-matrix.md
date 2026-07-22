# CDO08-REL-21 - RPO/RTO Matrix (Draft)

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20, yêu cầu #2
**Subtask:** "Đặt con số RPO/RTO đo được cho từng store"
**Trạng thái:** **Draft - đề xuất ban đầu.** Nguyên sẽ research thêm và chỉnh số trước khi đưa vào ADR ký chính thức ([CDO08-REL-21-adr-draft.md](CDO08-REL-21-adr-draft.md)).
**Input:** [CDO08-REL-20-revenue-path-dependency-trace.md](../scan/CDO08-REL-20-revenue-path-dependency-trace.md) (phân loại criticality), [CDO08-REL-20-stateful-store-inventory.md](../scan/CDO08-REL-20-stateful-store-inventory.md) (cơ chế backup hiện có)

---

## Phân tầng

- **Critical** - mất là mất tiền/audit trail thật, không tái tạo được.
- **Important** - dữ liệu đọc/ghi thật nhưng ngoài luồng ra tiền, chấp nhận RPO/RTO nới hơn.
- **Reconstructable** - tái tạo được từ nguồn khác (git, seed data, hoặc khách tự làm lại), không cần backup chặt.

## Matrix

| Store / miền dữ liệu | Tầng | RPO đề xuất | RTO đề xuất | Rationale | Đo bắt đầu / kết thúc |
|---|---|---|---|---|---|
| RDS - schema `accounting` (sổ cái order) | Critical | 15 phút | 1 giờ | Doanh thu + audit trail, không được mất. RDS PITR restore theo giây trong vòng vài phút gần nhất - 15 phút RPO đạt được bằng cơ chế đang có sẵn, không cần thêm gì | Bắt đầu: thời điểm dữ liệu bị mất/hỏng. Kết thúc RPO: timestamp bản ghi cuối cùng khôi phục được so với thời điểm sự cố. Kết thúc RTO: `accounting` service query DB thành công + qua integrity check |
| MSK - topic `orders` (event đơn hàng đang xử lý) | Critical | Best-effort (chấp nhận rủi ro, ghi rõ trong ADR) | 2 giờ (dựng lại cluster + trỏ lại endpoint) | Hiện không có cơ chế backup nào (GAP-02). Muốn RPO chặt phải thêm archival ra S3 - việc đó ngoài scope task này, ADR sẽ ghi nhận là rủi ro chấp nhận + đề xuất follow-up riêng | Bắt đầu: cluster báo unavailable. Kết thúc: cluster mới nhận lại message, checkout produce/consume thông suốt |
| ElastiCache - `valkey-cart` (giỏ hàng) | Reconstructable | Không cam kết (chấp nhận mất toàn bộ) | 30 phút (thời gian dựng replication group mới) | Dữ liệu tự hết hạn sau 60 phút, khách tự thêm lại được - backup chặt không cải thiện outcome thực tế | Bắt đầu: cache unavailable. Kết thúc: `cart` đọc/ghi lại bình thường |
| RDS - schema `catalog` (seed sản phẩm) | Reconstructable | N/A | ~10-15 phút (thời gian deploy lại chart) | Static seed data từ `postgresql/init.sql`, không bị ghi runtime, tái tạo từ git/Helm | Bắt đầu: phát hiện catalog rỗng/sai. Kết thúc: chart sync xong, `product-catalog` trả đúng data |
| RDS - schema `reviews` (product-reviews) | Important | 1 giờ | 2 giờ | Business data đọc/ghi thật nhưng ngoài luồng ra tiền - nới hơn `accounting` dù chung 1 instance | Cùng cơ chế PITR như `accounting` (chung instance), nhưng ưu tiên khôi phục `accounting` trước nếu phải chọn |
| Terraform state (S3 + DynamoDB lock) | Infrastructure | ~0 (S3 versioning giữ mọi version) | Đã đạt - không cần thêm việc | Đã bền vững sẵn, xem inventory §3 | N/A |
| Repo GitOps `tf4-phase3-gitops-manifests` | Infrastructure | ~0 (host GitHub, có lịch sử) | ~15-30 phút (re-bootstrap ArgoCD root app) | Đã xác minh bền vững, không phải single point of failure | Bắt đầu: cluster cần dựng lại từ đầu. Kết thúc: ArgoCD sync xong toàn bộ Application |

## Ghi chú cho người ký ADR

- Số RPO/RTO ở trên là **đề xuất dựa trên khả năng thực tế của cơ chế backup hiện có** (xem inventory), không phải số đã được business duyệt. Cần Hải/owner dữ liệu xác nhận mức chấp nhận rủi ro trước khi chốt, nhất là dòng MSK `orders` (hiện chưa có cách nào bảo vệ chặt).
- RDS `accounting` và `reviews` dùng chung 1 instance vật lý - restore 1 schema về 1 mốc thời gian sẽ ảnh hưởng cả 2 schema cùng lúc. Cần quyết định: có tách instance riêng cho `accounting` không, hay chấp nhận restore chung.
