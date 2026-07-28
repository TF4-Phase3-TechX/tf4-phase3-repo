# M13-PM-01 — Kế hoạch triển khai tối ưu compute an toàn với ARM64 và Spot

## 1. Trạng thái tài liệu

| Trường | Giá trị |
|---|---|
| Trạng thái | **PLANNED — chưa triển khai, chưa có kết quả runtime** |
| Mandate | `mandates/MANDATE-13-cost-efficiency-elastic.md` |
| Eligibility source | `jira-report/SPOT-ARM64-ELIGIBILITY-MATRIX.md` |
| Load/SLO contract | `../epic-09-compute-cost-optimization/D13-PERF-01-variable-load-curve-slo-contract.md` |
| Chủ trì | CDO04 Infrastructure / Cost |
| Reliability gate | CDO08 Reliability / on-call |
| Ngày lập | 2026-07-25 |
| Hạn gốc của mandate | 2026-07-24 — đã qua; execution chỉ bắt đầu khi có change ticket/gia hạn được phê duyệt |

Tài liệu này là execution contract và evidence index. Nó **không** khẳng định cluster đã chạy Spot/Graviton, đã giảm node-hours, đã chịu được interruption hoặc đã đạt SLO.

## 2. Mục tiêu và tiêu chí hoàn thành

Cùng một đường cong tải thấp → cao → thấp, cấu hình optimized chỉ được PASS khi đồng thời đạt tất cả điều kiện sau:

1. Tổng worker node-hours giảm ít nhất **30%** so với baseline.
2. Spot chiếm **hơn 50%** tổng optimized worker node-hours.
3. Có Graviton/ARM64 thực sự chạy workload và phục vụ traffic; ARM64 node idle không được tính.
4. Karpenter tăng node khi tải tăng và xóa peak-only node khi tải giảm.
5. Checkout success **≥99%**; Browse và Cart success **≥99.5%**; Storefront p95 **<1 giây**.
6. Một Spot node bị interruption giữa peak nhưng delta failure của request khách hàng bằng **0**.
7. EC2, Cost Explorer và Grafana cung cấp đủ ba nhóm bằng chứng Mandate 13 yêu cầu.
8. Có ADR được owner/reviewer ký, ghi rõ capacity pools, Karpenter, PDB/replica/drain và rollback.

Không được hạ SLO, bơm On-Demand để che lỗi, dùng USD cost trong account credit làm metric chính, public cổng vận hành hoặc disable/thay đổi cơ chế sự cố `flagd`.

## 3. Quyết định triển khai

Áp dụng chiến lược **provision and qualify → move pods → reduce old floor**, không replace node hàng loạt:

1. Giữ Managed Node Group AMD64 On-Demand hiện tại làm break-glass/controller baseline trong các bước build, canary và interruption rehearsal.
2. Tách capacity theo vai trò, không mở rộng `techx-general` thành một pool hỗn hợp để mọi workload có thể vô tình lên Spot.
3. Chứng minh image và ứng dụng trên ARM64 On-Demand trước; chỉ sau đó mới thêm rủi ro Spot.
4. Chỉ batch stateless đã đủ replica/PDB/probe được phép lên ARM64 Spot.
5. Stateful, singleton chưa harden và platform/observability quan trọng luôn dùng protected AMD64 On-Demand trong phạm vi mandate này.
6. Chỉ giảm `min_size`/`desired_size` của Managed Node Group sau khi canary và real Spot interruption gate đều PASS; không xóa node group trong mandate này.

### 3.1 Batch đầu tiên

Batch đầu tiên lấy nguyên từ eligibility matrix:

- `cart`
- `checkout`
- `currency`
- `frontend`
- `frontend-proxy`
- `payment`
- `product-catalog`
- `quote`
- `shipping`

Các workload này hiện có từ hai replicas, PDB, probe và topology spread. Trước mỗi lần chuyển capacity vẫn phải xác minh trạng thái **live**; cấu hình trong Git không thay thế bằng chứng runtime.

### 3.2 Ngoài phạm vi batch đầu

**Protected vì stateful/PVC:**

- `kafka`
- `postgresql`
- `valkey-cart`
- `prometheus`
- `alertmanager`
- `opensearch`

**Chưa đủ điều kiện vì singleton/thiếu resilience:**

- `accounting`
- `ad`
- `email`
- `flagd`
- `fraud-detection`
- `image-provider`
- `llm`
- `product-reviews`
- `recommendation`

`load-generator` là test infrastructure, không dùng để chứng minh customer-serving workload đã chuyển Spot. Mở rộng eligibility cho các singleton là workstream sau: tối thiểu hai replicas, probe, PDB, topology, dependency review và interruption test riêng.

## 4. Trạng thái hiện tại và khoảng cách cần đóng

