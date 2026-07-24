# CDO08-REL-27 — Mandate 20 Requirement-to-Evidence Matrix

| Thuộc tính | Giá trị |
|---|---|
| Task | CDO08-REL-27 — Map Mandate 20 requirements to timestamped evidence |
| Owner | Hải (PM) + Nguyên (Tech Lead) |
| Phạm vi | Requirement #1–#5 của Mandate 20 |
| Đánh giá tại | 2026-07-24 UTC |
| Account/Region runtime đã ghi nhận | `511825856493` / `us-east-1` |
| Evidence pack root | `docs/cdo08/week3/` |

## 1. Quy ước verdict

- `PASS`: evidence hiện có chứng minh đầy đủ acceptance criteria.
- `PARTIAL`: một số control con đạt nhưng requirement tổng chưa đạt.
- `FAIL`: có gap đã xác nhận hoặc evidence bắt buộc chưa tồn tại.
- `NOT RUN`: hoạt động runtime/drill chưa được thực hiện; khi tổng hợp Mandate được xem là chưa đạt.

Không dùng migration, cấu hình IaC hoặc ảnh “backup enabled” để thay thế cho PITR/restore drill. Timestamp trong cột evidence là thời điểm hoạt động được tài liệu ghi nhận; nếu tài liệu không ghi thời điểm runtime cụ thể thì dùng `Not recorded` và không nâng verdict thành PASS dựa trên timestamp file.

## 2. Ma trận tổng quan

| Requirement Mandate 20 | Kết quả | Evidence chính | Gap để PASS | Owner |
|---|---|---|---|---|
| #1 — Inventory đầy đủ mọi stateful store và cluster state trên revenue path | **PASS** | Inventory và dependency trace | Xác minh lại runtime nếu có resource tạo ngoài Terraform | Nguyên |
| #2 — Signed target RPO/RTO và backup/drill cadence tương xứng | **FAIL** | ADR/RPO-RTO matrix đang Draft | Chốt target, cadence và chữ ký Hải + Nguyên | Hải + Nguyên |
| #3 — Point-in-time restore về trước sự cố, trong môi trường cô lập | **NOT RUN** | RDS có PITR 7 ngày; chưa có PITR execution evidence | Chạy isolated PITR drill, lưu command/output/timeline | Nguyên + DB Operator |
| #4 — Witnessed destructive restore/replay drill và đo actual RPO/RTO | **NOT RUN** | Runbook đã có; chưa có witnessed drill result | Thực hiện drill, validation, cleanup, witness và actual results | Hải + Nguyên |
| #5 — Encryption, retention và deletion separation | **PARTIAL / FAIL** | Encryption/retention có; deletion separation có gap | Negative-delete test phải `AccessDenied`, chốt delete approver | Security + Nguyên |

**Overall Mandate 20 verdict tại 2026-07-24:** **FAIL / NOT READY TO CLOSE**. Requirement #2, #3, #4 và phần deletion separation của #5 chưa có evidence đạt.

## 3. Requirement #1 — Inventory đầy đủ

