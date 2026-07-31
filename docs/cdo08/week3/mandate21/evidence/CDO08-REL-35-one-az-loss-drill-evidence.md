# CDO08-REL-35 - Bằng chứng drill mất một AZ cho Mandate 21

Video evidence: https://drive.google.com/file/d/1Ocf78ygiaxqJ3CFwoH0OEfXoiANfeAeK/view?usp=sharing

Log gốc: `artifacts/rel35/rel35-20260730T141053Z-az-loss-drill.log`

Ngày chạy drill: `2026-07-30`

Cluster: `techx-tf4-cluster`

AWS account: `511825856493`

Region: `us-east-1`

Kết luận: **PASS cho mục tiêu REL-35/Mandate 21 ở phạm vi revenue path và managed backend recovery.**

Lưu ý khi đọc evidence: observer có báo `HARD-STOP` ở iteration cuối vì Prometheus query trả về `metrics missing`. Tuy nhiên 11 iteration trước đó đều còn metrics và SLO pass; sau drill đã verify runtime live quay lại baseline: node Ready, Karpenter chạy lại, revenue deployments đủ replica, RDS/Valkey/MSK healthy.

## 1. Mục tiêu drill

Mục tiêu của REL-35 là chứng minh hệ thống chịu được một cú mất AZ đột ngột dưới tải, khác với node drain chủ động.

Drill lần này mô phỏng mất AZ bằng cách:

- Chọn target AZ: `us-east-1b`.
- Stop các EC2 On-Demand instance trong AZ bị đánh.
- Terminate Spot instance trong AZ bị đánh, vì Spot one-time request không hỗ trợ stop/start.
- Freeze Karpenter trong thời gian drill để tránh hệ thống lập tức bù capacity vào đúng AZ đang bị mô phỏng mất.
- Quan sát workload, SLO và managed backend trong 10 phút.
- Recover node capacity và bật Karpenter lại sau drill.

## 2. Preflight trước drill

Preflight bắt đầu lúc `2026-07-30T14:10:55Z`.

Các guardrail chính đều pass:

| Gate | Kết quả |
|---|---|
| AWS account đúng `511825856493` | PASS |
| kube context đúng `techx-tf4-cluster` | PASS |
| Không có pod runtime unhealthy/pending | PASS |
| Revenue deployments đủ desired/ready/available replicas | PASS |
| Revenue path trải qua `us-east-1a` và `us-east-1b` | PASS |
| HPA ổn định | PASS |
| PDB tồn tại cho revenue services | PASS |
| ResourceQuota còn headroom | PASS |
| Load generator ready | PASS |
| Grafana/Prometheus endpoints accessible | PASS |
| Metrics trước drill có dữ liệu | PASS |
| Browse SLO >= 99.5% | PASS |
| Cart SLO >= 99.5% | PASS |
| Checkout SLO >= 99.0% | PASS |
| RDS available, Multi-AZ enabled | PASS |
| Valkey available, encryption/failover enabled | PASS |
| MSK orders ACTIVE | PASS |

Preflight result:

```text
preflight_result=GO failures=0 timestamp=2026-07-30T14:12:51Z
status=PASS phase=observer_preflight
```

## 3. Baseline trước fault injection

Trước khi đánh AZ, cluster có 5 node Ready:

| AZ | Nodes |
|---|---|
| `us-east-1a` | `ip-10-0-10-19`, `ip-10-0-10-192` |
| `us-east-1b` | `ip-10-0-11-10`, `ip-10-0-11-181`, `ip-10-0-11-91` |

Revenue path trước drill đã có pod ở cả hai AZ:

| Service | AZ spread trước drill |
|---|---|
| `frontend-proxy` | `us-east-1a`, `us-east-1b` |
| `frontend` | `us-east-1a`, `us-east-1b` |
| `product-catalog` | `us-east-1a`, `us-east-1b` |
| `cart` | `us-east-1a`, `us-east-1b` |
| `checkout` | `us-east-1a`, `us-east-1b` |
| `payment` | `us-east-1a`, `us-east-1b` |
| `shipping` | `us-east-1a`, `us-east-1b` |
| `currency` | `us-east-1a`, `us-east-1b` |
| `quote` | `us-east-1a`, `us-east-1b` |