| Hạng mục | Trạng thái trong repository | Khoảng cách |
|---|---|---|
| Managed Node Group | `t3.large`, AMD64, On-Demand, min/desired 2 | Chưa co được dưới floor hai managed nodes |
| Karpenter | v1.14.0; `enable_spot_termination = false` | Chưa có interruption queue/controller configuration đã chứng minh |
| NodePool | AMD64, On-Demand, `t3.large`/`t3a.large` | Chưa có ARM64 hoặc Spot |
| Consolidation | `WhenEmptyOrUnderutilized`, sau 5 phút | Có cơ chế scale-in nhưng chưa được chứng minh trên load curve |
| ECR images | Image đang deploy chỉ có AMD64 | Cần OCI index với Linux AMD64 + ARM64 bằng tag mới |
| Local ARM64 | Tất cả custom image build đạt; tám service Compose đạt | Là prerequisite, không phải ECR/runtime proof |
| Scheduling | Chart hỗ trợ selector/affinity/toleration/spread | Cần placement policy rõ ràng cho protected/canary/Spot |
| Quota namespace | CPU request 4, CPU limit 8, memory request 8 GiB, 40 pods | Có thể chặn HPA, rollout surge hoặc replacement pod |
| Evidence | Có D13 variable-load/SLO contract | Chưa có baseline/optimized runtime artifacts |

## 5. Kiến trúc capacity đích

### 5.1 Protected AMD64 On-Demand

Mục đích: chạy stateful, singleton, platform/observability và workload chưa được phê duyệt cho Spot.

Thiết kế dự kiến:

- `kubernetes.io/arch=amd64`.
- `karpenter.sh/capacity-type=on-demand`.
- Label vai trò, ví dụ `optimization.techx.io/tier=protected`.
- Stateful/singleton/platform dùng selector hoặc required affinity tới tier này.
- Managed Node Group cũng được label protected để làm floor khôi phục.
- Instance policy đủ đa dạng sau khi kiểm tra scheduler fit, quota và AMI; không pin một type nếu không cần.
- Capacity limit hữu hạn và được review theo budget.

### 5.2 ARM64 On-Demand canary

Mục đích: tách kiểm chứng ARM64 khỏi rủi ro bị thu hồi của Spot.

Thiết kế dự kiến:

- `kubernetes.io/arch=arm64`.
- `karpenter.sh/capacity-type=on-demand`.
- Label riêng, ví dụ `optimization.techx.io/tier=arm64-canary`.
- `NoSchedule` taint; chỉ workload canary có toleration.
- Capacity limit chỉ đủ canary và recovery headroom.
- Chỉ cho phép instance family/size đã qua quota, AMI, pod-request và allocatable-fit preflight.

Pool này không được dùng trong final optimized run nếu nó làm tỷ lệ Spot không đạt hơn 50%, trừ capacity phục vụ recovery ngắn hạn đã được tính đầy đủ trong mẫu số.

### 5.3 ARM64 elastic capacity

Mục đích: chạy batch đủ điều kiện bằng Graviton Spot và có fallback được kiểm soát khi Spot thiếu.

Thiết kế dự kiến:

- `kubernetes.io/arch=arm64`.
- Cho phép Spot và On-Demand theo hành vi ưu tiên/fallback đã được xác minh với đúng Karpenter v1.14.0 và cấu hình account.
- Label riêng, ví dụ `optimization.techx.io/tier=arm64-elastic`.
- `NoSchedule` taint; chỉ batch chín workload có toleration.
- Diversify qua nhiều family, size và hai AZ phù hợp; không pin một Spot capacity pool.
- Capacity limit hữu hạn; disruption budget ngăn nhiều node biến mất đồng thời do consolidation/drift.
- Mọi On-Demand fallback đều được tính vào optimized total node-hours. Nếu Spot ratio không còn **>50%**, run FAIL/rerun; fallback không được dùng để làm đẹp SLO rồi bỏ khỏi mẫu số.

Nếu preflight cho thấy mixed capacity pool không cung cấp preference/fallback có thể kiểm soát hoặc audit với phiên bản hiện tại, implementation phải tách thành ARM64 Spot pool và ARM64 On-Demand recovery pool. Không đổi mục tiêu placement hay phép đo.

### 5.4 Vì sao không dùng một pool chung

Một pool chung `amd64 + arm64 + on-demand + spot` tạo ba vấn đề:

1. Stateful/platform workload có thể lên Spot nếu chỉ nhìn resource fit.
2. Không kiểm soát được canary ARM64 trước khi thêm rủi ro interruption.
3. Khó giải thích tỷ lệ Spot, Graviton và rollback trong ADR/evidence.

Tách role bằng label/taint giữ blast radius nhỏ và làm từng phase có thể rollback độc lập.

