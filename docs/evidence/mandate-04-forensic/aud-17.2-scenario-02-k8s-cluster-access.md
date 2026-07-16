# Scenario 02 — K8s Cluster Access
## AUD-17.2 · Forensic Drill Scenario Design

| Field | Giá trị |
|---|---|
| Scenario ID | AUD-17.2-S02 |
| Loại | K8s cluster access — ConfigMap update / Pod delete |
| Nguồn log | K8s Audit Log — CloudWatch `/aws/eks/techx-tf4-cluster/cluster` |
| Độ khó | Dễ–Trung bình |
| Target thời gian | ≤7 phút |
| Tác giả | Ty (CDO07) |
| Ngày | 2026-07-15 |

---

## Mô tả kịch bản

**Tình huống mentor đưa ra:**
> "Ai đã thay đổi ConfigMap trong cluster lúc ~14:25 ngày 14/07?"

Hoặc:
> "Pod nào bị xóa thủ công? Ai làm?"

**Loại event cần trace:**
- ConfigMap `update` / `patch` — thay đổi cấu hình trong cluster
- Pod `delete` — xóa pod thủ công (không phải do deployment rollout)
- `pods/portforward` `create` — mở tunnel kubectl vào pod

**Lý do dùng K8s Audit Log:** Đây là hành động trong cluster qua kubectl hoặc K8s API — xuất hiện trong K8s audit log, không trong CloudTrail. Rule phân loại: hành động trong cluster → K8s Audit Log.

---

## Data thật đã có (từ incident 14/07)

> **Sự kiện thật:** `phuong` + bastion `i-072084d1cf0b2f1c9` kubectl port-forward vào Grafana/Jaeger lúc 14:25–14:27 +07 ngày 14/07/2026. Evidence đã commit tại `docs/audit/postmortems/evidence_incident.jpg`.

---

## Query cụ thể

### Query A — ConfigMap update (generic)

```bash
# Epoch: 2026-07-14T07:00:00Z = 1752382800000
# Epoch: 2026-07-14T08:00:00Z = 1752386400000

aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time 1752382800000 \
  --end-time 1752386400000 \
  --filter-pattern '"configmaps"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.objectRef.resource == "configmaps")
        | select(.verb | IN("update", "patch", "create", "delete"))
        | select(.user.username | test("system:") | not)
        | {
            time:      .requestReceivedTimestamp,
            user:      .user.username,
            verb:      .verb,
            object:    .objectRef.name,
            namespace: .objectRef.namespace,
            userAgent: .userAgent,
            status:    .responseStatus.code
          }'
```

### Query B — Pod delete thủ công

```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_EPOCH_MS \
  --end-time END_EPOCH_MS \
  --filter-pattern '"delete" "pods"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.verb == "delete")
        | select(.objectRef.resource == "pods")
        | select(.user.username | test("system:") | not)
        | {
            time:      .requestReceivedTimestamp,
            user:      .user.username,
            pod:       .objectRef.name,
            namespace: .objectRef.namespace,
            userAgent: .userAgent
          }'
```

### Query C — kubectl port-forward (đã dùng trong drill)

```bash
# Epoch: 14:20 +07 = 07:20 UTC = 1752384000000
# Epoch: 14:35 +07 = 07:35 UTC = 1752384900000

aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time 1752384000000 \
  --end-time 1752384900000 \
  --filter-pattern '"portforward"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | {
            time:     .requestReceivedTimestamp,
            user:     .user.username,
            verb:     .verb,
            resource: .objectRef.resource,
            name:     .objectRef.name
          }'
```

---

## Output thật từ hệ thống (Query C — đã verified)

```json
{ "time": "2026-07-14T07:25:39Z", "user": "phuong", "verb": "create", "resource": "pods/portforward", "name": "grafana-b9fc94c47-..." }
{ "time": "2026-07-14T07:25:30Z", "user": "tf4-portal-bastion-role/i-072084d1cf0b2f1c9", "verb": "create", "resource": "pods/portforward", "name": "grafana-b9fc94c47-..." }
{ "time": "2026-07-14T07:25:42Z", "user": "tf4-portal-bastion-role/i-072084d1cf0b2f1c9", "verb": "create", "resource": "pods/portforward", "name": "jaeger-5f4f88c5a8-..." }
{ "time": "2026-07-14T07:27:18Z", "user": "tf4-portal-bastion-role/i-072084d1cf0b2f1c9", "verb": "create", "resource": "pods/portforward", "name": "grafana-b9fc94c47-..." }
{ "time": "2026-07-14T07:27:18Z", "user": "tf4-portal-bastion-role/i-072084d1cf0b2f1c9", "verb": "create", "resource": "pods/portforward", "name": "jaeger-5f4f88c588-..." }
```

---

## Trả lời forensic mẫu (dùng data thật)

```
WHO:   phuong (TF4-SecReliabilityReadOnlyAudit) và bastion i-072084d1cf0b2f1c9
       (tf4-portal-bastion-role)

WHAT:  kubectl port-forward vào pod Grafana và Jaeger
       K8s verb = "create" trên resource "pods/portforward"
       → Hành động điều tra incident, không phải thay đổi cấu hình

WHEN:  2026-07-14T07:25:30Z → 07:27:18Z UTC = 14:25:30 → 14:27:18 +07

HOW:   kubectl từ bastion i-072084d1cf0b2f1c9
       Bastion truy cập qua SSM StartSession (confirmed CloudTrail)
```

---

## Điểm cần lưu ý khi drill

1. **Verb `create` trên `pods/portforward`** = kubectl port-forward, không phải tạo pod mới
2. **Service account noise** — luôn thêm `select(.user.username | test("system:") | not)` để lọc
3. **Bastion role** `tf4-portal-bastion-role/i-INSTANCE-ID` — traceable về instance ID cụ thể
4. **Epoch ms** — CloudWatch cần milliseconds, nhân 1000 từ Unix timestamp

---

## Evidence liên quan

- Data thật: `docs/audit/postmortems/evidence_incident.jpg`
- Incident context: `docs/audit/postmortems/incident-20260714-checkout-payment.md`
- Drill log (thời gian thực tế): `docs/evidence/mandate-04-forensic/aud-17.2-drill-log.md` Scenario 1
