# Architecture Decision Log (ADR Index)

Sổ ghi nhận các quyết định liên quan đến kiến trúc, bảo mật và vận hành hệ thống TF4.

**Quy tắc:** Bất kỳ thay đổi nào ảnh hưởng đến luồng bảo mật hoặc thiết kế hệ thống đều phải được ghi nhận vào đây và tạo một file ADR chi tiết trong folder `docs/audit/adr/`.

---

## Index — Đã có ADR file

| ADR # | Ngày | Tóm tắt (The What) | Lý do chính (The Why) | Trạng thái | Owner | File |
|---|---|---|---|---|---|---|
| ADR-001 | 2026-07-08 | Tách biệt quyền Audit và Platform | Separation of Duties — Audit chỉ có quyền Read | Accepted | CDO-07 | [ADR-001](./adr/001-audit-platform-separation.md) |
| ADR-002 | 2026-07-08 | Single NAT Gateway cho Week 1 | Kiểm soát chi phí ~$7.56/tuần, chấp nhận network dependency risk | Accepted | CDO-04 | [ADR-002](./adr/002-single-nat-gateway-cost-tradeoff.md) |
| ADR-003 | 2026-07-08 | GitHub Actions dùng cluster-admin (Bootstrap) | Đơn giản hóa CI/CD ban đầu — downscope sau Week 1 | Accepted — Review Week 2 | CDO-04 | [ADR-003](./adr/003-github-actions-cluster-admin-bootstrap.md) |
| ADR-004 | 2026-07-08 | In-cluster PostgreSQL/Kafka/Valkey cho Week 1 | Cost control — tránh managed service cost ~$100-200/tuần | Accepted — Review Week 2 | CDO-04/08 | [ADR-004](./adr/004-in-cluster-datastores-week1-baseline.md) |
| ADR-005 | 2026-07-08 | Bật EKS Control Plane Logging | Audit requirement — lưu vết kubectl/API calls vào CloudWatch | Accepted | CDO-04 | [ADR-005](./adr/005-eks-control-plane-logging-enabled.md) |
| ADR-006 | 2026-07-09 | Tách Observability sang namespace techx-observability | Lifecycle isolation, RBAC separation, resource isolation | Accepted — Implemented | CDO-04 | [ADR-006](./adr/006-observability-namespace-separation.md) |
| ADR-007 | 2026-07-09 | Single replica và không có probes cho Week 1 | Speed to baseline — fix Week 1/2 sau khi có runtime data | Accepted — Fix Week 1 P0 | CDO-08 | [ADR-007](./adr/007-single-replica-no-probes-week1-baseline.md) |
| ADR-008 | 2026-07-09 | Hardcoded DB credentials plaintext trong values.yaml | Speed to baseline — migrate K8s Secrets Week 1 | Accepted — Fix Week 1 P1 | CDO-08 | [ADR-008](./adr/008-hardcoded-credentials-plaintext-values.md) |
| ADR-009 | 2026-07-09 | Grafana anonymous Admin + OpenSearch security disabled | Demo environment baseline — fix trước khi public expose | Accepted — Fix Week 1 P0/P1 | CDO-08 | [ADR-009](./adr/009-grafana-anonymous-admin-opensearch-security-disabled.md) |
| ADR-010 | 2026-07-09 | Alertmanager disabled — SLO alert gap | Chưa config alert channel — CDO-07 owns OBS-01 | Accepted — Fix Week 1 P1 | CDO-07 | [ADR-010](./adr/010-alertmanager-disabled-slo-alerts-gap.md) |
| ADR-011 | 2026-07-09 | Checkout partial-success sau payment, không có idempotency | Complexity cao — deferred Week 2-3 | Accepted — Deferred | CDO-08 | [ADR-011](./adr/011-checkout-partial-success-post-payment.md) |
| ADR-012 | 2026-07-09 | flagd Central Flag Sync bị deferred — risk ghi nhận | flagd image v0.12.9 crash khi dùng /bin/sh wrapper | **URGENT — Fix ngay** | CDO-04 | [ADR-012](./adr/012-flagd-central-sync-deferred.md) |
| ADR-013 | 2026-07-09 | Multi-AZ chỉ áp dụng cho EKS compute layer | Cost control — stateful workload HA chưa claim | Accepted | CDO-04 | [ADR-013](./adr/013-multi-az-eks-compute-layer-only.md) |
| ADR-014 | 2026-07-14 | AI trust and safety controls for the product review assistant | Amazon Bedrock Converse, Pod Identity, and Guardrails integration | Superseded | CDO-04/AIO | [ADR-014](./adr/014-ai-trust-safety-guardrails.md) |
| ADR-015 | 2026-07-15 | Hệ thống Log kiểm toán bất biến (Tamper-Evident) | S3 Object Lock Compliance Mode 90 ngày, KDF EKS stream, SSO | Accepted | CDO-07 | [ADR-015](./adr/015-eks-cloudtrail-tamper-evident-logging.md) |

---

## ADRs cần tạo (Backlog — chờ thêm thông tin)

| Quyết định cần ghi | Pillar | Owner | Chờ gì |
|---|---|---|---|
| OpenSearch/Prometheus persistence disabled — retention decision | Auditability/Cost | CDO-04 | Runtime cost data |
| Load-generator autostart — explicit profile per env | Cost | CDO-04 | CDO-04 implement COST-01 |
| Cart 60-minute TTL — retention decision | Reliability | CDO-08 | CDO-08 durability decision |
| Container hardening — runAsNonRoot baseline | Security | CDO-08 | CDO-08 implement SEC-03 |
| ALB → frontend-proxy ingress design | Architecture | CDO-04 | Verify runtime ingress config |

---

## Hướng dẫn tạo ADR mới

1. Đặt tên: `NNN-short-description.md` (số tiếp theo).
2. Điền đủ: Context, Decision, Rationale, Known Risks, Fix Plan/Review Triggers, References.
3. Thêm entry vào bảng Index.
4. Tạo PR — cần ít nhất 1 member `tf4-leads` approve.
5. Evidence file: tạo trong `docs/evidence/epic-01/` theo template.
