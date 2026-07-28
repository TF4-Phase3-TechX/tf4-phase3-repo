# D13-INFRA-01 — Nghiên cứu & triển khai Karpenter Spot NodePools

- **Mandate:** Mandate 13 — Cost Efficiency / Elastic Scaling
- **Owner:** CDO04 Infrastructure/Cost
- **Reliability gate / stop authority:** CDO08
- **Loại thay đổi:** Terraform + GitOps, chỉ triển khai sau review
- **Trạng thái:** Research checklist — chưa được xem là approval để apply

## 1. Mục tiêu

Triển khai capacity rẻ qua thay đổi Terraform/GitOps đã được review, với hai NodePool Spot tách biệt:

1. **Spot AMD64** cho các workload x86 đủ điều kiện.
2. **Spot Graviton/ARM64** chỉ cho workload đã xác nhận tương thích ARM64.

Thiết kế phải giữ On-Demand reliability floor, không đưa system-critical workload lên Spot, và có rollback khả thi về protected On-Demand.

## 2. Dependency và điều kiện mở triển khai

- [ ] `D13-PERF-03` hoàn thành và đã cung cấp đầu vào resource/load cần thiết.
- [ ] `D13-PERF-04` hoàn thành và đã cung cấp đầu vào reliability/SLO cần thiết.
- [ ] CDO08 xác nhận placement policy, interruption readiness, resilience gate và quyền dừng rollout.
- [ ] Terraform/GitOps owner, application owner và change approver được chỉ định.
- [ ] Chưa đạt dependency nào thì chỉ nghiên cứu, **không apply** Terraform/GitOps.

## 3. Path cần khảo sát và xác nhận ownership