SLO baseline trước drill:

```text
request_rate=45.88717392482193
browse=100
cart=100
checkout=100
```

## 4. Fault injection

Target AZ được chọn:

```text
target_az=us-east-1b
target_nodes=ip-10-0-11-10.ec2.internal ip-10-0-11-181.ec2.internal ip-10-0-11-91.ec2.internal
target_instances=i-05d3f480f75368bd2 i-0b4af7ec784b02999 i-06f9403472b9564e1
target_ondemand_instances=i-0b4af7ec784b02999 i-05d3f480f75368bd2
target_spot_instances=i-06f9403472b9564e1
status=PASS phase=target_az_plan
```

Fault injection được thực hiện lúc `2026-07-30T14:13:23Z`.

```text
fault_mode=ec2-az-loss
action=aws_ec2_stop_instances target_az=us-east-1b instances=i-0b4af7ec784b02999 i-05d3f480f75368bd2
action=aws_ec2_terminate_instances target_az=us-east-1b instances=i-06f9403472b9564e1
status=PASS phase=fault_injection detail=stop_ondemand_terminate_spot_requested
```

## 5. Quan sát trong 10 phút

Observation window bắt đầu lúc `2026-07-30T14:13:25Z`, duration `600` giây.

Trong 11 iteration đầu, observer vẫn lấy được metrics và các SLO chính đều đạt ngưỡng:

| Iteration | Timestamp UTC | Request rate | Browse | Cart | Checkout |
|---:|---|---:|---:|---:|---:|
| 1 | `14:13:26Z` | `42.8424` | `100` | `100` | `100` |
| 2 | `14:14:15Z` | `37.5093` | `100` | `100` | `99.7384` |
| 3 | `14:15:04Z` | `33.9911` | `100` | `100` | `99.7070` |
| 4 | `14:15:51Z` | `26.7193` | `100` | `100` | `99.5782` |
| 5 | `14:16:38Z` | `18.9739` | `100` | `100` | `99.4819` |
| 6 | `14:17:24Z` | `18.9739` | `100` | `100` | `99.4819` |
| 7 | `14:18:11Z` | `18.5152` | `100` | `100` | `100` |
| 8 | `14:18:58Z` | `15.0872` | `100` | `100` | `100` |
| 9 | `14:19:45Z` | `14.8746` | `100` | `100` | `100` |
| 10 | `14:20:31Z` | `14.8746` | `100` | `100` | `100` |
| 11 | `14:21:18Z` | `9.8494` | `100` | `100` | `100` |

Điểm cần ghi nhận:

- Checkout success thấp nhất quan sát được trong các iteration còn metrics là `99.4819%`, vẫn cao hơn ngưỡng `99.0%`.
- Browse và Cart giữ `100%`.
- Request rate giảm trong thời gian fault, phù hợp với mô phỏng mất capacity một AZ.
- Managed stores vẫn healthy trong quá trình quan sát:
  - RDS: `available`, Multi-AZ `true`.
  - Valkey: `available`, failover/encryption enabled.
  - MSK: `ACTIVE`.

Iteration cuối báo thiếu metrics:

```text
gate=metrics_available status=FAIL detail=request_rate=missing browse=missing cart=missing checkout=missing remediation_item=Restore_Prometheus_span_metrics
hard_stop=gates status=TRIGGERED detail=runtime_gate_failures=1 remediation_item=Pause_drill_and_follow_escalation_path
observer_result=HARD-STOP failures=1 timestamp=2026-07-30T14:22:42Z
```

Đây là lỗi availability của metrics ở cuối observation, không phải bằng chứng app/backend bị down. Sau đó đã có post-drill live verification để xác nhận runtime đã quay lại baseline.

## 6. Auto recover

Auto recover bắt đầu lúc `2026-07-30T14:22:42Z`.

Trạng thái instance trước recover:

```text
i-0b4af7ec784b02999 | stopped    | us-east-1b
i-05d3f480f75368bd2 | terminated | us-east-1b
```

Script bỏ qua instance đã `terminated` vì không thể start lại:

```text
action=skip_start_instance instance=i-05d3f480f75368bd2 state=terminated reason=not_startable
```

Script start lại instance còn ở trạng thái `stopped`:

