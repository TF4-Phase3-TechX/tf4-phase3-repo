# Báo cáo Forensic Investigation Report

**Dự án:** Task Force 4 (TF4) · Mặt trận XBrain

---

## Case 1 – Kubernetes Audit Log Forensics (EKS API Server)

### Báo cáo kết quả truy vết & dựng lại hiện trường (Forensic Report)

| Thuộc tính | Giá trị |
|---|---|
| Người thực hiện | CDO-07 Auditability |
| Gửi tới | Mentors (anh Nghĩa, anh Toàn) |
| Thời điểm điều tra | 09:28 (UTC+7) · 17/07/2026 |
| Trạng thái | ✅ Hoàn tất dựng lại hiện trường 100% |

### I. Tóm tắt kết quả truy vết (Executive Summary)

Dựa trên dữ liệu thu thập trực tiếp từ EKS API Server Audit Logs, đội kiểm toán CDO-07 đã dựng lại thành công vụ việc tạo rồi xóa đối tượng "vết" xảy ra vào đêm 16/07/2026.

**1. Identity thực hiện**

- **ARN:** `arn:aws:iam::511825856493:user/cdo04-an`
- **User ID:** `aws-iam-authenticator:511825856493:AIDAXOKZSY7WTTLW3YONF`
- **Quyền hạn:** ClusterRoleBinding — `AmazonEKSClusterAdminPolicy` (Cluster Administrator)

**2. Hành động**

- Create ConfigMap
- Delete ConfigMap

**Đối tượng:** `drill-marker-8398`

Hiện đối tượng đã bị xóa hoàn toàn khỏi Kubernetes Cluster.

**3. Timeline**

| Sự kiện | Thời gian UTC | Giờ Việt Nam |
|---|---|---|
| Create | 2026-07-16T16:47:26.154305Z | 23:47:26.154 |
| Delete | 2026-07-16T16:47:30.998392Z | 23:47:30.998 |

**Thời gian tồn tại:** 4.84 giây

**4. Source**

- **IP:** 116.109.13.201
- **Client:** kubectl v1.35.2
- **OS:** macOS (darwin/arm64)

### II. Quá trình truy vết chi tiết (Step-by-Step Forensics)

#### Bước 1. Kiểm tra tính toàn vẹn của Logs

Trước khi phân tích, đội kiểm toán xác minh dữ liệu log không bị chỉnh sửa hoặc xóa.

**Kiểm tra:**
- CloudWatch Logs hoạt động theo cơ chế Append-only

**Kiểm tra Log Group:** `/aws/eks/techx-tf4-cluster/cluster`

**Kết quả:**
- Toàn bộ Log Stream còn nguyên vẹn
- Không phát hiện việc xóa log
- Không có khoảng trống dữ liệu

> 📷 *Hình minh họa: ![alt text](image.png)*

**Phương án dự phòng**

Nếu Log Stream bị xóa, đội CDO-07 vẫn có thể phục hồi từ S3 Bucket `tf4-cdo07-audit-logs`, được đồng bộ thời gian thực thông qua Kinesis Firehose và bảo vệ bằng S3 Object Lock (Compliance Mode).

#### Bước 2. Truy vấn CloudWatch Logs Insights

```
SOURCE "arn:aws:logs:us-east-1:511825856493:log-group:/aws/eks/techx-tf4-cluster/cluster"

START=2026-07-16T16:30:00.000Z
END=2026-07-16T18:20:00.000Z

| fields @timestamp,
         user.username,
         verb,
         objectRef.resource,
         objectRef.name,
         sourceIPs.0,
         responseStatus.code
| filter objectRef.namespace = "techx-tf4"
| filter verb in ["create","delete"]
| sort @timestamp desc
| limit 100
```

**Kết quả:**
- Phát hiện 02 sự kiện liên tiếp
- **Object:** `drill-marker-8398`
- **Namespace:** `techx-tf4`
- Khoảng cách giữa Create và Delete khoảng 5 giây
- **Actor:** `cdo04-an`
- **Source IP:** `116.109.13.201`


### III. Bằng chứng pháp y (Raw Audit Log Evidence)

**Event 1 – Create ConfigMap**