| Control/evidence | Path | Evidence timestamp | Context | Kết quả | Ghi chú |
|---|---|---|---|---|---|
| Revenue-path dependency trace | [`../week2/mandate20/scan/CDO08-REL-20-revenue-path-dependency-trace.md`](../week2/mandate20/scan/CDO08-REL-20-revenue-path-dependency-trace.md) | Not recorded | Browse → cart → checkout; app/store/infra dependencies | **PASS** | Xác định phạm vi store cần backup/rebuild. |
| Stateful-store inventory | [`../week2/mandate20/scan/CDO08-REL-20-stateful-store-inventory.md`](../week2/mandate20/scan/CDO08-REL-20-stateful-store-inventory.md) | Runtime observations `2026-07-19`–`2026-07-21` | RDS, ElastiCache, MSK, S3/DynamoDB Terraform state, GitOps, Secrets Manager, PVC | **PASS** | Inventory ghi cả resource trong và ngoài revenue path, owner, backup/restore/encryption và gap. |
| Inventory/gap summary | [`../week2/mandate20/scan/CDO08-REL-20-summary.md`](../week2/mandate20/scan/CDO08-REL-20-summary.md) | Not recorded | Mandate 20 scan | **PASS** | Dùng làm entry point; evidence chi tiết nằm trong inventory/gap register. |
| Runtime account/region for managed PostgreSQL | [`../week2/mandate8/evidence/REL-15-postgresql-restore-evidence.md`](../week2/mandate8/evidence/REL-15-postgresql-restore-evidence.md) | Artifact `postgresql-schema-20260720-124528.sql`; runtime evidence ngày `2026-07-20` | Account `511825856493`, `us-east-1`, RDS `techx-tf4-postgresql`, DB `otel` | **PASS** | Xác nhận runtime context của shared RDS và schemas `accounting`, `catalog`, `reviews`. |
| MSK runtime cutover inventory | [`../week2/mandate8/evidence/REL-17-kafka-msk-cutover-evidence.md`](../week2/mandate8/evidence/REL-17-kafka-msk-cutover-evidence.md) | `2026-07-22 ICT` | MSK-backed checkout, accounting, fraud-detection; namespace `techx-tf4` | **PASS** | Chứng minh MSK là runtime event path; không chứng minh backup/replay. |

**Requirement #1 verdict:** **PASS**, với residual caveat: inventory dựa trên IaC và quyền read-only có giới hạn; resource tạo tay ngoài Terraform cần được query lại bằng inventory role trước final sign-off.

## 4. Requirement #2 — Signed RPO/RTO/cadence

| Control/evidence | Path | Evidence timestamp | Context | Kết quả | Ghi chú |
|---|---|---|---|---|---|
| ADR target RPO/RTO, cadence, retention | [`../week2/mandate20/adr/CDO08-REL-21-adr-draft.md`](../week2/mandate20/adr/CDO08-REL-21-adr-draft.md) | Not recorded | RDS accounting/catalog/reviews, MSK orders, Valkey cart | **FAIL** | File ghi rõ `DRAFT - CHƯA KÝ`; target vẫn là đề xuất. |
| RPO/RTO matrix | [`../week2/mandate20/adr/CDO08-REL-21-rpo-rto-matrix.md`](../week2/mandate20/adr/CDO08-REL-21-rpo-rto-matrix.md) | Not recorded | Target theo data tier | **FAIL** | Chưa phải commitment được Hải và Nguyên ký. |
| Backup cadence/retention matrix | [`../week2/mandate20/adr/CDO08-REL-21-backup-policy-matrix.md`](../week2/mandate20/adr/CDO08-REL-21-backup-policy-matrix.md) | Not recorded | RDS, Valkey, MSK/S3 | **PARTIAL** | RDS/Valkey hiện có cadence; MSK S3 archival vẫn là đề xuất/gap. |
| Review/sign-off request | [`../week2/mandate20/review-requests/CDO08-REL-21-REVIEW-REQUEST-RPO-RTO-PROCESS.md`](../week2/mandate20/review-requests/CDO08-REL-21-REVIEW-REQUEST-RPO-RTO-PROCESS.md) | Not recorded | PM/Tech Lead approval process | **FAIL** | Có quy trình review nhưng chưa có chữ ký/timestamp approval. |

**Requirement #2 verdict:** **FAIL**. Điều kiện PASS: target nằm trong ADR ở trạng thái signed, có tên và UTC timestamp của Hải/Nguyên; backup và drill cadence đủ đạt target. Actual result về sau phải nằm cột riêng, không được sửa target đã ký.

## 5. Requirement #3 — PITR evidence

