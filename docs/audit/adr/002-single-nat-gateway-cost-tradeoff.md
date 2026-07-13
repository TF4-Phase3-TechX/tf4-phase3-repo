# ADR-002: Single NAT Gateway cho Week 1 Baseline (Cost Trade-off)

**Ngày:** 2026-07-08
**Trạng thái:** Accepted
**Người quyết định:** CDO-04 (Cost + Infrastructure Owner: Huy Hoàng)
**Người review:** CDO-07 (Audit), toàn TF4
**Pillar liên quan:** Cost Optimization, Auditability
**Terraform file:** `infra/terraform/vpc.tf`

---

## 1. Bối cảnh (Context)

EKS worker nodes chạy trong **private subnets** — không có Internet Gateway trực tiếp. Toàn bộ outbound traffic (pull ECR image, gọi AWS services) phải đi qua **NAT Gateway**.

Có hai lựa chọn:
- **Option A:** 1 Single NAT Gateway dùng chung cho cả 2 AZ.
- **Option B:** 1 NAT Gateway per AZ (2 NAT Gateways cho 2 AZ).

Budget ràng buộc: **$300/tuần** cho toàn bộ hạ tầng TF4.

---

## 2. Quyết định (Decision)

**TF4 chọn Single NAT Gateway cho Week 1 baseline.**

Được implement trong `infra/terraform/vpc.tf`:

```hcl
enable_nat_gateway     = true
single_nat_gateway     = true      # 1 NAT dùng chung
one_nat_gateway_per_az = false     # Không có NAT riêng per AZ
```

**Kết quả thực tế đã verify (2026-07-08):**
- NAT Gateway ID: `nat-0f57f14c4e6039bf4`
- State: `available`
- VPC: `vpc-0a4e2abe9fbb70451`
- Chi phí ước tính: ~$7.56/tuần (hourly) + data processing

---

## 3. Lý do (Rationale)

| Tiêu chí | Single NAT | NAT per AZ | Quyết định |
|---|---|---|---|
| Chi phí/tuần | ~$7.56 | ~$15.12 | ✅ Single NAT tiết kiệm ~$7.56/tuần |
| Network HA | Không full HA | Full HA per AZ | ❌ Single NAT là dependency risk |
| Độ phức tạp | Đơn giản | Phức tạp hơn | ✅ Single NAT dễ quản lý |
| Phù hợp Week 1 | Phù hợp | Premature | ✅ Single NAT đủ cho baseline |

**Lý do chính:** Week 1 tập trung vào baseline deployment và evidence collection, không claim production-grade HA. Chi phí tiết kiệm được dành cho EKS nodes và observability.

---

## 4. Giới hạn của quyết định này (Scope Limitation)

> ⚠️ **Quan trọng:** Multi-AZ trong TF4 Week 1 **chỉ áp dụng cho EKS compute layer** (2 worker nodes ở 2 AZ). Team KHÔNG claim:
> - Full network HA
> - Full application HA
> - Stateful workload HA (PostgreSQL, Kafka, Valkey)

---

## 5. Rủi ro đã ghi nhận (Known Risks)

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| NAT Gateway là SPOF cho outbound | Nếu NAT/AZ lỗi, outbound traffic từ private subnets bị ảnh hưởng | Medium | Monitor NAT metrics; upgrade NAT per AZ khi cần |
| Cross-AZ data transfer cost | Private subnet AZ-b route qua NAT ở AZ-a | Low/Medium | Verify route table; Cost Explorer theo dõi |
| Hiểu nhầm Multi-AZ = full HA | Stakeholder có thể claim full HA sai | Medium | Ghi rõ trong ADR và pitch |

---

## 6. Điều kiện để xem xét lại (Review Triggers)

Quyết định này cần được xem xét lại nếu:
- [ ] Cost Explorer cho thấy NAT data processing > $15/tuần.
- [ ] Outbound connectivity trở thành critical dependency cho checkout/payment.
- [ ] Budget headroom đủ để thêm NAT ($7-8/tuần).
- [ ] BTC yêu cầu network HA cao hơn.

---

## 7. Tham chiếu (References)

- `infra/terraform/vpc.tf` — Terraform config thực tế
- `docs/evidence/epic-04-cost-optimization/02-single-nat-tradeoff.md` — Trade-off analysis chi tiết
- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md` — Cost estimate với NAT ~$7.56/tuần
- `docs/evidence/epic-02-baseline-architecture/05-architecture-risk-register.md` — ARCH-RISK-03