## 6. Preflight bắt buộc

Không apply IaC hoặc đổi placement khi bất kỳ mục nào dưới đây chưa PASS.

### 6.1 Governance

- Có change ticket/gia hạn vì hạn gốc 2026-07-24 đã qua.
- Ghi owner, reviewer, on-call, test window, rollback window và người có quyền stop.
- Freeze thay đổi không liên quan trong baseline và optimized windows.
- Ghi previous-known-good Git/Terraform/chart revisions.
- Xác nhận các file load test bị xóa cục bộ không bị tự ý khôi phục hoặc sửa. Chỉ dùng asset đang tồn tại và đã được owner phê duyệt tại thời điểm chạy.

### 6.2 AWS/Karpenter

- Kiểm tra Service Quotas cho các family ARM64 On-Demand và Spot dự kiến.
- Kiểm tra Spot capacity flexibility trên nhiều family/size/AZ; không khóa vào một pool.
- Kiểm tra subnet IP, security-group selector, node IAM role và ECR pull permission.
- Kiểm tra AL2023 alias đang pin có ARM64 AMI tương thích Kubernetes 1.34.
- Đối chiếu Terraform module và Karpenter v1.14.0 với NodePool/EC2NodeClass schema thực tế.
- Xác minh `enable_spot_termination` tạo đúng SQS queue, EventBridge rules/targets, IAM và Helm `interruptionQueue`; không chỉ đổi boolean rồi giả định đã hoạt động.
- Xác minh queue không phải SQS của module Slack/security khác.
- Kiểm tra Karpenter controller metrics/logs và NodeClaim events có thể quan sát.
- Review Terraform plan: chỉ resource Mandate 13 được thay đổi, không có destroy ngoài dự kiến.

### 6.3 Image supply chain

Với từng service trong batch:

- Tag mới là immutable.
- OCI image index có đúng `linux/amd64` và `linux/arm64` child manifests.
- Lưu index digest và từng child digest.
- Cả hai child manifests qua vulnerability gate, SBOM, signature, provenance/attestation và verify tương đương.
- Index digest dùng trong GitOps cũng được ký/attest/verify theo policy đã review.
- Không có `exec format error`, image pull error hoặc missing runtime asset trên ARM64.

### 6.4 Kubernetes/workload

Với từng eligible service trước interruption:

- Ít nhất hai pods `Ready`.
- PDB healthy và `allowedDisruptions` đủ cho một node loss.
- Service có ít nhất hai serving endpoints khi applicable.
- Hai replicas nằm trên hai node khác nhau.
- Probe, graceful termination và `terminationGracePeriodSeconds` phù hợp cửa sổ interruption.
- CPU/memory requests hợp lệ; không có OOMKilled, restart burst hoặc throttling regression.
- HPA có thể lên `maxReplicas` và rollout có thể tạo replacement/surge mà không bị ResourceQuota chặn.
- Không có Pending, FailedScheduling hoặc topology conflict.

`ScheduleAnyway` chỉ là spread mềm. Nếu live scheduler vẫn đặt hai replicas cùng node, phải dùng hostname spread/required anti-affinity phù hợp trước drill.

### 6.5 Test và observability

- Dùng nguyên contract 25 → 200 → 25 trong `D13-PERF-01-variable-load-curve-slo-contract.md`.
- Baseline và optimized dùng cùng Git SHA của load generator, image digest, traffic mix, test data, feature flags, retry/timeout và duration.
- Prometheus, Grafana, Locust, node metrics và Karpenter metrics hoạt động.
- Có đồng hồ UTC chung cho console/video/events.
- Chênh tổng requests dự kiến không quá 5%.
- `flagd` và OpenFeature incident path vẫn hiện diện, không bị bypass.

### 6.6 Feasibility trước khi chạy

Dùng projected lifecycle để tính trước:

```text
projected_total_node_hours =
  protected_on_demand_hours
  + arm64_spot_hours
  + arm64_on_demand_fallback_hours

projected_spot_ratio_percent =
  100 * arm64_spot_hours / projected_total_node_hours

projected_reduction_percent =
  100 * (baseline_node_hours - projected_total_node_hours)
      / baseline_node_hours
```

Nếu retained floor và projected scale-down không thể đạt đồng thời giảm ≥30% và Spot >50%, dừng. Tune resource requests/bin-packing hoặc xin phê duyệt floor thấp hơn trước, không chạy để thử may.

## 7. Chiến lược build multi-architecture

### 7.1 Thay đổi tối thiểu

Build path hiện tại chạy `buildx bake --load` cho AMD64 rồi `docker push`. Multi-platform image không thể dùng chuỗi này làm cơ chế publish.

Future implementation phải:

1. Giữ bước validate target bằng `docker buildx bake --print`.
2. Với mỗi service, chạy **một** Buildx publish operation cho `linux/amd64,linux/arm64`.
3. Bỏ `--load` và bỏ `docker push` riêng sau build.
4. Giữ tag `${DEMO_VERSION}-${SERVICE}` và ECR repository hiện tại.
5. Chỉ cài QEMU/binfmt khi GitHub runner không native-build được ARM64; action phải pin immutable revision như các action hiện tại.
6. Không đổi Dockerfile nếu chưa có build/runtime failure cụ thể; local matrix đã chứng minh build ARM64.

### 7.2 Digest và promotion

Sau publish:

1. Resolve digest gắn với tag; digest này phải là OCI index/manifest-list digest.
2. Inspect raw index và trích child digest theo architecture.
3. Assert tập platform có `linux/amd64` và `linux/arm64`; platform thiếu hoặc thừa ngoài policy làm gate FAIL.
4. Ghi `service=index_digest`, `amd64_child_digest`, `arm64_child_digest` vào build metadata.
5. GitOps promotion tiếp tục pin **index digest**, để kubelet chọn child manifest đúng theo node architecture.
6. Sau Argo CD sync, xác minh pod AMD64 và ARM64 đều resolve từ cùng index digest tới child digest đúng.

### 7.3 Security gate

Workflow hiện tại scan/sign/SBOM/attest digest trả về theo tag. Trước khi giữ nguyên hành vi này phải chứng minh tool thực sự xử lý cả hai child manifests.

Nếu không chứng minh được, workflow phải:

- enumerate AMD64 và ARM64 child digests;
- chạy Trivy HIGH/CRITICAL gate trên từng child;
- tạo CycloneDX SBOM cho từng child;
- ký và attest provenance/SBOM từng child với trường architecture;
- verify signature/attestation từng child;
- ký/attest/verify index digest dùng cho deployment;
- upload artifact gồm index, children, scans, SBOMs, provenance và verify outputs.

Không mở promotion PR nếu một architecture fail. Không coi ECR scan-on-push hoặc index-level scan là bằng chứng thay thế nếu chưa xác minh coverage.

### 7.4 Build exit gate

Mỗi eligible service chỉ được chuyển ARM64 khi có:

- workflow run URL và source SHA;
- immutable tag;
- index + AMD64 + ARM64 digests;
- security gate PASS cho cả hai architectures;
- GitOps index digest khớp build metadata;
- một ARM64 canary pod Ready và một request/trace thành công qua pod đó.

## 8. Chiến lược resource requests và resilience

Mandate không yêu cầu rightsize hoàn hảo từng pod. Mục tiêu là tín hiệu đủ đúng cho HPA/Karpenter và đủ safety margin để tránh OOM.

Với mỗi service:

1. Thu CPU usage, memory working set, throttling, restart và latency ở low/ramp/peak từ cùng load contract.
2. CPU request phải đủ đại diện cho sustained usage để HPA CPU utilization có ý nghĩa và Karpenter bin-pack không quá chặt.
3. Memory request lấy peak quan sát cộng safety margin đã review; memory limit không được thấp tới mức gây OOM khi consolidation.
4. Tính tổng requests tại HPA max, cộng rollout surge và replacement pods.
5. So với namespace ResourceQuota và allocatable của instance candidates.
6. Thay từng batch nhỏ, chạy lại low/peak smoke gate, không tune đồng thời image, request và replica nếu không cần.
7. Ghi before/after request, observed peak, margin và lý do vào ADR/evidence.

Singleton chỉ được thêm vào Spot eligibility ở workstream riêng sau khi có ≥2 replicas, PDB, probes, cross-node placement và dependency-specific review. Không tăng toàn bộ singleton lên hai replicas chỉ để đạt tỷ lệ Spot nếu semantics (ví dụ Kafka consumer) chưa được owner xác nhận.

## 9. Kế hoạch rollout theo phase

Mỗi phase fail sẽ chặn tất cả phase sau.

### Phase 0 — Freeze và baseline

**Owner:** CDO04; **reviewer:** CDO08.

**Entry:** governance, load contract và observability preflight PASS.

**Actions:**

1. Ghi Git/Terraform/chart revision, load-generator digest, feature flags, quota, nodes, NodeClaims, pods, HPA, PDB và endpoints.
2. Chạy nguyên curve 25 users 5 phút → ramp 5 phút → 200 users 15 phút → ramp-down 5 phút → 25 users ít nhất 30 phút.
3. Giữ low phase tới khi HPA ổn định và Karpenter đã đánh giá consolidation.
4. Lưu EC2 launch/termination timestamps cho mọi worker giao với run window.
5. Lưu raw Locust CSV/history/failures/exceptions, Grafana và ba console views.