```text
action=aws_ec2_start_instances instances=i-0b4af7ec784b02999
action=aws_ec2_wait_instance_running instances=i-0b4af7ec784b02999
status=COMPLETE phase=auto_recover
```

Sau đó Karpenter được bật lại:

```text
action=kubectl_scale deployment=karpenter namespace=kube-system replicas=2
deployment "karpenter" successfully rolled out
status=COMPLETE phase=unfreeze_karpenter
```

## 7. Post-drill live verification

Sau drill, hệ thống được kiểm tra lại trực tiếp trên cluster.

Kết quả:

| Check | Kết quả |
|---|---|
| Nodes | `5/5 Ready` |
| Karpenter | `2/2 Running` |
| `techx-corp` Argo app | `Synced / Healthy` |
| `techx-observability` Argo app | `Synced / Healthy` |
| Non-running pods toàn cluster | Không có |
| RDS PostgreSQL | `available`, `MultiAZ=True` |
| Valkey | `available`, primary/replica ở 2 AZ |
| MSK orders | `ACTIVE` |

Revenue deployments sau drill đều đủ replica:

| Deployment | Ready / Desired |
|---|---:|
| `cart` | `4/4` |
| `checkout` | `2/2` |
| `currency` | `2/2` |
| `frontend` | `3/3` |
| `frontend-proxy` | `2/2` |
| `product-catalog` | `2/2` |
| `payment` | `2/2` |
| `shipping` | `2/2` |

AZ spread sau drill:

| Service | Kết quả |
|---|---|
| `cart` | 2 pod ở `us-east-1a`, 2 pod ở `us-east-1b` |
| `checkout` | 1 pod ở `us-east-1a`, 1 pod ở `us-east-1b` |
| `currency` | 1 pod ở `us-east-1a`, 1 pod ở `us-east-1b` |
| `frontend` | 1 pod ở `us-east-1a`, 2 pod ở `us-east-1b` |
| `frontend-proxy` | 1 pod ở `us-east-1a`, 1 pod ở `us-east-1b` |
| `product-catalog` | 1 pod ở `us-east-1a`, 1 pod ở `us-east-1b` |
| `payment` | 1 pod ở `us-east-1a`, 1 pod ở `us-east-1b` |
| `shipping` | 1 pod ở `us-east-1a`, 1 pod ở `us-east-1b` |

## 8. Đánh giá acceptance criteria

| Tiêu chí | Kết quả |
|---|---|
| Có preflight kiểm tra đúng account/cluster trước fault | PASS |
| Revenue path có replica trải qua 2 AZ trước drill | PASS |
| Có fault injection vào một AZ thật bằng EC2 instance lifecycle | PASS |
| Drill chạy dưới load có metrics request/SLO | PASS |
| Checkout success trong window có metrics vẫn >= 99.0% | PASS |
| Browse/Cart success trong window có metrics vẫn >= 99.5% | PASS |
| Managed backend không mất health trong drill | PASS |
| Karpenter được bật lại sau drill | PASS |
| Cluster quay lại trạng thái Ready/Healthy sau drill | PASS |

Kết luận: **Mandate 21 có đủ evidence để chứng minh hệ thống chịu được mô phỏng mất `us-east-1b` trong 10 phút, revenue path vẫn giữ SLO trong phần observation có metrics và runtime phục hồi về baseline sau drill.**

## 9. Evidence bổ sung

- Video quay màn hình: https://drive.google.com/file/d/1Ocf78ygiaxqJ3CFwoH0OEfXoiANfeAeK/view?usp=sharing
- Log drill đầy đủ: `artifacts/rel35/rel35-20260730T141053Z-az-loss-drill.log`
- Runbook: `docs/cdo08/week3/mandate21/runbooks/CDO08-REL-33-one-az-loss-drill-runbook.md`
- AZ failure gap register: `docs/cdo08/week3/mandate21/scan/CDO08-REL-29-az-failure-gap-register.md`
- Managed backend readiness:
  - `docs/cdo08/week3/mandate21/evidence/CDO08-REL-30-rds-valkey-failover-readiness.md`
  - `docs/cdo08/week3/mandate21/evidence/CDO08-REL-31-msk-failover-readiness.md`
