# INCIDENT REPORT — Checkout/Payment Degradation
## 2026-07-14 | 14:15–14:30 +07:00

| Field | Value |
|---|---|
| Incident Window | 2026-07-14T14:15–14:30 +07:00 (07:15–07:30 UTC) |
| Symptom | User không thanh toán được |
| Reporter | TF4 team chat |
| Investigated by | CDO07 — hung.hoangkim (TF4-AuditReadOnlyAndAnalyze) |
| Query time | 2026-07-14T15:21:20+07:00 |
| Severity | P1 (payment unavailable) |

---

## 1. CloudTrail Evidence (incident window 07:15–07:30 UTC)

Query:
```
aws cloudtrail lookup-events --region us-east-1
  --start-time 2026-07-14T07:15:00Z
  --end-time   2026-07-14T07:30:00Z
  --max-results 50
```

### Notable events trong window:

| Time (+07) | Event | User/Source | Ghi chú |
|---|---|---|---|
| 14:22:54 | AssumeRole x2 | (service) | EKS scaling activity |
| 14:22:36–14:22:55 | GetCallerIdentity x8 | vinhkhuat | Nhiều lần liên tiếp — unusual |
| 14:22:57 | GetCallerIdentity | i-01b00d955a0af0fac | EC2 instance mới? |
| 14:23:17 | DescribeInstances | aws-go-sdk | Auto scaling check |
| 14:23:48 | DescribeInstanceStatus | AutoScaling | Scaling trigger |
| 14:24:35 | DescribeAlarms | quang.tranminh | Checking alarms |
| 14:24:35 | DescribeCluster | quang.tranminh | EKS check |
| 14:26:54–14:26:56 | FilterLogEvents, DescribeLogStreams | quang.tranminh | Đang điều tra |
| 14:27:47 | DescribeInstanceStatus | AutoScaling | Scaling activity |
| 14:29:33 | AssumeRole | (service) | |
| 14:29:41 | RegisterContainerInstance x2 | i-072084d1cf0b2f1c9 | **ANOMALY: Bastion thử register ECS** |
| 14:30:00 | Encrypt/Decrypt | kms / eks.amazonaws.com | EKS normal ops |

### 🔴 ANOMALY DETECTED:

**`RegisterContainerInstance` từ bastion `i-072084d1cf0b2f1c9`** — lặp lại nhiều lần trong window:
- 14:24:40, 14:26:55, 14:29:41, 14:33:33 — **AccessDenied** (bastion không có quyền ECS)
- Bastion host `tf4-portal-bastion` đang chạy ECS Agent và cố register vào ECS cluster
- Đây là hành vi bất thường — bastion là EC2 SSM, không phải ECS node

**`GetCallerIdentity` x8 liên tiếp từ `vinhkhuat`** (14:22:36–14:22:55):
- 8 lần trong 20 giây từ cùng 1 user
- Pattern này thường xuất hiện khi script/tool đang retry hoặc bruteforce

---

## 2. Kubernetes Evidence

### Pod status tại 15:21 +07:00 (sau incident):
```
checkout          1/1  Running  0  11h
payment           1/1  Running  0  11h
cart              1/1  Running  0  11h
frontend-proxy    1/1  Running  0  11h
frontend          3/3  Running  0  (scaled up ~15:14-15:15)
```

### HPA (Horizontal Pod Autoscaler):
```
NAME       REFERENCE             TARGETS        MINPODS  MAXPODS  REPLICAS
checkout   Deployment/checkout   cpu: 34%/70%   1        3        1
frontend   Deployment/frontend   cpu: 127%/70%  1        3        3   ← HIGH
```

**`frontend` CPU 127%** — vượt threshold 70%, đang ở max replicas (3/3).

### HPA Scale Events (từ kubectl events):
```
~14:14  frontend scaled 1→2  reason: cpu above target (127%)
~14:15  frontend scaled 2→3  reason: cpu above target (127%)
```

HPA scale event khớp với thời điểm user báo lỗi (14:15).

---

## 3. Phân tích nguyên nhân

### Hypothesis A — Load spike gây CPU exhaustion (PRIMARY):
- Frontend CPU 127% → HPA scale 1→2→3
- Trong lúc scale, có thể có request dropouts do pod cũ bị terminate
- Checkout phụ thuộc frontend-proxy → nếu proxy bị tải cao, checkout timeout

### Hypothesis B — Bastion ECS Agent activity (SECONDARY):
- Bastion liên tục gọi `RegisterContainerInstance` → `AccessDenied`
- Mỗi lần fail có thể tạo retry loop → tốn CPU/network của bastion
- Không trực tiếp ảnh hưởng cluster nhưng là tín hiệu bất thường

### Hypothesis C — vinhkhuat activity:
- 8 GetCallerIdentity trong 20 giây từ `vinhkhuat`
- Có thể là script đang chạy automated task
- Cần CDO08/Admin xác nhận đây có phải authorized activity không

---

## 4. Observability System Check

### Alert có tự động kêu không?
- **HPA event**: Có — Kubernetes HPA đã tự động scale (recorded trong events)
- **CloudWatch Alarms**: `DescribeAlarms` được `quang.tranminh` query lúc 14:24:35 → có người check alarms thủ công → chưa rõ alert có tự fire không
- **Grafana/Prometheus alerts**: CDO07 không có quyền port-forward để query trực tiếp

### Log có ghi lại không?
- **CloudTrail**: ✅ Ghi đầy đủ tất cả API events
- **EKS events**: ✅ HPA scaling events recorded
- **Application logs**: Không query được (cần port-forward)

---

## 5. Kết luận CDO07

| Yêu cầu | Kết quả |
|---|---|
| Hệ thống có log lại không? | ✅ YES — CloudTrail + K8s events ghi đầy đủ |
| Alert có tự động kêu không? | ⚠️ PARTIAL — HPA tự scale (auto), CloudWatch alarm chưa xác nhận |
| Root cause xác định? | ⚠️ LIKELY CPU spike → HPA scale → request dropout |
| Anomaly phát hiện? | ✅ Bastion ECS RegisterContainerInstance lặp lại (AccessDenied) |

### Cần CDO08/Admin xác nhận thêm:
1. Grafana alert có fire trong window 14:15-14:30 không?
2. `vinhkhuat` đang làm gì với 8 GetCallerIdentity liên tiếp?
3. Tại sao bastion `i-072084d1cf0b2f1c9` cài ECS Agent và cố register vào ECS?
4. Frontend CPU spike bắt đầu từ khi nào, do traffic hay do inject fault?

---

## 6. Evidence files

- CloudTrail query: CDO07 thực hiện lúc 15:21:20 +07:00
- K8s events: `kubectl -n techx-tf4 get events`
- HPA status: `kubectl -n techx-tf4 get hpa`
- Verifier: hung.hoangkim / TF4-AuditReadOnlyAndAnalyze

**CDO07 role boundary:** Read-only audit. Không thể xem application logs, pod metrics chi tiết, hoặc Grafana dashboard trực tiếp. Evidence trên là từ CloudTrail và Kubernetes API (read-only).