| Thành phần | Path / phạm vi | Điều cần xác nhận |
|---|---|---|
| NodePool / NodeClass | [karpenter-nodepool.tf](file:///d:/Phase3_Xbrain/tf4-phase3-repo/infra/terraform/karpenter-nodepool.tf) | Terraform là writer duy nhất; requirements, limits, disruption và NodeClass dependency hợp lệ. |
| Reliability floor | [eks.tf](file:///d:/Phase3_Xbrain/tf4-phase3-repo/infra/terraform/eks.tf) | Managed On-Demand `min_size=2`, `desired_size=2` vẫn Ready. |
| Karpenter interruption | Terraform Karpenter/IAM/SQS/EventBridge liên quan | Queue, IAM, controller, AMI, subnet và security group preflight PASS. |
| GitOps placement | Production values/manifests trong GitOps repo | Workload chỉ vào Spot qua selector + toleration của đúng tier. |
| Kế hoạch vận hành | [M13-PM-01-safe-compute-optimization-execution-plan.md](file:///d:/Phase3_Xbrain/tf4-phase3-repo/docs/evidence/mandate13-compute-cost-optimization/M13-PM-01-safe-compute-optimization-execution-plan.md) | Hard-stop, rollback order và evidence contract được tuân thủ. |

## 4. Subtask nghiên cứu → triển khai

### 4.1 Dependency, ownership và baseline
- [ ] Thu sign-off/đầu vào từ `D13-PERF-03`, `D13-PERF-04` và CDO08.
- [ ] Lập RACI cho Terraform writer, GitOps writer, application owner, on-call, reliability stop authority và change approver.
- [ ] Capture UTC snapshot trước thay đổi: managed floor, NodePool, NodeClass, NodeClaim, nodes, pod placement, HPA, PDB, requests/limits và taints/tolerations.
- [ ] Liệt kê workload system-critical, stateful, controller, observability-critical và load-generator bắt buộc giữ protected On-Demand.

**Output:** dependency checklist, RACI và inventory before-change.

### 4.2 Karpenter/Terraform preflight
- [ ] Xác nhận Terraform là writer duy nhất của Karpenter resources.
- [ ] Xác minh Karpenter version và schema CRD đang chạy có hỗ trợ các trường dự kiến.
- [ ] Xác minh interruption queue/events, IAM, AMI, quota, subnet và security group.
- [ ] Chạy read-only `terraform plan`; phân loại mọi drift/destroy ngoài phạm vi D13.
- [ ] Chỉ tiếp tục khi plan sạch và prerequisite hạ tầng PASS.

**Output:** preflight report và Terraform plan review.

### 4.3 Thiết kế Spot AMD64 NodePool
- [ ] Xác định workload x86 eligible cùng CPU/memory profile, HPA envelope và AZ.
- [ ] Đề xuất `kubernetes.io/arch=amd64` và `karpenter.sh/capacity-type=spot`.
- [ ] Đề xuất explicit allow-list gồm nhiều AMD64 instance families/types và AZ; không dùng wildcard instance type.
- [ ] Thiết kế label/tier, `NoSchedule` taint, selector và toleration rõ ràng.
- [ ] Đề xuất CPU capacity ceiling, `consolidationPolicy`, `consolidateAfter` và disruption budget.

**Output:** AMD64 design table + Terraform diff proposal được CDO04/CDO08 review.

### 4.4 Thiết kế Spot Graviton NodePool
- [ ] Xác minh OCI index/multi-arch và runtime compatibility cho từng workload trước khi cho phép ARM64.
- [ ] Đề xuất `kubernetes.io/arch=arm64` và `karpenter.sh/capacity-type=spot`.
- [ ] Đề xuất explicit allow-list nhiều Graviton family/type, gồm AZ phù hợp; không dùng wildcard.
- [ ] Thiết kế label `optimization.techx.io/tier=arm64-spot`, `NoSchedule` taint, selector/toleration riêng, CPU ceiling và consolidation controls.
- [ ] Loại trừ mọi workload không chứng minh ARM64-compatible.

**Output:** ARM64 eligibility matrix + Terraform/GitOps diff proposal được review.

### 4.5 GitOps placement và safety boundary
- [ ] Map từng workload eligible vào đúng Spot tier.
- [ ] Render/diff manifests để chứng minh workload không có selector/toleration không thể schedule lên Spot.
- [ ] Tách change NodePool limits khỏi workload requests/limits, trừ khi metrics chứng minh cần thay đổi request.
- [ ] Xác nhận protected/system-critical workload không có Spot toleration.

**Output:** workload-placement matrix, manifest render/diff và exclusion list.

### 4.6 Guardrail, failure mode và rollback
- [ ] Review PDB, replicas, topology spread, replacement headroom, quota, disruption budget và khả năng reschedule sau mất một Spot node.
- [ ] Ghi hard-stop: protected workload Pending; NodePool/NodeClass/IAM/interruption error; hoặc SLO degradation.
- [ ] Xác định previous-known-good Terraform revision và GitOps revision.
- [ ] Viết rollback order về protected On-Demand; bao gồm restore managed floor khi cần và Browse/Cart/Checkout smoke checks.
- [ ] Peer-review rollback runbook; phải có revision/lệnh cụ thể, không chỉ mô tả.

**Output:** risk register, go/no-go checklist CDO08 và rollback runbook.

### 4.7 Design review, canary và runtime evidence
- [ ] Review Terraform/GitOps design; xác minh `terraform plan` chỉ thay đổi resource D13 mong đợi, không có destroy ngoài dự kiến.
- [ ] Sau approval và trong change window: apply canary theo từng NodePool.
- [ ] Xác minh Spot AMD64 NodePool `Ready` và Spot Graviton NodePool `Ready`.
- [ ] Tạo/quan sát NodeClaim canary; xác minh requirements, labels/taints, instance diversification, ceiling, disruption budget và consolidation.
- [ ] Xác minh On-Demand system/reliability floor vẫn `Ready` và system-critical workload không bị đặt lên Spot.
- [ ] Lưu Terraform/GitOps revision, UTC timestamps, `kubectl get nodepool,nodeclaim,nodes` và evidence placement.

**Output:** runtime capture và go/no-go cho performance curve/interruption test.

### 4.8 ADR và handoff
- [ ] Cập nhật ADR-013 với allow-list instance thực tế, capacity/disruption controls, workload eligibility/exclusion, guardrails, rollback và links evidence.
- [ ] CDO04/CDO08 review, ký ADR và handoff evidence cho Task 1–4.

**Output:** ADR-013 sẵn sàng sign-off và evidence package có traceability.

## 5. Acceptance criteria

- [ ] Terraform/GitOps path và ownership được xác nhận.
- [ ] Spot AMD64 NodePool `Ready`.
- [ ] Spot Graviton NodePool `Ready`.
- [ ] Labels, taints và architecture/capacity requirements đúng.
- [ ] Diversification đủ rộng, dùng explicit allow-list và không wildcard.
- [ ] Consolidation được bật.
- [ ] Limits/capacity ceiling và disruption policy được CDO04/CDO08 review.
- [ ] On-Demand system floor vẫn `Ready`; system-critical workload không ở Spot.
- [ ] Rollback path Terraform/GitOps được xác nhận bằng revision cụ thể.

## 6. Evidence bàn giao

- Terraform plan/apply review và rollback revisions.
- Before/after snapshots NodePool, NodeClass, NodeClaim, nodes và workload placement.
- ARM64 compatibility matrix và workload eligibility/exclusion matrix.
- Rendered GitOps manifests/diff thể hiện selector/toleration boundary.
- Runtime capture cho hai Spot NodePool, NodeClaim canary, consolidation, limits/budgets và On-Demand floor.
- ADR-013 đã được review/ký, liên kết đến tất cả evidence trên.