| Control/evidence | Path | Evidence timestamp | Context | Kết quả | Ghi chú |
|---|---|---|---|---|---|
| RDS automated backup/PITR configuration | [`../../../infra/terraform/rds.tf`](../../../infra/terraform/rds.tf) | Repository state evaluated `2026-07-24` | `techx-tf4-postgresql`; retention `7`; backup window `18:00-19:00 UTC`; encrypted/private | **PASS** | Chứng minh implementation/configuration, không chứng minh restore. |
| Live PITR/backup inventory | [`../week2/mandate20/scan/CDO08-REL-20-stateful-store-inventory.md`](../week2/mandate20/scan/CDO08-REL-20-stateful-store-inventory.md) | Automated snapshots observed `2026-07-19`–`2026-07-21` | RDS `techx-tf4-postgresql` | **PASS** | Chứng minh PITR khả dụng/retention tại thời điểm scan. |
| Existing schema restore/DMS evidence | [`../week2/mandate8/evidence/REL-15-postgresql-restore-evidence.md`](../week2/mandate8/evidence/REL-15-postgresql-restore-evidence.md) | `2026-07-20` | Migration source → RDS target | **NOT APPLICABLE TO PITR** | Đây là schema restore + DMS full-load/CDC, không phải `restore-db-instance-to-point-in-time` về trước sự cố. |
| Isolated PITR execution evidence | Expected under `docs/cdo08/week3/evidence/<RUN_ID>/` | **Not available / NOT RUN** | Source RDS → isolated RDS restore | **NOT RUN** | Cần `02-rds-pitr-source.json`, `03-restore-events.json`, validation và cleanup output. |
| Executable PITR runbook | [`CDO08-REL-27-SHARED-RDS-PITR-ACCOUNTING-MSK-REPLAY-RUNBOOK.md`](CDO08-REL-27-SHARED-RDS-PITR-ACCOUNTING-MSK-REPLAY-RUNBOOK.md) | `2026-07-24` | Shared RDS accounting isolated restore | **PASS (documentation only)** | Đủ preflight, expected output, abort, cleanup; không thay execution evidence. |

**Requirement #3 verdict:** **NOT RUN**. PITR được cấu hình nhưng chưa có timestamped command/output chứng minh restore một điểm trước corruption sang instance cô lập.

## 6. Requirement #4 — Witnessed restore drill

| Control/evidence | Path | Evidence timestamp | Context | Kết quả | Ghi chú |
|---|---|---|---|---|---|
| Drill runbook | [`CDO08-REL-27-SHARED-RDS-PITR-ACCOUNTING-MSK-REPLAY-RUNBOOK.md`](CDO08-REL-27-SHARED-RDS-PITR-ACCOUNTING-MSK-REPLAY-RUNBOOK.md) | `2026-07-24` | Accounting PITR + MSK archive replay | **PASS (readiness document)** | Phân biệt drill/incident, automatic/manual, owner, abort, validation và cleanup. |
| Controlled corruption evidence | Expected under `docs/cdo08/week3/evidence/<RUN_ID>/` | **Not available / NOT RUN** | Isolated test data | **NOT RUN** | Cần before/after record IDs/checksum và exact UTC corruption time. |
| Witness and timeline | Expected `10-timeline.md` trong run evidence | **Not available / NOT RUN** | Hải/Nguyên hoặc mentor witness | **NOT RUN** | Cần T0, PITR, restore available, validation complete, witness names. |
| Actual RPO/RTO and validation report | Expected `09-accounting-validation-after.txt` và `12-verdict.md` | **Not available / NOT RUN** | RDS accounting; MSK/S3 replay nếu archive có | **NOT RUN** | Phải đo đến khi dữ liệu usable và validation PASS, không chỉ đến khi RDS `available`. |
| Cleanup evidence | Expected `11-cleanup.txt` | **Not available / NOT RUN** | Temporary RDS/topic/runner/secrets | **NOT RUN** | Cần resource IDs, delete output, source vẫn available và cost duration. |
| MSK runtime cutover | [`../week2/mandate8/evidence/REL-17-kafka-msk-cutover-evidence.md`](../week2/mandate8/evidence/REL-17-kafka-msk-cutover-evidence.md) | `2026-07-22 ICT` | Checkout/accounting/fraud on MSK | **NOT APPLICABLE TO REPLAY DRILL** | Chứng minh runtime flow/cutover, không chứng minh S3 archive/replay sau data loss. |

**Requirement #4 verdict:** **NOT RUN**. Runbook sẵn sàng nhưng chưa có controlled loss → restore/replay → integrity validation → actual RPO/RTO → cleanup được witness.

## 7. Requirement #5 — Encryption, retention và deletion separation

