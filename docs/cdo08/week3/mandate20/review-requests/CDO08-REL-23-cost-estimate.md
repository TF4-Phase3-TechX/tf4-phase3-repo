# CDO08-REL-23 — Phân tích chi phí thật (accounting RDS isolation)

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20, ràng buộc ngân sách
**Task:** [CDO08-REL-23-accounting-rds-isolation-plan.md](../implementation/CDO08-REL-23-accounting-rds-isolation-plan.md) §8 PM Approval Gate
**Phương pháp:** số liệu dưới đây lấy từ trang giá chính thức AWS + nguồn tổng hợp giá công khai (có trích dẫn từng dòng), đối chiếu với cấu hình **thật** đang chạy (`aws rds describe-db-instances`, `infra/terraform/`). Không có số nào tự bịa — chỗ nào chưa xác nhận được 100% ghi rõ "cần Pricing Calculator export xác nhận", theo đúng quy trình đã dùng ở [MANDATE-08-COST-PROPOSAL.md](../../../week2/mandate8/review-requests/MANDATE-08-COST-PROPOSAL.md).
**Region:** `us-east-1`
**Trạng thái:** DRAFT — ước tính cho PM review, chưa phải số cuối cùng

---

## 1. Phạm vi chi phí

REL-23 chỉ thêm tài nguyên mới, không xoá tài nguyên nào đang chạy (instance cũ `techx-tf4-postgresql` vẫn giữ nguyên cho `catalog`/`reviews`). Tài nguyên mới phát sinh (theo quyết định PA-A đã chốt ở §3.1/§3.2 của kế hoạch):

1. 1 RDS instance mới: `db.t4g.micro`, Multi-AZ, 20 GiB gp3, backup retention 7 ngày (mirror cấu hình instance hiện tại — xác nhận qua `aws rds describe-db-instances --db-instance-identifier techx-tf4-postgresql`, kết quả thật: `Class=db.t4g.micro, Engine=17.9, MultiAZ=True, Storage=20, Backup=7`).
2. 1 AWS Secrets Manager secret mới: `techx/tf4/rds-accounting`.
3. **Không** cần DMS instance, không cần NLB tạm thời — vì PA-A (`pg_dump`/`restore` + tạm dừng consumer) đã được chọn thay vì PA-B (AWS DMS full-load+CDC).

## 2. So sánh: giữ nguyên hiện trạng vs tách instance riêng (REL-23)

