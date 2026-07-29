# M13-PM-01: Hồ sơ thực thi compute ARM64 và Spot

## 1. Trạng thái

| Trường | Giá trị |
|---|---|
| Trạng thái execution | **EXECUTED** |
| Hoàn tất migration | 2026-07-28 |
| Mandate | `mandates/MANDATE-13-cost-efficiency-elastic.md` |
| Chủ trì | CDO04 Infrastructure / Cost |
| Reliability gate | CDO08 Reliability / on-call |
| Cập nhật | 2026-07-29 |

`EXECUTED` xác nhận workstream hạ tầng và migration đã hoàn tất. Tài liệu này không phải final acceptance verdict của Mandate 13.

## 2. Các thay đổi đã thực thi

- Thiết lập nền tảng image multi-architecture, ARM64 capacity và Karpenter Spot interruption handling.
- Tạo protected ARM64 On-Demand capacity và chuyển protected pool về `t4g.large`.
- Tạo hai Managed Node Group ARM64 green, mỗi AZ một group.
- Chuyển workload từ blue AMD64 capacity sang ARM64 capacity.
- Drain blue nodes theo từng AZ bằng eviction/PDB bình thường.
- Retire Managed Node Group AMD64 sau khi green capacity và migration soak hoàn tất.
- Giữ protected capacity cho OpenSearch và observability; giữ hai Spot nodes làm reliability floor cho stateless workloads.
- Khôi phục Prometheus sang PVC `gp3-retain`; PV `gp2-retain` cũ vẫn được giữ lại với reclaim policy `Retain`.

## 3. Trạng thái hạ tầng sau execution

```text
us-east-1a:
  1 x Managed t4g.large ARM64 On-Demand
  1 x ARM64 Spot node

us-east-1b:
  1 x Managed t4g.large ARM64 On-Demand
  1 x protected t4g.large ARM64 On-Demand
  1 x ARM64 Spot node
```

Terraform hiện khai báo:

- Hai Managed Node Group `t4g.large`, AL2023 ARM64, On-Demand, một group mỗi AZ.
- Một protected ARM64 On-Demand NodePool cho workload stateful và observability.
- Một ARM64 Spot NodePool cho workload stateless đủ điều kiện.
- Một `techx-general` AMD64 `t3a.large` fallback NodePool vẫn còn trong desired state nhưng không có live node tại checkpoint.

Vì vậy, claim chính xác là:

- 100% live EKS worker nodes là ARM64 tại checkpoint 2026-07-28.
- 100% Managed Node Groups là ARM64.
- Desired state vẫn còn AMD64 fallback qua Karpenter.

## 4. Kết quả workstream

| Hạng mục | Trạng thái |
|---|---|
| Multi-architecture image và ARM64 workload rollout | EXECUTED |
| ARM64 Spot capacity | EXECUTED |
| Protected ARM64 On-Demand capacity | EXECUTED |
| Hai Managed Node Group cuối cùng chuyển sang ARM64 | EXECUTED |
| AMD64 Managed Node Group retirement | EXECUTED |
| Managed ARM64 migration verdict | PASS |
| Mandate 21 reliability floor | Giữ nguyên theo quyết định vận hành |

Steady topology giữ ba On-Demand nodes và hai Spot nodes. Vì vậy steady-state Spot ratio là `40%`; `50%` chỉ xuất hiện khi Spot NodePool scale từ hai lên ba node ở high load. Đây là quyết định reliability floor, không phải lỗi migration độc lập.

Final Mandate 13 acceptance vẫn tách khỏi migration verdict. Report request-changes ghi nhận các điểm chưa đủ để đóng mandate, gồm lifecycle node-hours, complete-run Spot ratio và các denominator liên quan.

## 5. Commit và nguồn chính

| Commit / PR | Nội dung |
|---|---|
| `4feb7925` / #641 | Multi-architecture image và capacity foundation |
| `b89104ba` / #695 | Protected ARM64 NodePool |
| `91f3eee0` / #705 | Protected capacity chuyển về `t4g.large` |
| `7757be37` / #717 | Tạo hai Managed ARM64 green groups |
| `dfdd9440` / #718 | Loại policy trùng trên Managed Node Groups |
| `acd947f3` / #719 | Retire Managed AMD64 Node Group |

Source of truth:

- `infra/terraform/eks.tf`
- `infra/terraform/karpenter.tf`
- `infra/terraform/karpenter-nodepool.tf`
- `deploy/build-push-images.sh`
- `.github/workflows/build-and-push.yaml`

Evidence và verdict:

- `D13-MANAGED-ARM64-MIGRATION-VERDICT.md`
- `D13-EVIDENCE-PACK-REQUEST-CHANGES-20260728.md`
- `D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md`
- `D13-SPOT-INTERRUPTION-DRILL-EVIDENCE.md`
- `ADR-013-arm64-spot-capacity-decision.md`
- `M13-PROGRESS-REPORT-20260727.md`

Phương pháp nghiệm thu, load-test contract và checklist vận hành không lặp lại trong tài liệu này. Chúng nằm ở mandate và các evidence report tương ứng.
