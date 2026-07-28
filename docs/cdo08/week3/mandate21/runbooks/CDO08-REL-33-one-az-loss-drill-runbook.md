# CDO08-REL-33 One-AZ Loss Drill Runbook

**Owner:** Quyết
**Mandate:** MANDATE-21 - DR Failover
**Status:** Draft usable now; REL-32 baseline incorporated
**Last updated:** 2026-07-28

## 1. Purpose

Runbook này quyết định `GO/NO-GO`, quan sát AZ loss dưới tải thật, ghi timestamp
để đo RTO/RPO và hard-stop khi evidence không còn đáng tin cậy.

Đây không phải node drain runbook. Observer không cordon, drain, delete, scale,
failover hoặc sửa AWS/Kubernetes resource. Mentor sở hữu fault injection và
thời điểm mất AZ.

RTO/RPO theo REL-28:

| Surface | Target |
| --- | ---: |
| Browse success | `>= 99.5%`, recovery `<= 5 phút` |
| Cart success | `>= 99.5%`, recovery `<= 5 phút` |
| Checkout success | `>= 99.0%`, recovery `<= 5 phút` |
| Confirmed orders | `RPO = 0` missing/duplicate |
| Accounting/fraud catch-up | `<= 10 phút` |

## 2. REL-32 baseline status

REL-32 đã merge qua commit `49a9e69f` và được đưa vào expected baseline REL-33.
Script tách baseline thành bốn biến:

```text
REQUIRED_DEPLOYMENTS
REQUIRED_TWO_AZ_DEPLOYMENTS
REQUIRED_PDBS
LOAD_GENERATOR_DEPLOYMENT
```

Nếu classification/topology thay đổi sau này, owner chỉ cập nhật bốn expected
values theo replica/PDB và waiver đã được duyệt. Observer loop, output và
hard-stop không cần viết lại.

Draft hiện dùng customer synchronous path từ REL-28:

```text
frontend-proxy frontend product-catalog cart checkout
payment shipping currency quote
```

Runtime check ngày 2026-07-28 xác nhận:

```text
cart zone topology: DoNotSchedule
cart Ready placement: us-east-1a + us-east-1b
```

Không chạy witnessed drill nếu preflight lại báo `cart` hoặc workload bắt buộc
không trải hai AZ.

## 3. Tool

```text
docs/cdo08/week3/mandate21/scripts/rel33-az-loss-observer.sh
```

Modes:

| Mode | Behavior | Exit |
| --- | --- | ---: |
| `preflight` | Chạy gates một lần và in `GO/NO-GO`. | `0` GO, `2` NO-GO |
| `observe` | Snapshot loop; dừng khi hard-stop hoặc hết duration. | `0` complete, `3` hard-stop |

Script chỉ dùng read-only APIs:

- `kubectl get/describe/exec`;
- Prometheus instant query;
- AWS `sts`, `rds describe`, `elasticache describe`, `kafka list/describe`.

Không cần hoặc đọc plaintext secret.

## 4. Required operator setup

Chạy từ Git Bash tại repository root:

```bash
export AWS_PROFILE=tf4-cdo08-admin
export AWS_REGION=us-east-1
export EXPECTED_AWS_ACCOUNT_ID=511825856493
export EXPECTED_KUBE_CONTEXT='arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster'
```

Xác nhận identity:

```bash
aws sts get-caller-identity \
  --profile "$AWS_PROFILE" \
  --query '[Account,Arn]' \
  --output table

kubectl config current-context
```

Sai account hoặc context là `NO-GO`.

## 5. Preflight gates

Chạy:

```bash
make rel33-preflight \
  REL33_AWS_PROFILE=tf4-cdo08-admin \
  REL33_OUTPUT=artifacts/rel33/preflight.log
```

Hoặc trực tiếp:

```bash
AWS_PROFILE=tf4-cdo08-admin \
EXPECTED_AWS_ACCOUNT_ID=511825856493 \
EXPECTED_KUBE_CONTEXT="$EXPECTED_KUBE_CONTEXT" \
bash docs/cdo08/week3/mandate21/scripts/rel33-az-loss-observer.sh \
  preflight --output artifacts/rel33/preflight.log
```

### 5.1 GO gates

Tất cả phải PASS:

- Đúng AWS account và EKS context.
- Không có pod mới `Pending`, not Ready, `CrashLoopBackOff`,
  `CreateContainerConfigError`, `ImagePullBackOff`, `ErrImagePull`, `OOMKilled`.
- Tất cả required deployment đạt desired/ready/available.
- Required workload có Ready pods ở ít nhất hai AZ.
- HPA `currentReplicas == desiredReplicas`, `AbleToScale=True`,
  `ScalingActive=True`.
- Required PDB tồn tại và `disruptionsAllowed >= 1`.
- ResourceQuota tồn tại, không có used value bằng hard limit.
- `load-generator` desired/ready/available.
- Grafana và Prometheus có Ready EndpointSlice.
- Prometheus có browse/cart/checkout metric và request rate `>= 0.01 req/s`.
- Baseline browse `>= 99.5%`, cart `>= 99.5%`, checkout `>= 99.0%`.
- RDS `available`, `MultiAZ=True`.
- Valkey `available`, Multi-AZ và automatic failover `enabled`.
- MSK `ACTIVE`.

Kết quả hợp lệ:

```text
preflight_result=GO failures=0
```

Mọi `NO-GO` phải được xử lý hoặc có waiver bằng văn bản từ Tech Lead/PM. Script
không tự bypass gate.

## 6. Start observer

Mở terminal riêng trước khi mentor inject fault:

