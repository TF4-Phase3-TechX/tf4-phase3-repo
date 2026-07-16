# Scenario 01 — Infrastructure Change
## AUD-17.2 · Forensic Drill Scenario Design

| Field | Giá trị |
|---|---|
| Scenario ID | AUD-17.2-S01 |
| Loại | Infrastructure change |
| Nguồn log | CloudTrail — `tf4-general-cloudtrail` |
| Độ khó | Trung bình |
| Target thời gian | ≤8 phút |
| Tác giả | Ty (CDO07) |
| Ngày | 2026-07-15 |

---

## Mô tả kịch bản

**Tình huống mentor đưa ra:**
> "Tuần vừa rồi có ai thay đổi cấu hình EKS nodegroup không? Ai làm, khi nào?"

Hoặc:
> "S3 bucket nào đó bị tạo thêm — ai tạo, lúc mấy giờ?"

**Loại event cần trace:**
- `UpdateNodegroupConfig` — thay đổi scaling config / AMI / labels của EKS nodegroup
- `CreateBucket` — tạo S3 bucket mới
- `DeleteBucket` — xóa S3 bucket

**Lý do dùng CloudTrail:** Đây là AWS API call ở tầng infrastructure — không xuất hiện trong K8s audit log. Rule phân loại: hành động AWS API → CloudTrail.

---

## Query cụ thể

### Query A — EKS nodegroup change

```bash
# Tìm mọi UpdateNodegroupConfig trong 7 ngày
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateNodegroupConfig \
  --start-time "2026-07-09T00:00:00Z" \
  --end-time "2026-07-16T00:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:        .EventTime,
      event:       .EventName,
      user:        .Username,
      userArn:     (.CloudTrailEvent | fromjson | .userIdentity.arn),
      cluster:     (.CloudTrailEvent | fromjson | .requestParameters.clusterName),
      nodegroup:   (.CloudTrailEvent | fromjson | .requestParameters.nodegroupName),
      scalingMin:  (.CloudTrailEvent | fromjson | .requestParameters.scalingConfig.minSize),
      scalingMax:  (.CloudTrailEvent | fromjson | .requestParameters.scalingConfig.maxSize),
      srcIP:       (.CloudTrailEvent | fromjson | .sourceIPAddress)
    }'
```

### Query B — S3 bucket operations

```bash
# Tìm CreateBucket / DeleteBucket
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=CreateBucket \
  --start-time "2026-07-09T00:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:    .EventTime,
      event:   .EventName,
      user:    .Username,
      userArn: (.CloudTrailEvent | fromjson | .userIdentity.arn),
      bucket:  (.CloudTrailEvent | fromjson | .requestParameters.bucketName),
      region:  (.CloudTrailEvent | fromjson | .awsRegion),
      srcIP:   (.CloudTrailEvent | fromjson | .sourceIPAddress)
    }'
```

### Query C — Mọi infra change của 1 user (nếu mentor hỏi theo người)

```bash
# Thay TÊN_USER bằng username cần tìm
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=Username,AttributeValue=TÊN_USER \
  --start-time "2026-07-09T00:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | select(.EventSource == "eks.amazonaws.com" or .EventSource == "s3.amazonaws.com")
        | {time: .EventTime, event: .EventName, source: .EventSource}'
```

---

## Output thật từ hệ thống (đã verified 2026-07-15)

```
EventTime              EventName         User    Cluster              Nodegroup
2026-07-07T09:16:56Z   CreateNodegroup   root    techx-tf4-cluster    techx-general-ng-20260707091432750200000017
```

Chi tiết từ CloudTrailEvent:
```json
{
  "time":        "2026-07-07T09:16:56Z",
  "event":       "CreateNodegroup",
  "user":        "root",
  "userArn":     "arn:aws:iam::511825856493:root",
  "cluster":     "techx-tf4-cluster",
  "nodegroup":   "techx-general-ng-20260707091432750200000017",
  "scalingMin":  2,
  "scalingMax":  4,
  "desiredSize": 2,
  "instanceType": "t3.large",
  "capacityType": "ON_DEMAND",
  "srcIP":       "117.2.125.107",
  "userAgent":   "Terraform/1.15.5 terraform-provider-aws/5.100.0"
}
```

> **Ghi chú:** Query chạy lúc 2026-07-15 bằng profile `TF4-AuditReadOnlyAndAnalyze-511825856493`.
> Event này là lúc CDO04 dùng Terraform khởi tạo cluster tuần đầu.

---

## Trả lời forensic (dùng data thật)

```
WHO:   root (arn:aws:iam::511825856493:root) — tức là Terraform chạy với root credentials
       userAgent = "Terraform/1.15.5" → đây là CI/CD / infrastructure-as-code, không phải người
       srcIP = 117.2.125.107 → IP của CDO04 hoặc CI runner

WHAT:  CreateNodegroup — tạo EKS nodegroup mới
       Nodegroup: techx-general-ng-20260707091432750200000017
       Cluster: techx-tf4-cluster
       Config: t3.large, ON_DEMAND, scaling 2–4 nodes

WHEN:  2026-07-07T09:16:56Z = 2026-07-07T16:16:56+07

HOW:   Terraform apply qua AWS API
       Không phải human action thủ công — hoàn toàn IaC

LƯU Ý QUAN TRỌNG:
       Username = "root" là đáng lo — best practice là dùng role thay vì root.
       Đây là finding security cần ghi nhận (ADR liên quan: ADR-003).
```

---

## Điểm cần lưu ý khi drill

1. **GitHub Actions IP range** là `192.30.255.0/24` — nhận ra ngay là CI/CD, không phải người
2. **Session name trong ARN** = run ID hoặc bot name → traceable về GitHub Actions run
3. Nếu không thấy event → mở rộng window, hoặc thử `CreateNodegroup`, `DeleteNodegroup`
4. S3 events có thể ở region khác — thêm `--region` nếu cần scan nhiều region

---

## Evidence liên quan

- Framework: `docs/audit/tickets/AUDIT-CDO07-MANDATE04-FORENSIC-FRAMEWORK.md`
- Query patterns: `aud-17.2-query-patterns.md`
- Drill log: `docs/evidence/mandate-04-forensic/aud-17.2-drill-log.md`