**Exit:** tất cả baseline SLO PASS, denominators đầy đủ, lifecycle đủ tính node-hours.

**Rollback/abort:** baseline SLO fail hoặc evidence thiếu thì dừng và sửa baseline/test; không triển khai optimization trên baseline không hợp lệ.

### Phase 1 — Multi-arch build gate

**Owner:** CI/security + application owners.

**Entry:** Phase 0 PASS; build change được review.

**Actions:** publish batch chín service; inspect index/children; chạy supply-chain gate; promote index digests qua GitOps.

**Exit:** mọi service đạt build exit gate.

**Rollback/abort:** giữ deployment ở known-good AMD64 digest nếu thiếu child manifest, CVE/signature/attestation fail hoặc ARM64 startup fail.

### Phase 2 — Capacity foundation

**Owner:** CDO04.

**Entry:** Terraform plan, quota, AMI, IAM và interruption infrastructure preflight PASS.

**Actions:**

1. Bật Spot interruption handling theo module/version đã xác minh.
2. Tạo protected AMD64, ARM64 canary và ARM64 elastic capacity definitions.
3. Gắn taint/label; chưa giảm Managed Node Group.
4. Pin protected workloads trước khi Spot nhận toleration.
5. Provision một ARM64 On-Demand canary node và xác minh collector/platform DaemonSets tương thích.

**Exit:** pools reconcile; canary NodeClaim Ready; unapproved workload không thể lên Spot; protected workloads schedulable.

**Rollback/abort:** revert Terraform revision nếu NodeClass/NodePool/IAM/queue fail hoặc protected workload bị Pending.

### Phase 3 — ARM64 On-Demand canary

**Owner:** application owner + CDO08.

**Entry:** Phase 2 PASS; `currency` có multi-arch gate PASS.

**Actions:**

1. Chuyển riêng `currency` sang ARM64 canary bằng existing `schedulingRules`.
2. Xác minh architecture, image child digest, Ready, endpoints, PDB, HPA và traffic.
3. Chạy low/ramp/peak checks; theo dõi exec-format, startup, OOM, throttling, latency và error.
4. Sau PASS, chuyển lần lượt: `quote` → `shipping` → `product-catalog` → `cart` → `payment` → `checkout` → `frontend` → `frontend-proxy`.
5. Mỗi bước phải ổn định trước bước kế tiếp; không move cả batch một lần.

**Exit:** toàn batch chạy ARM64 On-Demand, SLO PASS, không Pending và không protected workload sai placement.

**Rollback/abort:** trả selector/toleration về protected AMD64 và digest known-good của service vừa chuyển.

### Phase 4 — ARM64 Spot canary và rehearsal

**Owner:** CDO04 thực hiện capacity action; CDO08/on-call giữ stop authority.

**Entry:** Phase 3 PASS; interruption queue/events/metrics đã được chứng minh end-to-end; replacement headroom sẵn sàng.

**Actions:**

1. Chuyển eligible batch từ ARM64 canary sang ARM64 elastic capacity theo từng nhóm nhỏ.
2. Xác minh target node thực sự là EC2 Spot, ARM64, Ready, đang chạy replicated eligible workloads và đang nhận traffic.
3. Xác minh mỗi service có replica khác trên node khác và PDB cho phép một disruption.
4. Chạy voluntary `drain`/termination rehearsal để kiểm tra scheduler, PDB và recovery. Evidence phải ghi **SIMULATED — không thỏa live Spot interruption gate**.
5. Khi simulated rehearsal PASS, chạy provider-authentic Spot interruption bằng cơ chế AWS-supported đã được phê duyệt cho account/version; ưu tiên AWS Fault Injection Service nếu preflight xác nhận đúng semantics và audit trail.
6. Giữ một Locust process ở 200 users; không restart/reset/isolate counters.
7. Ghi cumulative requests/failures ngay trước và sau recovery, node/PDB/eviction/NodeClaim timeline và Grafana liên tục.

**Exit:** interruption request count >0; customer failure delta = 0; replacement Ready; mọi SLO PASS; protected workload không bị ảnh hưởng.

**Rollback/abort:** bất kỳ customer error nào lập tức dừng test và trả batch về ARM64 On-Demand hoặc protected AMD64 theo nguyên nhân.

### Phase 5 — Giảm Managed Node Group floor

**Owner:** CDO04; **approval:** CDO08 + change approver.

**Entry:** Phase 4 PASS; feasibility vẫn đạt ≥30% reduction và >50% Spot sau khi tính mọi fallback.

**Actions:**

1. Chọn minimal break-glass/controller floor dựa trên protected requests, AZ resilience và recovery test; không chọn bằng cảm tính.
2. Thay `min_size`/`desired_size` qua reviewed Terraform.
3. Không xóa node group.
4. Quan sát drain, protected placement, stateful health và observability.
5. Chạy Browse/Cart/Checkout smoke test sau reduction.

