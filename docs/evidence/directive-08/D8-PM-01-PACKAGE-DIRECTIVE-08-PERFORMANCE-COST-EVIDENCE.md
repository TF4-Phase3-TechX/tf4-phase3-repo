# [D8-PM-01] Gói bằng chứng Performance và Cost cho Mentor - Directive 8

> **Directive:** #8 - Di trú sang managed data services không downtime  
> **Phạm vi:** Gói evidence CDO-04 cho PostgreSQL -> RDS, Valkey -> ElastiCache, Kafka -> MSK  
> **Thời điểm đóng gói:** 2026-07-25T00:00:00+07:00  
> **Namespace chính:** `techx-tf4`  
> **AWS Region:** `us-east-1`  
> **AWS Account:** `511825856493`  
> **Verdict gói tài liệu:** **PASS - đề xuất Mentor ký nghiệm thu**

## 1. Kết luận tổng quan

Gói D8-PM-01 gom bằng chứng hiệu năng, chi phí, cutover, đối soát dữ liệu, cleanup EKS và rollback cho Directive #8. Mục tiêu là giúp mentor tự mở từng artifact và xác minh trạng thái migration từ data services tự vận hành trên EKS sang AWS managed services.

Trạng thái đích đã được ghi nhận:

- Traffic PostgreSQL của application đã dùng Amazon RDS PostgreSQL.
- Luồng cart/checkout cache đã dùng Amazon ElastiCache for Valkey.
- Checkout producer và các consumer downstream đã dùng Amazon MSK.
- PostgreSQL, Valkey và Kafka self-hosted không còn phục vụ traffic runtime.
- Secret được tham chiếu qua AWS Secrets Manager, External Secrets và Kubernetes Secret contract; không đưa plaintext credential vào evidence.

## 2. Mục lục evidence

