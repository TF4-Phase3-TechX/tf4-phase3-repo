# D18-COST-05 — Xác minh mức giảm usage ngoài compute và top cost driver

> Owner: CDO-04 (Performance & Cost)  
> Primary verdict: **CONDITIONAL PASS**  
> Primary metric: usage units; không dùng USD làm verdict chính.

## 1. Evidence source và measurement windows

| Nguồn | Window / nội dung |
|---|---|
| D18-COST-01 | Live inventory `2026-07-22T04:19:53Z`–`2026-07-22T04:21:07Z`; Cost Explorer `[2026-07-15T00:00:00Z, 2026-07-22T00:00:00Z)` |
| D18-COST-02 | Orphan inventory `2026-07-21T14:41:23Z`, after execution record `2026-07-25T15:55:00Z` |
| D18-COST-03 | EBS/storage baseline cùng live inventory D18-COST-01 |
| D18-COST-04 | NAT/cross-AZ baseline và destination analysis |
| D18-PLAT-01 | Endpoint apply `2026-07-25T03:28:06Z`–`2026-07-25T03:37:12Z`; after NAT sample đến `2026-07-25T16:10:00Z` |

## 2. Top cost drivers

Trước thay đổi, top usage drivers ngoài compute là:

1. Orphan candidates: EIP, Released-PV EBS và snapshot chain.
2. gp2 provisioned storage và snapshot lifecycle.
3. NAT gateway data path.

Sau thay đổi, reduction evidence chắc chắn nhất là orphan/unattached EBS và số lượng GP2 giảm về 0. NAT AWS-service traffic mới chỉ có runtime signal không matched; Interface Endpoint cost không được dùng làm primary verdict; STS/SSM được giữ vì security và operational boundary.

## 3. Before/after usage matrix

| Cost driver | Unit | Before | After | Delta | Verdict | Evidence |
|---|---:|---:|---:|---:|---|---|
| Unattached EBS | count / GiB | 4 available volumes / 35 GiB | 0 available volumes / 0 GiB | Giảm về 0 | REDUCED | D18-COST-01, D18-COST-02, after-readonly |
| gp2 storage | provisioned GiB | 5 volumes / 75 GiB gp2 | 0 gp2; 290 GiB total provisioned | GP2 eliminated; total GiB tăng | MIXED / NO RIGHT-SIZE CLAIM | D18-COST-03, after-readonly |
| Snapshot storage | count / logical GiB | 9 self-owned snapshots / 76 GiB logical source size | 4 / 216 GiB logical source size | Count giảm; logical GiB tăng | MIXED | D18-COST-01, D18-COST-03, after-readonly |
| NAT processing | bytes, matched 13.53-hour windows | 79,063,981 bytes | 83,768,702 bytes | **+5.95%** | NO REDUCTION EVIDENCE | D18-PLAT-01 §5, after-readonly |
| Metrics series | count | 179,044 active series; 3,535.45 samples/s | 208,592 active series; 33,287.225 samples/s | Tăng | NO REDUCTION EVIDENCE | D18-PERF-01, after-readonly |

## 4. Confirmed runtime evidence

| Validation | Trạng thái | Ghi chú |
|---|---|---|
| Logs / Flow Logs | PASS | `FlowLogStatus=ACTIVE`, `DeliverLogsStatus=SUCCESS` |
| Request investigation | PASS có điều kiện | Có DNS, route, ECR, SSM, Logs và NAT lookup path |

## 5. Orphan và resource decision

- D18-COST-02 đã ghi nhận owner và decision cho các EBS, EIP và snapshot candidates.
- Không coi volume `Bound` hoặc recovery snapshot là orphan nếu chưa có owner/rollback decision.
- After-scan phải ghi rõ `REDUCED`, `NO CHANGE`, `RETAIN` hoặc `EXCEPTION` kèm owner và expiry.

## 6. Acceptance criteria

| Tiêu chí | Trạng thái | Evidence / lý do |
|---|---|---|
| Top driver trước thay đổi được xác định | ✅ PASS | D18-COST-01 ranking |
| Ít nhất một storage metric giảm | ✅ PASS có điều kiện | Available EBS `35 GiB → 0 GiB`; tổng provisioned GiB không giảm |
| Không dùng USD làm primary verdict | ✅ PASS | Ma trận dùng count, GiB, GB/day, spans/s, series |
| Investigation capability PASS | ✅ PASS có điều kiện | Có runtime lookup paths; thiếu after dashboard/query artifacts |
| Không còn orphan chưa được giải thích | ✅ PASS có điều kiện | 17-region after-scan không còn EBS/EIP/AMI orphan; 4 snapshot cần owner/expiry |

## 7. After read-only collection (2026-07-25)

Artifact chi tiết: [after-readonly-2026-07-25.md](./after-readonly-2026-07-25.md).

Kết quả live sau cleanup và endpoint apply:

- Account-wide enabled-region scan (17 regions): `us-east-1` còn 7 volume,
  `0 available / 0 GiB`, `0` unassociated EIP, `0` self-owned AMI; 16 region
  còn lại không có volume/snapshot/EIP rời/AMI.
- Snapshot còn `4` (baseline `9`), nhưng logical source size `216 GiB`
  (baseline `76 GiB`) do migration backup mới; chỉ claim count reduction.
- GP2 còn `0` (baseline `5 / 75 GiB`); provisioned total hiện tại
  `290 GiB` nên không claim total storage reduction/right-sizing.
- NAT matched window `2026-07-24T13:54:07Z`–`2026-07-25T03:28:00Z` versus
  `2026-07-25T03:28:00Z`–`2026-07-25T17:01:53Z`: `79,063,981` → `83,768,702`
  bytes (`+5.95%`).
- Prometheus after snapshot: `208,592` active series, `33,287.225/s` samples,
  `4.802 GB` blocks; đều cao hơn baseline.
- Flow Logs `ACTIVE/SUCCESS`; group có `storedBytes=0`.
- Storefront runtime evidence đã được thu thập trong cùng after collection.

Verdict sau collection vẫn **CONDITIONAL PASS**.

## 8. Rollback

Nếu correctness, SLO hoặc operational access regression: revert Terraform source revision, chạy `terraform plan` xác nhận destroy scope, apply trong change window, sau đó kiểm tra NAT route cũ, DNS, ECR pull, SSM và logging.