**Exit:** protected workloads healthy; floor mới ổn định; rollback tăng floor đã sẵn sàng.

**Rollback/abort:** restore previous min/desired nếu Pending, stateful/platform degradation, lost observability hoặc recovery capacity không đủ.

### Phase 6 — Final optimized acceptance run

**Owner:** CDO04 + CDO08.

**Entry:** final topology ổn định; baseline input còn comparable; evidence collectors Ready.

**Actions:**

1. Chạy cùng curve, duration, traffic mix và feature flags như baseline.
2. Thực hiện lại real Spot interruption tại T+15 đến T+20 trong peak.
3. Giữ low observation ít nhất 30 phút và tới khi HPA ổn định, peak-only NodeClaims đã terminate, worker count về approved low state.
4. Lấy EC2 lifecycle timestamps, Locust, Grafana, Karpenter/Kubernetes evidence.
5. Tính node-hours và Spot ratio từ lifecycle overlap.
6. Sau Cost Explorer reporting lag, bổ sung Usage Quantity grouped by Purchase Option và Instance Type.

**Exit:** toàn bộ compliance matrix ở mục 13 PASS.

**Rollback/abort:** áp dụng hard-stop và rollback ở mục 11; run fail không được dùng để claim mandate.

### Phase 7 — ADR và verdict

**Owner:** CDO04; **sign-off:** CDO08 + change approver.

- Viết `ADR-013-arm64-spot-capacity-decision.md`.
- Ghi instance constraints thực tế, không chỉ ví dụ family ban đầu.
- Ghi pool labels/taints, capacity behavior, interruption queue, PDB/replica/drain, floor, rollback và rejected options.
- Link mọi runtime artifact.
- Chỉ ghi Mandate 13 PASS khi tất cả hard gates có bằng chứng.

## 10. Phép đo và evidence contract

Không định nghĩa lại contract D13. Dùng nguyên công thức:

```text
node_seconds_i = max(
  0,
  min(instance_termination_utc_i, run_end_utc)
    - max(instance_launch_utc_i, run_start_utc)
)

total_worker_node_hours = sum(node_seconds_i) / 3600

node_hour_reduction_percent =
  100 * (baseline_worker_node_hours - optimized_worker_node_hours)
      / baseline_worker_node_hours

spot_node_hour_ratio_percent =
  100 * optimized_spot_worker_node_hours
      / optimized_total_worker_node_hours
```

EC2 launch/termination timestamps là nguồn lifecycle chính. NodeClaim timestamps là correlation/fallback có ghi chú, không thay thế mặc định.

### 10.1 Request và interruption

```text
flow_total = flow_success + flow_failure
flow_success_rate_percent = 100 * flow_success / flow_total

interruption_request_count =
  post_interruption_cumulative_requests
  - pre_interruption_cumulative_requests

customer_error_count =
  post_interruption_cumulative_failures
  - pre_interruption_cumulative_failures
```

Interruption gate chỉ hợp lệ khi:

- cùng một Locust process chạy liên tục;
- `interruption_request_count > 0`;
- `customer_error_count = 0`;
- interruption requests vẫn nằm trong complete-run denominator;
- không cộng trùng 5xx/timeout/reset vào Locust failure count.

### 10.2 Graviton serving proof

Phải lưu:

- EC2 instance ID/type/architecture/Purchase Option;
- Kubernetes node + NodeClaim và label `kubernetes.io/arch=arm64`;
- eligible pod names, Ready state và image child digest;
- traffic window và request/trace/metric có denominator >0 gắn với workload đó.

Một ARM64 node không có customer-serving pod hoặc request không thỏa mandate.

### 10.3 Ba màn hình bắt buộc

1. **EC2 Instances:** Lifecycle/Purchase Option, instance type, architecture, launch/state/termination.
2. **Cost Explorer Usage Quantity:** Service EC2-Compute, Hours, grouped by Purchase Option rồi Instance Type; dùng sau reporting lag.
3. **Grafana live:** node count, request rate, Checkout/Browse/Cart success, Storefront p95 và interruption/recovery timeline.

Cost Explorer là corroboration theo giờ/ngày; nó không thay thế lifecycle calculation hoặc live Grafana/Locust.

## 11. Hard stop và rollback

### 11.1 Hard stop

Dừng phase ngay khi có một trong các điều kiện:

- Checkout <99%.
- Browse hoặc Cart <99.5%.
- Storefront p95 ≥1000 ms trong hai cửa sổ rolling 5 phút hợp lệ liên tiếp.
- Bất kỳ customer failure nào trong interruption interval.
- Request-volume difference baseline/optimized >5%.
- Locust bị reset/restart hoặc denominator/interruption request count không hợp lệ.
- Pending/FailedScheduling vượt allowance hoặc ảnh hưởng SLO.
- ResourceQuota chặn HPA, surge hoặc replacement.
- PDB không cho recovery hoặc serving endpoints thiếu.
- ARM64 exec-format, pull, startup hoặc readiness failure.
- OOMKilled, restart burst, throttling/node pressure regression ảnh hưởng serving capacity.
- Karpenter không tạo replacement, Spot starvation không recover hoặc interruption event không tới controller.
- Mất Locust/Grafana/Prometheus/Karpenter/EC2 signal cần cho verdict.
- Stateful/singleton/platform workload lên Spot.
- `flagd`/OpenFeature incident path bị disable hoặc bypass.

### 11.2 Rollback order

1. Dừng load an toàn nhưng giữ nguyên raw artifacts và timestamps.
2. Trả workload selector/toleration về protected AMD64 On-Demand qua previous-known-good GitOps revision.
3. Trả image digest known-good nếu lỗi liên quan image/ARM64.
4. Revert Terraform revision và tăng Managed Node Group về floor trước nếu lỗi capacity.
5. Xác minh nodes, Karpenter controller, critical replicas, PDB, endpoints, stateful services và observability.
6. Chạy Browse/Cart/Checkout smoke tests.
7. Ghi stop time UTC, trigger, operator, rollback revisions và recovery result.
8. Đánh dấu run **FAIL**; không dùng số liệu run đó cho baseline/optimized comparison.

## 12. Evidence layout

```text
docs/evidence/mandate13-compute-cost-optimization/
├── M13-PM-01-safe-compute-optimization-execution-plan.md
├── ADR-013-arm64-spot-capacity-decision.md
└── runtime/
    ├── baseline-<YYYYMMDDTHHMMSSZ>/
    ├── arm64-ondemand-canary-<YYYYMMDDTHHMMSSZ>/
    ├── spot-rehearsal-<YYYYMMDDTHHMMSSZ>/
    └── optimized-<YYYYMMDDTHHMMSSZ>/
        ├── metadata/
        ├── ci-supply-chain/
        ├── ec2/
        ├── kubernetes/
        ├── locust/
        ├── grafana/
        ├── interruption/
        ├── node-hour-calculation/
        ├── cost-explorer/
        └── final-verdict.md
```

Mỗi run lưu tối thiểu:

- Git SHA, Terraform/chart revision, image index và child digests;
- operator, reviewer, change ticket, UTC start/end/phase boundaries;
- nodes, NodeClaims, pods, HPA, PDB, endpoints, quota và events;
- EC2 lifecycle/type/architecture/Purchase Option;
- Locust stats/history/failures/exceptions và HTML;
- Grafana screenshots/video với UTC;
- Cost Explorer Usage Quantity khi dữ liệu xuất hiện;
- scan/SBOM/signature/attestation/verify artifacts cho cả AMD64 và ARM64.

## 13. Compliance matrix

| Mandate requirement | Gate | Bằng chứng | PASS |
|---|---|---|---|
| Variable low → high → low | Dùng nguyên 25→200→25, tối thiểu 60 phút | D13 contract, Locust history, UTC timeline | Đúng curve và duration |
| Cùng lượng tải | Raw complete-run requests | Locust CSV | Chênh ≤5% |
| Giảm node-hours | EC2 lifecycle overlap | EC2 timestamps + calculation | ≥30% |
| Spot | Spot hours / total optimized hours | EC2 + Cost Explorer Purchase Option | **>50%** |
| Graviton | ARM64 workload phục vụ traffic | EC2/node/pod/digest/request trace | Node-hours và request count >0 |
| Scale-up/down | HPA + NodeClaim + node lifecycle | Grafana/Karpenter/EC2 | Peak nodes tạo; peak-only nodes xóa ở low |
| Scheduler signals | Requests/HPA/quota fit | Metrics, HPA, quota, events | Không quota block/Pending/OOM |
| Checkout SLO | Complete run + interruption | Locust + Grafana | ≥99% |
| Browse/Cart SLO | Complete run + interruption | Locust + Grafana | ≥99.5% |
| Storefront latency | Rolling và complete run | Grafana/Locust | p95 <1 giây |
| Spot interruption | Provider-authentic event khi peak | Audit event + uninterrupted Locust + timeline | Request count >0; errors = 0 |
| Scale-down thật | Low observation exit gate | NodeClaims/EC2/Grafana | Node count về approved floor |
| Console evidence | Ba views mandate | Video/screenshots | Đủ EC2, CE Usage, Grafana |
| ADR | Signed decision | ADR-013 | Owner/reviewer/date đầy đủ |
| Guardrails | Network/flagd/budget | Terraform/config/evidence | Không regression |