| Control/evidence | Path | Evidence timestamp | Context | Kết quả | Ghi chú |
|---|---|---|---|---|---|
| RDS encryption/retention/deletion protection | [`../../../infra/terraform/rds.tf`](../../../infra/terraform/rds.tf) | Repository state evaluated `2026-07-24` | RDS `techx-tf4-postgresql` | **PASS** | `storage_encrypted=true`, retention 7 ngày, deletion protection, giữ automated backup/final snapshot. |
| MSK encryption | [`../../../infra/terraform/msk.tf`](../../../infra/terraform/msk.tf) | Repository state evaluated `2026-07-24` | MSK `techx-tf4-orders` | **PASS** | KMS at rest, TLS in transit; không có backup/archive retention trong file này. |
| PostgreSQL migration dump encryption/retention | [`../../../infra/terraform/postgresql-migration-backup.tf`](../../../infra/terraform/postgresql-migration-backup.tf) | Repository state evaluated `2026-07-24` | S3 migration backup bucket | **PASS (migration only)** | Versioning, SSE-S3 và lifecycle 7 ngày; one-time migration dump không phải periodic MSK/RDS DR archive. |
| MSK Connect/S3 archive encryption/retention | No repository evidence found at `2026-07-24` | **Not available** | Orders archive | **FAIL** | Chưa có connector/bucket/archive contract để đánh giá encryption, cadence, retention hoặc replay. |
| Backup delete separation inventory | [`../week2/mandate20/scan/CDO08-REL-20-stateful-store-inventory.md`](../week2/mandate20/scan/CDO08-REL-20-stateful-store-inventory.md) | Runtime scan up to `2026-07-21` | CI/apply role `tf4-github-actions-terraform-apply` | **FAIL** | Inventory ghi role có thể xóa RDS/DynamoDB/EBS/ElastiCache backup và MSK cluster. |
| IAM negative-delete command/output | Expected under `docs/cdo08/week3/evidence/<RUN_ID>/` | **Not available / NOT RUN** | Normal operator role; protected backup/archive | **NOT RUN** | PASS chỉ khi delete attempt trả `AccessDenied` và privileged delete approver được ghi rõ. |

**Requirement #5 verdict:** **PARTIAL / FAIL**. Encryption và một số retention control đạt; MSK archive chưa tồn tại trong evidence và separation of duties/negative-delete chưa đạt.

## 8. Evidence còn phải thu để đổi verdict

| ID | Evidence cần bổ sung | Điều kiện chấp nhận | Dự kiến owner |
|---|---|---|---|
| E-01 | Signed ADR target RPO/RTO/cadence | Hải + Nguyên ký tên và UTC timestamp; target cố định | Hải + Nguyên |
| E-02 | RDS PITR source/restore output | Account/region/source/restore ID, selected PITR, private/encrypted instance | DB Operator |
| E-03 | Accounting validation | Tables, counts/checksums, FK, sequence, missing/duplicate PASS | DB + App Owner |
| E-04 | MSK Connect/S3 archival inventory | Connector RUNNING, topic/bucket/prefix/schema, encryption, cadence, retention | Streaming Operator |
| E-05 | Isolated replay evidence | Immutable manifest, range/partition/count reconciliation, lag 0, no unexplained duplicate/missing | Streaming + App |
| E-06 | Witnessed drill timeline | Controlled loss, restore/replay, actual RPO/RTO, witness and cleanup | Hải + Nguyên |
| E-07 | IAM negative-delete | Normal operator delete returns `AccessDenied`; delete approver documented | Security |
| E-08 | Final cleanup | Temporary RDS/topic/runner/secrets removed; source/archive unchanged | Recovery Lead |

Mọi evidence mới phải nằm dưới `docs/cdo08/week3/`, có UTC timestamp, account/region/cluster context, raw command/output hoặc link tới immutable artifact, owner và verdict. Mọi FAIL phải được đưa vào remediation backlog của Subtask 4; không được xóa dòng FAIL để đóng Mandate.

## 9. Reviewer sign-off cho matrix

| Vai trò | Tên | Verdict review | UTC timestamp | Chữ ký/comment |
|---|---|---|---|---|
| PM | Hải | Pending |  |  |
| Tech Lead | Nguyên | Pending |  |  |
| Mentor/Witness |  | Pending |  |  |