```bash
make rel33-observe \
  REL33_AWS_PROFILE=tf4-cdo08-admin \
  REL33_INTERVAL=30 \
  REL33_DURATION=1800 \
  REL33_OUTPUT=artifacts/rel33/observer.log
```

`REL33_DURATION=0` chạy tới khi nhấn `Ctrl+C`.

Mỗi iteration ghi:

- UTC timestamp;
- node readiness, capacity type và AZ;
- pod readiness/node placement;
- HPA;
- PDB;
- ResourceQuota;
- 40 warning events gần nhất;
- RDS/Valkey/MSK state;
- request rate và browse/cart/checkout SLO.

Trong `observe`, SLO xuống dưới threshold là tín hiệu cần đo chứ không phải
hard-stop. Script ghi:

```text
slo_dip_detected surface=<browse|cart|checkout> timestamp=<UTC>
slo_recovered surface=<browse|cart|checkout> timestamp=<UTC>
```

Observer tiếp tục chạy qua failure window để hai timestamp này dùng tính RTO.

Trước fault injection, operator ghi vào chat/evidence:

```text
PRECHECK GO timestamp=<UTC>
observer_log=<path>
mentor_fault_start=<pending>
```

Khi mentor xác nhận thời điểm fault:

```bash
printf '%s mentor_fault_start az=<AZ>\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  | tee -a artifacts/rel33/observer.log
```

Không đo RTO từ lúc chạy script; đo từ mentor fault timestamp hoặc SLO dip theo
REL-28.

## 7. Hard-stop gates

Observer dừng với exit `3` khi có:

- Pending/CrashLoop/OOM/ImagePull/config error mới;
- load-generator không còn Ready;
- request volume hoặc Prometheus metrics mất;
- RDS, Valkey hoặc MSK unhealthy.

SLO baseline dưới threshold chỉ là `NO-GO` trong `preflight`. Trong `observe`,
SLO dip được ghi nhận và theo dõi đến recovery, không kích hoạt hard-stop.

Output:

```text
hard_stop=<gate> status=TRIGGERED ...
observer_result=HARD-STOP ...
```

Khi hard-stop:

1. Thông báo mentor: `STOP REL-33 evidence invalid/unhealthy`.
2. Không inject fault mới và không tự thay đổi fault do mentor sở hữu.
3. Giữ observer log, dashboard screenshot và exact UTC timestamp.
4. Chuyển sang rollback/escalation.

## 8. Recovery and RTO

Recovery đạt khi:

- required deployments có endpoint Ready ở AZ lành;
- browse/cart/checkout trở lại ngưỡng và ổn định đủ cửa sổ 5 phút;
- RDS/Valkey/MSK healthy;
- accounting/fraud lag catch up trong 10 phút;
- reconcile confirmed orders không missing/duplicate.

Tính:

```text
RTO = stable_slo_recovery_timestamp - mentor_fault_start
```

Nếu mentor không cung cấp timestamp:

```text
RTO = stable_slo_recovery_timestamp - first_slo_dip_timestamp
```

Observer cung cấp infrastructure timeline; REL-34 dashboard và reconcile
tooling cung cấp SLO/RPO business evidence.

## 9. Rollback and escalation

Observer không tạo cloud resource nên cleanup bình thường chỉ là:

```bash
Ctrl+C
```

Fault rollback do mentor/platform owner thực hiện. Sau khi mentor xác nhận AZ
đã phục hồi:

```bash
bash docs/cdo08/week3/mandate21/scripts/rel33-az-loss-observer.sh \
  preflight --output artifacts/rel33/post-rollback.log
```

Escalation:

| Condition | Escalate |
| --- | --- |
| EKS scheduling/readiness/PDB/quota | Platform/Kubernetes owner |
| RDS not `available` | RDS owner + Tech Lead |
| Valkey failover unhealthy | Cart/Valkey owner + Tech Lead |
| MSK not `ACTIVE`, lag not recovering | Kafka owner + CDO08 Reliability |
| SLO below target with healthy infra | Service owner + SRE/observability |
| Missing/duplicate confirmed order | Incident commander; freeze drill evidence and start reconciliation |

Không rollback production bằng command ad hoc trong runbook này.

## 10. Evidence checklist

- [ ] Preflight log có `GO`.
- [ ] Observer start timestamp.
- [ ] Mentor fault timestamp và AZ.
- [ ] Node/pod placement trước, trong và sau fault.
- [ ] HPA/PDB/quota snapshots.
- [ ] Warning events.
- [ ] RDS/Valkey/MSK timeline.
- [ ] Request volume và SLO timeline.
- [ ] Stable recovery timestamp và RTO calculation.
- [ ] Reconcile confirmed orders, missing `0`, duplicate `0`.
- [ ] Accounting/fraud catch-up duration.
- [ ] Rollback/post-check log.
- [ ] Mọi mismatch có remediation owner/item.

## 11. Baseline change checklist

Khi REL-32 hoặc workload classification có thay đổi tiếp:

1. Đọc manifest/runtime mới.
2. Cập nhật required deployment, two-AZ và PDB lists.
3. Ghi waiver cho intentional single-replica accounting/fraud nếu còn.
4. Chạy lại `make rel33-preflight`.
5. Cập nhật runbook khi output phản ánh baseline mới.

References:

- `../adr/CDO08-REL-28-az-failure-rto-rpo-adr.md`
- `../adr/CDO08-REL-28-revenue-path-scope.md`
- `../scan/CDO08-REL-29-multi-az-runtime-baseline.md`
- `../scan/CDO08-REL-29-az-failure-gap-register.md`
- `../evidence/CDO08-REL-31-msk-failover-readiness.md`