## 14. RACI và change windows

| Role | Trách nhiệm |
|---|---|
| CDO04 Infrastructure/Cost | Terraform, pools, managed floor, EC2/node-hour/Cost Explorer evidence, infra rollback |
| CDO08 Reliability | PDB/replica/topology gate, SLO/interruption monitoring, stop authority, recovery verification |
| Application owners | ARM64 behavior, dependency readiness, image và workload rollback |
| CI/security owner | OCI index, per-architecture scan/SBOM/sign/attest/verify, promotion gate |
| On-call | Theo dõi alerts, quyết định stop, ghi timeline |
| Mentor/change approver | Gia hạn/change window, real interruption, floor reduction, ADR/final verdict |

Ba cửa sổ tách biệt:

1. **Build/IaC review:** không customer-impact test.
2. **Canary/rehearsal:** giữ toàn bộ rollback capacity.
3. **Final evidence:** baseline/optimized measurement và real interruption; lên lịch Cost Explorer follow-up sau reporting lag.

## 15. Dependency graph

```text
Approved extension/change ticket
  → freeze + valid On-Demand baseline
  → quota/AMI/Spot/interruption preflight
  → secure multi-arch index publish
  → protected + ARM64 canary + ARM64 elastic capacity
  → currency ARM64 On-Demand canary
  → remaining eligible ARM64 On-Demand batch
  → ARM64 Spot batch
  → simulated drain rehearsal
  → provider-authentic Spot interruption PASS
  → reduce managed floor
  → final optimized curve + repeat interruption
  → node-hour/Spot/SLO verdict
  → delayed Cost Explorer evidence
  → signed ADR and final sign-off
```

Local ARM64 build, idle ARM64 node, voluntary drain, Spot screenshot hoặc aggregate SLO đẹp không được bỏ qua các gate downstream.

## 16. Các file dự kiến thay đổi khi implementation được phê duyệt

Tài liệu này không sửa các file dưới đây. Một implementation PR sau dự kiến chạm tối thiểu:

- `infra/terraform/karpenter.tf` — interruption infrastructure đã verify.
- `infra/terraform/karpenter-nodepool.tf` — protected/canary/elastic capacity roles.
- `infra/terraform/eks.tf` — protected label và giảm managed floor sau gate.
- `deploy/build-push-images.sh` — một lần multi-platform Buildx publish.
- `.github/workflows/build-and-push.yaml` — QEMU khi cần, index/child verification và per-architecture security evidence.
- `techx-corp-chart/values.yaml` — placement qua existing `schedulingRules`, requests/resilience chỉ khi metrics chứng minh cần.
- GitOps values/digest file trong repository promotion — pin OCI index digest.
- `docs/evidence/mandate13-compute-cost-optimization/ADR-013-arm64-spot-capacity-decision.md`.
- Runtime evidence paths trong mục 12.

Không chỉnh `deploy/karpenter/*.yaml` cũ nếu Terraform là source of truth. Không tự ý khôi phục các load-test files đang bị xóa trong working tree.

## 17. Nguồn tham chiếu

### Repository

- `mandates/MANDATE-13-cost-efficiency-elastic.md`
- `docs/evidence/mandate13-compute-cost-optimization/jira-report/SPOT-ARM64-ELIGIBILITY-MATRIX.md`
- `docs/evidence/epic-09-compute-cost-optimization/D13-PERF-01-variable-load-curve-slo-contract.md`
- `infra/terraform/eks.tf`
- `infra/terraform/karpenter.tf`
- `infra/terraform/karpenter-nodepool.tf`
- `deploy/build-push-images.sh`
- `.github/workflows/build-and-push.yaml`
- `techx-corp-chart/templates/_objects.tpl`
- `techx-corp-chart/values.yaml`
- `techx-corp-chart/prometheus/flash-sale-alerts.yaml`
- `deploy/quota.yaml`

### AWS

- [Introducing multi-architecture container images for Amazon ECR](https://aws.amazon.com/blogs/containers/introducing-multi-architecture-container-images-for-amazon-ecr/)
- [Amazon EKS image security best practices](https://docs.aws.amazon.com/eks/latest/best-practices/image-security.html)
- [Using Amazon EC2 Spot Instances with Karpenter](https://aws.amazon.com/blogs/containers/using-amazon-ec2-spot-instances-with-karpenter/)
- [Applying Spot-to-Spot consolidation best practices with Karpenter](https://aws.amazon.com/blogs/compute/applying-spot-to-spot-consolidation-best-practices-with-karpenter/)

AWS references giải thích capability chung. AMI, quota, Spot availability, Karpenter v1.14.0, module behavior, interruption queue và FIS semantics phải được xác minh lại trong account ở preflight; link tài liệu không phải runtime evidence.