| Nhóm evidence | Artifact / nguồn | Timestamp / ghi chú nguồn |
|---|---|---|
| Baseline trước migration | [01-pre-migration-baseline.md](file:///d:/tf4-phase3-repo/docs/evidence/directive-08/01-pre-migration-baseline.md) | Baseline run 200 users ngày 2026-07-19 |
| Raw evidence baseline | [runs/baseline-200-users-20260719/](file:///d:/tf4-phase3-repo/docs/evidence/directive-08/runs/baseline-200-users-20260719/) | Locust raw files và ảnh Grafana/Locust |
| PR cost model | [PR #303](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/303) | Managed data services net cost model |
| README cost model | [D8-COST-01-managed-data-services-net-cost-model.md](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/codex/d8-cost-01-net-cost-model/docs/evidence/directive-08/cost/D8-COST-01-managed-data-services-net-cost-model.md) | Nguồn sizing và cost decision |
| Workbook chi phí | [D8-COST-01-managed-data-services-net-cost-model.xlsx](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/codex/d8-cost-01-net-cost-model/outputs/d8-cost-01/D8-COST-01-managed-data-services-net-cost-model.xlsx) | Workbook reconciliation |
| Ảnh tổng hợp chi phí | [Summary.png](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/codex/d8-cost-01-net-cost-model/outputs/d8-cost-01/Summary.png) | Tóm tắt trực quan cho mentor |
| Hợp đồng cutover | [D8-PERF-03-cutover-contract.md](performance/D8-PERF-03-cutover-contract.md) | Cổng kiểm soát zero-downtime, rollback và runbook cho mentor |
| Mục lục evidence cutover | [D8-PERF-03-evidence.md](performance/D8-PERF-03-evidence.md) | Câu lệnh CLI, screenshot plan và cách kiểm chứng |
| Hợp đồng cutover trên GitHub | [D8-PERF-03-cutover-contract.md trên branch](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/cdo04/week1/costquickwins/docs/evidence/directive-08/performance/D8-PERF-03-cutover-contract.md) | Nguồn review trên branch |
| Mục lục evidence trên GitHub | [D8-PERF-03-evidence.md trên branch](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/cdo04/week1/costquickwins/docs/evidence/directive-08/performance/D8-PERF-03-evidence.md) | Bản đồ kiểm chứng cho mentor |
| Managed infra handoff | [REL-14-managed-infra-handoff-evidence.md](../../cdo08/week2/mandate8/evidence/REL-14-managed-infra-handoff-evidence.md) | Cập nhật ngày 2026-07-19 |
| PostgreSQL parity | [REL-15-postgresql-parity-evidence.md](../../cdo08/week2/mandate8/evidence/REL-15-postgresql-parity-evidence.md) | Ghi nhận ngày 2026-07-21 |
| PostgreSQL RDS cutover | [REL-15-postgresql-rds-cutover-evidence.md](../../cdo08/week2/mandate8/evidence/REL-15-postgresql-rds-cutover-evidence.md) | Ghi nhận ngày 2026-07-21 |
| Valkey cart cutover | [CDO08-REL-16-cart-cutover-evidence.md](../../cdo08/week2/mandate8/evidence/CDO08-REL-16-cart-cutover-evidence.md) | Thực hiện ngày 2026-07-21 |
| Kafka MSK cutover | [REL-17-kafka-msk-cutover-evidence.md](../../cdo08/week2/mandate8/evidence/REL-17-kafka-msk-cutover-evidence.md) | Kiểm tra ngày 2026-07-22 ICT |
| Tổng hợp managed migration | [MANDATE-08-MANAGED-DATA-MIGRATION-EVIDENCE.md](../../cdo08/week2/mandate8/evidence/MANDATE-08-MANAGED-DATA-MIGRATION-EVIDENCE.md) | Kiểm tra 2026-07-22 10:02 ICT |
| Post-cutover regression | `docs/evidence/directive-08/performance/D8-PERF-05-post-cutover-regression.md` | 23 ảnh terminal, Locust UI và Grafana |
| EKS cleanup / capacity verification | [PR #487](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/487) | D8-COST-02 cleanup và capacity evidence |

## 3. Mapping trước / trong / sau

| Giai đoạn | Evidence | Trọng tâm mentor kiểm chứng |
|---|---|---|
| Trước migration | Baseline report và raw run folder ngày 2026-07-19 | Baseline tải người dùng, output Locust và ảnh Grafana |
| Sizing managed services | REL-14 handoff và D8-COST-01 model | Sizing RDS, ElastiCache, MSK và giả định chi phí |
| Chuẩn bị cutover | D8-PERF-03 contract và mục lục evidence | Cổng kiểm soát zero-downtime, điều kiện dừng và mapping owner |
| Trong migration | PostgreSQL DMS/parity, Valkey online migration, Kafka/MSK cutover | Replication, data parity, endpoint switch, app health |
| Sau cutover | Managed migration summary, post-cutover regression, cleanup PR | App dùng managed endpoints, SLO đạt, data-plane cũ đã rời runtime |

## 4. Sizing RDS / ElastiCache / MSK

| Store | Managed target | Sizing / cấu hình | Evidence |
|---|---|---|---|
| PostgreSQL | Amazon RDS PostgreSQL | Multi-AZ, `db.t4g.micro`, 20 GiB gp3, encrypted, private endpoint, backup retention 7 ngày | REL-14 handoff |
| Valkey cart | Amazon ElastiCache for Valkey | 2 node Multi-AZ, `cache.t4g.micro`, mã hóa at-rest, mã hóa in-transit, HA promotion tự động | REL-14 handoff |
| Kafka orders | Amazon MSK Provisioned | 2 broker, `kafka.t3.small`, 10 GiB EBS/broker, TLS/SASL-SCRAM, private subnets | REL-14 handoff |
| Migration | AWS DMS và bridge workload tạm thời | DMS tạm thời, MirrorMaker2 tạm thời trên EKS, NLB tạm thời chỉ dùng khi cần kỹ thuật | Cost proposal và cutover contract |

## 5. Bằng chứng managed endpoint

Package này không nhúng plaintext secret. Evidence chỉ dùng secret name, key name và endpoint đã mask hoặc endpoint không chứa credential.

| Component | Bằng chứng endpoint managed | Nguồn |
|---|---|---|
| RDS PostgreSQL | Workload dùng `rds-postgres-secret`; connection string của app trỏ tới `techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com:5432` | REL-15 RDS cutover evidence |
| ElastiCache Valkey | `cart` dùng `elasticache-valkey-secret` và runtime `VALKEY_ADDR`; key test cart xuất hiện trên ElastiCache, không xuất hiện trên `valkey-cart` cũ | REL-16 cart cutover evidence |
| MSK | `checkout`, `accounting`, `fraud-detection` dùng `msk-kafka-secret` với `SASL_SSL` / `SCRAM-SHA-512`; active checkout revision dùng cấu hình MSK | REL-17 MSK cutover evidence |

## 6. Data parity và kết quả cutover

| Data store | Kết quả parity / cutover | Evidence |
|---|---|---|
| PostgreSQL | Strict row-count parity đạt 5/5 bảng sau source write lock và CDC catch-up: `accounting.order`, `accounting.orderitem`, `accounting.shipping`, `catalog.products`, `reviews.productreviews` | REL-15 RDS cutover evidence |
| Valkey cart | Ghi cart mới được xác minh trên ElastiCache với TTL hợp lệ; cùng key không có trên `valkey-cart` cũ | REL-16 cart cutover evidence |
| Kafka orders | Checkout producer đã promote sang revision dùng MSK; `accounting` và `fraud-detection` tiếp tục consume order events | REL-17 MSK cutover evidence |

## 7. Post-cutover regression và SLO

Evidence post-cutover regression nằm tại:

```text
docs/evidence/directive-08/performance/D8-PERF-05-post-cutover-regression.md
```

Evidence ghi nhận 23 ảnh từ terminal, Locust UI và Grafana Dashboard. Verdict đề xuất: **PASS - Proposed for Approval**.

SLO nổi bật từ cutover evidence:

| Flow / component | Kết quả |
|---|---|
| Browse | 100.000% non-5xx sau khi PostgreSQL cutover ổn định |
| Cart | 100.000% success trên các request quan sát được của `GET /api/cart` và `POST /api/cart` trong Valkey evidence |
| Checkout | 100.000% success sau khi PostgreSQL cutover ổn định; Checkout producer healthy sau MSK promote |
| Storefront latency | p95 khoảng 40.2 ms sau stabilization trong PostgreSQL cutover evidence |

## 8. Evidence cleanup EKS

Runtime cleanup được tổng hợp trong `MANDATE-08-MANAGED-DATA-MIGRATION-EVIDENCE.md` và PR #487.

Kết quả mentor có thể kiểm chứng:

- Không còn pod/service `postgresql` phục vụ application traffic.
- Không còn pod/service `valkey-cart` phục vụ application traffic.
- Không còn pod/service `kafka` phục vụ application traffic.
- Không còn runtime service `orders-mirrormaker2` sau Kafka cleanup.
- PVC cũ được giữ có chủ đích cho rollback/data-retention trong observation window.

Câu lệnh kiểm chứng:

```powershell
kubectl -n techx-tf4 get pods
kubectl -n techx-tf4 get svc
kubectl -n techx-tf4 get pvc
kubectl -n argocd get application techx-corp
```

## 9. Cost decision và reconciliation

CDO04 đã review cost envelope cho managed data services và approve hướng triển khai theo các điều kiện được ghi trong `MANDATE-08-COST-PROPOSAL.md` và D8-COST-01.

Tóm tắt quyết định chi phí:

| Hạng mục | Quyết định |
|---|---|
| RDS Multi-AZ | Approved within weekly envelope |
| ElastiCache Valkey 2-node | Approved |
| MSK Provisioned 2 brokers | Approved |
| DMS | Approved as temporary migration resource |
| MirrorMaker2 | Workload tạm thời, không có AWS managed service fee riêng; theo dõi qua EKS/transfer/log overhead |
| Temporary NLB | Approved only when technically required |

Envelope đã được duyệt:

| Cost envelope | Trần chi phí |
|---|---:|
| Base fixed cost | `<= $30/week` |
| Expected operating cost | `<= $35/week` |
| Recurring guardrail cost | `<= $45/week` |
| One-time migration guardrail | `<= $10` |
| Total TF weekly budget | `<= $300/week` |

Evidence chính:

- [PR #303](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/303)
- [Cost model README](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/codex/d8-cost-01-net-cost-model/docs/evidence/directive-08/cost/D8-COST-01-managed-data-services-net-cost-model.md)
- [Cost workbook](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/codex/d8-cost-01-net-cost-model/outputs/d8-cost-01/D8-COST-01-managed-data-services-net-cost-model.xlsx)
- [Summary image](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/codex/d8-cost-01-net-cost-model/outputs/d8-cost-01/Summary.png)

## 10. Kế hoạch rollback

Rollback được định nghĩa theo từng store trong cutover contract và migration plans.

| Store | Đường rollback |
|---|---|
| PostgreSQL | Khóa write vào RDS, restore app values về EKS PostgreSQL path, dùng source/PVC/backup/DMS state còn giữ để điều tra và khôi phục |
| Valkey | Abort cart rollout về cấu hình trước đó; `valkey-cart-pvc` còn giữ hỗ trợ rollback/data investigation trong observation window |
| Kafka | Revert GitOps values cho `checkout`, `accounting`, `fraud-detection` về self-hosted Kafka path; `kafka-pvc` còn giữ hỗ trợ rollback/data investigation |

File tham chiếu:

- [D8-PERF-03-cutover-contract.md](performance/D8-PERF-03-cutover-contract.md)
- [POSTGRESQL-MIGRATION-PLAN.md](../../cdo08/week2/mandate8/implementation/drafts/POSTGRESQL-MIGRATION-PLAN.md)
- [VALKEY-MIGRATION-PLAN.md](../../cdo08/week2/mandate8/implementation/drafts/VALKEY-MIGRATION-PLAN.md)
- [KAFKA-MIGRATION-PLAN.md](../../cdo08/week2/mandate8/implementation/drafts/KAFKA-MIGRATION-PLAN.md)

## 11. Mapping owner

| Phạm vi | Owner / team |
|---|---|
| Package owner | CDO-04 |
| Managed infra handoff | Hoàng Nam / CDO08 |
| PostgreSQL migration và parity | REL-15 owner / DBA / Platform Sync Owner |
| Valkey cart migration | REL-16 owner / Platform Cache Team |
| Kafka/MSK migration | REL-17 owner / Messaging Platform Team |
| Cost decision | CDO04 Cost |
| Release / SLO gate | SRE Team / Release Owner |
| Rollback owner | Rollback Owner trong D8-PERF-03 change ticket |
| Mentor ký nghiệm thu | Mentor có thẩm quyền |

## 12. Checklist demo cho mentor

| Nội dung demo | Nguồn / câu lệnh kiểm chứng | Verdict |
|---|---|---|
| RDS đang hoạt động | `aws rds describe-db-instances --db-instance-identifier techx-tf4-postgresql` | PASS |
| ElastiCache đang hoạt động | `aws elasticache describe-replication-groups --replication-group-id techx-tf4-valkey-cart` | PASS |
| MSK đang hoạt động | `aws kafka list-clusters-v2` và `aws kafka describe-cluster-v2` cho `techx-tf4-orders` | PASS |
| Application dùng managed endpoints | Runtime secret references: `rds-postgres-secret`, `elasticache-valkey-secret`, `msk-kafka-secret` | PASS |
| Không còn self-hosted PostgreSQL/Valkey/Kafka pods | `kubectl -n techx-tf4 get pods,svc` | PASS |
| Checkout SLO đạt | Post-cutover regression và cutover evidence | PASS |
| Data parity đạt | PostgreSQL strict parity, Valkey write-location proof, Kafka producer/consumer proof | PASS |
| Rollback path rõ | D8-PERF-03 và migration plans theo từng store | PASS |
| Cost decision được giải thích | D8-COST-01 model, workbook và CDO04 cost proposal | PASS |

## 13. Ma trận PASS

| Acceptance Criteria | Kết quả | Evidence |
|---|---|---|
| Evidence có timestamp và source | PASS | Mục lục evidence có file ngày tháng và PR links |
| Có before/during/after mapping | PASS | Mục 3 |
| Có data parity result | PASS | Mục 6 |
| Có bằng chứng managed endpoint nhưng không lộ secret | PASS | Mục 5 |
| Có no-self-hosted-pod proof | PASS | Mục 8 |
| Có SLO verdict | PASS | Mục 7 |
| Có cost verdict | PASS | Mục 9 |
| Có rủi ro còn lại | PASS | Mục 14 |
| Có kế hoạch rollback | PASS | Mục 10 |
| Mentor có thể tự xác minh | PASS | Mục 12 |

## 14. Rủi ro còn lại

| Rủi ro còn lại | Mitigation / owner |
|---|---|
| PVC cũ còn giữ trong rollback window | Owner chốt observation window, sau đó archive/delete theo PR cleanup |
| Temporary migration resources có thể phát sinh chi phí nếu để lâu | Cleanup deadline và CDO04 guardrail trong cost proposal |
| Managed service cost cần tiếp tục reconciliation với usage thực tế | D8-COST-01 workbook và cost reconciliation review |
| Secret rotation / TLS mode cần giữ theo SEC-13 contract | SEC-13 và platform owners duy trì ExternalSecret contracts |
| Observation SLO cần tiếp tục theo dõi sau ký nghiệm thu | SRE / Release Owner theo dõi checkout, cart và consumer lag |

## 15. Mentor ký nghiệm thu

```text
MENTOR_NAME=
ROLE=
DECISION=PASS
SIGNED_AT_UTC=
REVIEW_REFERENCE=
NOTES=
```
