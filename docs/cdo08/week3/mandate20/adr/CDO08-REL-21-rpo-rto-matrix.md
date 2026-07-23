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
| RDS - schema `accounting` (sổ cái order) | Critical | 15 phút | 1 giờ | Doanh thu + audit trail, không được mất. RDS PITR restore theo giây trong vòng vài phút gần nhất - 15 phút RPO đạt được bằng cơ chế đang có sẵn, không cần thêm gì. **Sẽ tách sang 1 RDS instance riêng** (xem GAP-06), không còn chung với `catalog`/`reviews` - restore `accounting` sẽ không còn ảnh hưởng dữ liệu của 2 schema kia nữa | Bắt đầu: thời điểm dữ liệu bị mất/hỏng. Kết thúc RPO: timestamp bản ghi cuối cùng khôi phục được so với thời điểm sự cố. Kết thúc RTO: `accounting` service query DB thành công + qua integrity check |
| MSK - topic `orders` (event đơn hàng đang xử lý) | Critical | 15 phút | 2 giờ (dựng lại cluster/connector + trỏ lại endpoint) | MSK Connect + S3 Sink Connector, archival liên tục topic `orders` ra S3 - RPO 15 phút khớp chu kỳ flush connector (xem GAP-02) | Bắt đầu: cluster báo unavailable. Kết thúc: cluster mới dựng xong, replay lại message từ S3 archive vào `accounting`, xác nhận không thiếu đơn hàng nào |
| ElastiCache - `valkey-cart` (giỏ hàng) | Reconstructable | Không cam kết (chấp nhận mất toàn bộ) | 30 phút (thời gian dựng replication group mới) | Dữ liệu tự hết hạn sau 60 phút, khách tự thêm lại được - backup chặt không cải thiện outcome thực tế | Bắt đầu: cache unavailable. Kết thúc: `cart` đọc/ghi lại bình thường |
| RDS - schema `catalog` (seed sản phẩm) | Reconstructable | N/A | ~10-15 phút (thời gian deploy lại chart) | Static seed data từ `postgresql/init.sql`, không bị ghi runtime, tái tạo từ git/Helm. **Vẫn ở chung instance cũ với `reviews`** - không sao vì cả 2 đều không critical | Bắt đầu: phát hiện catalog rỗng/sai. Kết thúc: chart sync xong, `product-catalog` trả đúng data |
| RDS - schema `reviews` (product-reviews) | Important | 1 giờ | 2 giờ | Business data đọc/ghi thật nhưng ngoài luồng ra tiền - nới hơn `accounting`. **Ở lại instance cũ chung với `catalog`** sau khi `accounting` tách đi (xem GAP-06) - restore chung với `catalog` không sao vì cả 2 đều không critical | Cùng cơ chế PITR, đo riêng cho instance `catalog`+`reviews` (đã tách khỏi `accounting`) |
| Terraform state (S3 + DynamoDB lock) | Infrastructure | ~0 (S3 versioning giữ mọi version) | Đã đạt - không cần thêm việc | Đã bền vững sẵn, xem inventory §3 | N/A |
| Repo GitOps `tf4-phase3-gitops-manifests` | Infrastructure | ~0 (host GitHub, có lịch sử) | ~15-30 phút (re-bootstrap ArgoCD root app) | Đã xác minh bền vững, không phải single point of failure | Bắt đầu: cluster cần dựng lại từ đầu. Kết thúc: ArgoCD sync xong toàn bộ Application |

## Ghi chú cho người ký ADR

- Số RPO/RTO ở trên là **đề xuất dựa trên khả năng thực tế của cơ chế backup hiện có** (xem inventory), không phải số đã được business duyệt. Cần Hải/owner dữ liệu xác nhận trước khi chốt chính thức.
- Quyết định cho MSK `orders` và việc tách RDS instance: xem gap register (GAP-02, GAP-06).
- **Số trong matrix này là target ban đầu, chưa phải số đã đo thật** - xem quy trình chốt số đầy đủ (draft → sửa gap → test → điều chỉnh → ký) tại [CDO08-REL-21-REVIEW-REQUEST-RPO-RTO-PROCESS.md](../review-requests/CDO08-REL-21-REVIEW-REQUEST-RPO-RTO-PROCESS.md).

## Nguồn tham khảo cho cách đặt số

> Đã tự vào đọc trực tiếp từng trang bên dưới để xác minh (không chỉ dựa vào công cụ search) - bạn bấm link vào đọc lại được toàn bộ.

**Nguồn 1 - AWS Well-Architected Framework, Reliability Pillar, mục REL13-BP02**
Link: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_for_recovery_disaster_recovery.html

Nguyên văn tiếng Anh (copy chính xác từ trang, không diễn giải):
> "Backup and restore (RPO in hours, RTO in 24 hours or less): Back up your data and applications into the recovery Region. Using automated or continuous backups will permit point in time recovery (PITR), which can lower RPO to as low as 5 minutes in some cases."

Dịch: *"Backup và restore (RPO tính bằng giờ, RTO trong vòng 24 giờ hoặc ít hơn): Backup dữ liệu và ứng dụng vào region khôi phục. Dùng backup tự động hoặc liên tục sẽ cho phép point-in-time recovery (PITR), có thể hạ RPO xuống thấp tới 5 phút trong một số trường hợp."*

Áp vào hệ mình: chiến lược mình đang dùng (RDS point-in-time restore ra instance mới) chính là tier **"Backup and Restore"** mà AWS mô tả. Baseline mặc định của tier này là RPO tính bằng **giờ**, RTO có thể tới **24 giờ** - nhưng vì mình có PITR nên AWS xác nhận RPO có thể siết xuống **~5 phút**. Đây là lý do đề xuất RPO 15 phút cho `accounting` (an toàn hơn mức tối thiểu 5 phút AWS ghi, chưa đo thật nên chưa dám hứa sát mức 5 phút).

**Sửa lại so với bản trước:** trước tôi viết "Backup and Restore = RTO/RPO tính bằng giờ" - **không chính xác**, đúng ra là **RPO tính bằng giờ, RTO tới 24 giờ** (RTO nới hơn RPO nhiều). Bảng đề xuất 1 giờ RTO cho `accounting` vẫn hợp lý vì nó **chặt hơn** mức 24 giờ AWS coi là bình thường cho tier này - tức mình đang tự đặt mục tiêu khó hơn baseline, không phải copy nguyên baseline.

**Nguồn 2 - AWS Well-Architected, "Back up data"**
Link: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/back-up-data.html

Nguyên văn: *"Back up data, applications, and configuration to meet requirements for recovery time objectives (RTO) and recovery point objectives (RPO)."*

Dịch: *"Backup dữ liệu, ứng dụng và cấu hình để đáp ứng yêu cầu RTO/RPO."* Trang này dẫn tới mục con **"REL09-BP04 Perform periodic recovery of the data to verify backup integrity and processes"** (khôi phục dữ liệu định kỳ để xác minh backup toàn vẹn) - đây chính là AWS yêu cầu **phải test restore định kỳ**, xác nhận backup không chỉ để "bật lên rồi thôi", khớp với lý do matrix này chỉ là target, cần drill thật (REL-26) mới xác nhận được.

> *Đính chính:* bản trước tôi trích 1 câu ("Regular, automated restoration tests with actual RTO/RPO metrics are essential") mà **thực tế không có trên trang này** - đó là câu tóm tắt của công cụ search, không phải nguyên văn. Đã sửa lại bằng câu thật + tên mục con thật ở trên.