```json
JSON
{
  "kind": "Event",
  "apiVersion": "audit.k8s.io/v1",
  "level": "Metadata",
  "auditID": "91bb56e7-29e6-4274-8abc-eb74015ed870",
  "stage": "ResponseComplete",
  "requestURI": "/api/v1/namespaces/techx-tf4/configmaps?fieldManager=kubectl-create&fieldValidation=Strict",
  "verb": "create",
  "user": {
    "username": "arn:aws:iam::511825856493:user/cdo04-an",
    "uid": "aws-iam-authenticator:511825856493:AIDAXOKZSY7WTTLW3YONF",
    "groups": [
      "system:authenticated"
    ]
  },
  "sourceIPs": [
    "116.109.13.201"
  ],
  "userAgent": "kubectl/v1.35.2 (darwin/arm64) kubernetes/fdc9d74",
  "objectRef": {
    "resource": "configmaps",
    "namespace": "techx-tf4",
    "name": "drill-marker-8398",
    "apiVersion": "v1"
  },
  "responseStatus": {
    "code": 201
  },
  "requestReceivedTimestamp": "2026-07-16T16:47:26.154305Z",
  "stageTimestamp": "2026-07-16T16:47:26.178758Z"
}

```


**Event 2 – Delete ConfigMap**

```json
JSON
{
  "kind": "Event",
  "apiVersion": "audit.k8s.io/v1",
  "level": "Metadata",
  "auditID": "8a436a65-6f1a-45cc-af8c-53e10c06827f",
  "stage": "ResponseComplete",
  "requestURI": "/api/v1/namespaces/techx-tf4/configmaps/drill-marker-8398",
  "verb": "delete",
  "user": {
    "username": "arn:aws:iam::511825856493:user/cdo04-an",
    "uid": "aws-iam-authenticator:511825856493:AIDAXOKZSY7WTTLW3YONF",
    "groups": [
      "system:authenticated"
    ]
  },
  "sourceIPs": [
    "116.109.13.201"
  ],
  "userAgent": "kubectl/v1.35.2 (darwin/arm64) kubernetes/fdc9d74",
  "objectRef": {
    "resource": "configmaps",
    "namespace": "techx-tf4",
    "name": "drill-marker-8398",
    "apiVersion": "v1"
  },
  "responseStatus": {
    "status": "Success",
    "details": {
      "name": "drill-marker-8398",
      "kind": "configmaps",
      "uid": "029ef762-1aab-41d4-81da-ed33b0b0c70b"
    },
    "code": 200
  },
  "requestReceivedTimestamp": "2026-07-16T16:47:30.998392Z",
  "stageTimestamp": "2026-07-16T16:47:31.012110Z"
}

```



### IV. Kết luận kiểm toán (Audit Conclusion)

Nhờ hệ thống Audit Logging được triển khai tập trung, đội CDO-07 đã xác định chính xác:

- Danh tính người thực hiện
- Thời điểm xảy ra
- Địa chỉ IP nguồn
- Công cụ sử dụng
- Chuỗi hành vi

Mặc dù tài nguyên đã bị xóa khỏi Kubernetes Cluster, toàn bộ chứng cứ vẫn được lưu giữ đầy đủ phục vụ điều tra pháp y.

---

## Case 2 – AWS Infrastructure Forensics (CloudTrail)

### Báo cáo kết quả truy vết & dựng lại hiện trường hạ tầng

| Thuộc tính | Giá trị |
|---|---|
| Người thực hiện | CDO-07 Auditability |
| Gửi tới | Mentors (anh Nghĩa, anh Toàn) |
| Thời điểm điều tra | 09:46 (UTC+7) · 17/07/2026 |
| Trạng thái | ✅ Hoàn tất dựng lại hiện trường 100% |

### I. Tóm tắt kết quả truy vết (Executive Summary)

**Nguồn dữ liệu điều tra:** AWS CloudTrail Logs

Đội kiểm toán đã dựng lại chuỗi thao tác tạo, đọc và xóa đối tượng cấu hình trên hạ tầng AWS.

**1. Identity**

- **ARN:** `arn:aws:iam::511825856493:user/cdo04-an`
- **User Name:** `cdo04-an`
- **Principal ID:** `AIDAXOKZSY7WTTLW3YONF`
- **Access Key:** `AKIAXOKZSY7WTLQN55U6`

**2. Chuỗi hành động**

- **Dịch vụ:** AWS Systems Manager Parameter Store
- **Đối tượng:** `/forensic-drill/mandate04-23228`

**Chuỗi hành vi:**
- PutParameter
- GetParameter
- DeleteParameter

**3. Timeline**

| Thời gian | Sự kiện |
|---|---|
| 01:17:22 | PutParameter |
| 01:17:24 | GetParameter |
| 01:17:25 | DeleteParameter |

**Tổng thời gian:** 3 giây

**4. Source**