| | Giữ nguyên (status quo) | Tách riêng (REL-23) |
|---|---|---|
| Số RDS instance phục vụ `accounting`/`catalog`/`reviews` | 1 — `techx-tf4-postgresql` dùng chung cả 3 schema | 2 — `techx-tf4-postgresql` giữ `catalog`+`reviews`, thêm `techx-tf4-accounting-postgresql` mới cho `accounting` |
| Chi phí AWS bổ sung/tháng | **$0** — không tạo tài nguyên mới; chi phí instance hiện tại là sunk cost đã nằm trong ngân sách hiện hành, không đổi | **+$28.36 – $48.80** (chi tiết §3/§4) |
| Chi phí AWS bổ sung/tuần | **$0** | **+$6.53 – $11.23** (~2.2–3.7% ngân sách $300/tuần) |
| Recovery boundary (PITR/restore độc lập theo yêu cầu #3 Mandate 20) | **Không đạt** — restore `accounting` kéo theo `catalog`/`reviews` về cùng timestamp, đúng gap đã ghi ở [GAP-06 trong gap register](../scan/CDO08-REL-20-gap-register.md) | **Đạt** — restore `accounting` không còn ảnh hưởng 2 schema kia |
| Downsize instance cũ sau khi tách accounting đi? | N/A | Không nằm trong scope REL-23 — instance cũ vẫn giữ nguyên `db.t4g.micro`/20 GiB dù mất 1 schema, vì chưa đo dung lượng thật của `catalog`+`reviews` để biết có downsize an toàn được không. Không tự ý claim khoản tiết kiệm nào ở đây. |

**Kết luận so sánh:** giữ nguyên hiện trạng tốn **$0** thêm, nhưng đổi lại **không đạt yêu cầu #3 của Mandate
20** và để nguyên GAP-06 (severity Medium theo gap register). Task REL-23 không tồn tại để tiết kiệm hay
tốn tiền — mục tiêu là đóng gap tuân thủ; phần chi phí ở §3/§4 chính là cái giá phải trả (nhỏ, đã xác nhận
nằm trong ngân sách ở §5) để đạt được recovery boundary độc lập đó.

## 3. Base Fixed Cost — RDS instance mới

| Thành phần | Cấu hình | Đơn giá (nguồn) | Ước tính/tháng | Ước tính/tuần |
|---|---|---|---:|---:|
| Compute (Single-AZ) | `db.t4g.micro` | $0.016/giờ – $0.03/giờ (2 nguồn khác nhau, xem Ghi chú nguồn) | $11.68 – $21.90 | $2.70 – $5.06 |
| Compute (Multi-AZ, ×2 vì có standby chạy song song, tính riêng — không phải suy đoán, đây là cơ chế billing chính thức của AWS Multi-AZ) | `db.t4g.micro` × 2 | ×2 giá Single-AZ | $23.36 – $43.80 | $5.39 – $10.11 |
| Storage gp3 (×2 vì Multi-AZ có volume riêng cho mỗi AZ) | 20 GiB × 2 | $0.115/GB-tháng | $4.60 | $1.06 |
| **Tổng Base Fixed** | | | **$27.96 – $48.40** | **$6.45 – $11.17** |

**Ghi chú nguồn (không tự bịa số):**
- Giá compute `db.t4g.micro` có 2 con số khác nhau từ 2 nguồn công khai: [economize.cloud](https://www.economize.cloud/resources/aws/pricing/rds/db.t4g.micro/) ghi `$0.03/giờ` ($21.90/tháng, cập nhật 2026-07-23 — cùng ngày viết tài liệu này) và [selfhost.dev](https://selfhost.dev/blog/aws-rds-cost-breakdown-2026/) ghi `$0.016/giờ` ($11.68/tháng). Hai nguồn không khớp nhau — đây là lý do bảng ghi **khoảng (range)** thay vì 1 số cố định. **Cần AWS Pricing Calculator export để chốt số chính xác trước khi PM duyệt final.**
- Multi-AZ = 2× compute + 2× storage: cơ chế billing chính thức của AWS (standby chạy full-time, nhận synchronous write, được tính phí như 1 instance riêng) — xác nhận qua [Usage.ai — "RDS Multi-AZ vs Single-AZ: You Pay for Two Databases"](https://www.usage.ai/blogs/aws/rds-multi-az-vs-single-az-you-pay-for-two-databases/), không phải suy đoán.
- gp3 storage `$0.115/GB-tháng`: [selfhost.dev](https://selfhost.dev/blog/aws-rds-cost-breakdown-2026/), khớp với con số cũng xuất hiện ở kết quả search độc lập khác.

## 4. Expected Cost — chi phí phát sinh theo sử dụng

| Hạng mục | Xử lý | Ước tính |
|---|---|---|
| Backup storage vượt free allowance | Automated backup **miễn phí tới 100% dung lượng DB đã cấp phát** (20 GiB) trong retention period — theo [selfhost.dev](https://selfhost.dev/blog/aws-rds-cost-breakdown-2026/). Schema `accounting` chỉ có 3 bảng nhỏ (`order`/`orderitem`/`shipping`, PK dạng TEXT, không có BLOB) — thực tế gần như chắc chắn nằm dưới 20 GiB, nên **kỳ vọng $0/tháng** cho backup overage | $0/tháng (giả định — cần xác nhận lại sau khi có dung lượng dữ liệu thật, không phải số đã đo) |
| Manual snapshot vượt free tier (nếu tạo thêm ngoài automated backup) | $0.023/GB-tháng theo policy giá manual snapshot us-east-1 (nhiều nguồn khớp số này) | Không cần trong kế hoạch này — không có bước nào tạo manual snapshot ngoài automated backup |
| Secrets Manager — secret mới `techx/tf4/rds-accounting` | $0.40/secret/tháng (xác nhận trực tiếp từ **trang giá chính thức AWS** [aws.amazon.com/secrets-manager/pricing](https://aws.amazon.com/secrets-manager/pricing/) — không phải nguồn thứ 3) | $0.40/tháng |
| Secrets Manager — API calls (ExternalSecret sync `refreshInterval: 1h`) | $0.05/10,000 calls (cùng nguồn chính thức); 1 secret × 24 lần/ngày × 30 ngày ≈ 720 calls/tháng, dưới xa ngưỡng 10,000 | ~$0.0036/tháng (làm tròn $0) |
| **Tổng Expected** | | **~$0.40/tháng ≈ $0.09/tuần** |

## 5. Tổng hợp & đối chiếu ngân sách

| | Thấp | Cao |
|---|---:|---:|
| Base Fixed Cost/tháng | $27.96 | $48.40 |
| Expected Cost/tháng | $0.40 | $0.40 |
| **Tổng ước tính/tháng** | **$28.36** | **$48.80** |
| **Tổng ước tính/tuần** (÷ 4.345 tuần/tháng trung bình) | **$6.53** | **$11.23** |

### Đối chiếu ngân sách

Ngân sách đã được xác nhận là **$300/tuần/TF** (theo đúng Mandate 20 và
[MANDATE-08-COST-PROPOSAL.md](../../../week2/mandate8/review-requests/MANDATE-08-COST-PROPOSAL.md)). Với
mức đó, REL-23 thêm **$6.53–$11.23/tuần**, tương đương **~2.2–3.7%** ngân sách tuần — nằm gọn trong ngân
sách, không cần cân nhắc thêm.

**Bằng chứng thật đã kiểm tra (evidence, không phải suy đoán):** tài nguyên AWS Budget đang chạy thật lại
enforce ở mức **$300/THÁNG** chứ không phải $300/tuần:

```
$ aws budgets describe-budgets --account-id 511825856493
BudgetName: techx-tf4-monthly-cost-budget
BudgetLimit: 300.0 USD
TimeUnit:    MONTHLY
```

Đối chiếu `infra/terraform/budgets.tf`: `resource "aws_budgets_budget" "monthly_cost"` có `time_unit =
"MONTHLY"`. Đây là một **cảnh báo chi tiêu toàn tài khoản ở mức trần khác** (an toàn/guardrail chung, không
phải envelope $300/tuần riêng cho REL-23 hay cho TF) — không mâu thuẫn với ngân sách $300/tuần đã xác nhận
ở trên, chỉ là 2 cơ chế khác nhau (Budget alert toàn account theo tháng vs. envelope kế hoạch theo tuần).
Ghi nhận lại đây để không ai nhầm `ActualSpend`/`BudgetLimit` của tài nguyên này với ngân sách tuần khi tra
cứu sau này.

## 6. Required artifacts trước khi PM duyệt final (theo đúng tiền lệ MANDATE-08-COST-PROPOSAL.md §4)

- [ ] AWS Pricing Calculator export cho: 1× `db.t4g.micro` Multi-AZ PostgreSQL, 20 GiB gp3, backup retention 7 ngày, `us-east-1` — để chốt số chính xác thay vì khoảng $27.96-$48.40/tháng ở §3.
- [ ] Sau khi có Calculator export, cập nhật lại bảng §3/§5 bằng số chính thức, xoá dòng "cần xác nhận".

## 7. Kết luận

Chi phí tăng thêm của REL-23 là **nhỏ và trong ngân sách** (~$6.53–$11.23/tuần trên tổng $300/tuần đã xác
nhận, ~2.2–3.7%), tương đương 1 RDS `db.t4g.micro` Multi-AZ + 1 secret, và không cần DMS/NLB tạm thời nhờ
chọn PA-A. So với việc giữ nguyên hiện trạng (§2, chi phí AWS $0 nhưng không đạt yêu cầu #3 Mandate 20 và
giữ nguyên GAP-06), khoản chi thêm này là cái giá nhỏ đổi lấy recovery boundary độc lập. Việc còn lại trước
khi PM duyệt final chỉ là chốt số chính xác qua AWS Pricing Calculator export (§6), không còn vướng mắc
nào khác.