- **IP:** 116.109.13.201
- **User Agent:** aws-cli/2.34.33
- **OS:** macOS (darwin/arm64)

### II. Quá trình truy vết

#### Bước 1. Kiểm tra Log Integrity

**Kiểm tra CloudTrail Log Group:** `/aws/cloudtrail/tf4-general-cloudtrail`

**Kết quả:**
- CloudTrail hoạt động bình thường
- Log Stream nguyên vẹn
- Append-only
- Subscription Filter → Firehose → S3 Object Lock

> ![alt text](image-1.png)

#### Bước 2. CloudWatch Logs Insights

```
SOURCE "arn:aws:logs:us-east-1:511825856493:log-group:/aws/cloudtrail/tf4-general-cloudtrail"

START=2026-07-16T18:07:00.000Z
END=2026-07-16T18:27:00.000Z

| fields eventTime,
         userIdentity.userName as actor,
         eventName,
         requestParameters.name as objectName,
         sourceIPAddress,
         eventID
| filter @message like /mandate04-23228/
| sort eventTime asc
| limit 20
```

**Kết quả:**

Phát hiện đầy đủ chuỗi:
- PutParameter
- GetParameter
- DeleteParameter

do `cdo04-an` thực hiện từ `116.109.13.201`

> ![alt text](image-2.png)

### III. Bằng chứng pháp y (Raw CloudTrail Evidence)

**Event 1 – PutParameter**

```json
JSON
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "IAMUser",
    "arn": "arn:aws:iam::511825856493:user/cdo04-an",
    "userName": "cdo04-an"
  },
  "eventTime": "2026-07-16T18:17:22Z",
  "eventSource": "ssm.amazonaws.com",
  "eventName": "PutParameter",
  "awsRegion": "us-east-1",
  "sourceIPAddress": "116.109.13.201",
  "requestParameters": {
    "name": "/forensic-drill/mandate04-23228",
    "value": "HIDDEN_DUE_TO_SECURITY_REASONS",
    "type": "String"
  },
  "responseElements": {
    "version": 1,
    "tier": "Standard"
  },
  "requestID": "f0a586f8-c550-4b10-b538-4b32c6b132d6",
  "eventID": "b8f28767-d9c0-41ca-8aa0-878a68b2bca4"
}

```
> ![alt text](image-3.png)


**Event 2 – GetParameter**

```json
JSON
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "IAMUser",
    "arn": "arn:aws:iam::511825856493:user/cdo04-an",
    "userName": "cdo04-an"
  },
  "eventTime": "2026-07-16T18:17:24Z",
  "eventSource": "ssm.amazonaws.com",
  "eventName": "GetParameter",
  "awsRegion": "us-east-1",
  "sourceIPAddress": "116.109.13.201",
  "requestParameters": {
    "name": "/forensic-drill/mandate04-23228"
  },
  "responseElements": null,
  "requestID": "56e8a469-9123-45fa-8e0b-ffc7556a05ff",
  "eventID": "f761ed3d-a5f9-49c1-bab8-292238413fa1"
}

```

> ![alt text](image-4.png)

**Event 3 – DeleteParameter**

```json
JSON
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "IAMUser",
    "arn": "arn:aws:iam::511825856493:user/cdo04-an",
    "userName": "cdo04-an"
  },
  "eventTime": "2026-07-16T18:17:25Z",
  "eventSource": "ssm.amazonaws.com",
  "eventName": "DeleteParameter",
  "awsRegion": "us-east-1",
  "sourceIPAddress": "116.109.13.201",
  "requestParameters": {
    "name": "/forensic-drill/mandate04-23228"
  },
  "responseElements": null,
  "requestID": "a96dccde-f0a5-42c9-a6d5-bc978a9ff01e",
  "eventID": "455cc7cd-17b6-44b6-8f4b-40c4ef55e8dd"
}

```

> ![alt text](image-5.png)*

### IV. Kết luận kiểm toán

Cuộc điều tra xác định:

- Hành vi diễn ra hoàn toàn trên AWS Infrastructure, không thuộc Kubernetes Cluster.
- Người dùng `cdo04-an` đã tạo, đọc và xóa đối tượng cấu hình chỉ trong 3 giây nhằm loại bỏ dấu vết.
- Nhờ kiến trúc lưu trữ log chống chối bỏ (CloudTrail → CloudWatch → Firehose → S3 Object Lock), toàn bộ chuỗi hành vi vẫn được ghi nhận đầy đủ và đáp ứng yêu cầu điều tra pháp y theo Directive #4.