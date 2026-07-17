# Báo Cáo Audit Forensic Tổng Hợp: Mandate 04

## Kết Luận Tổng Quan

Đã audit hai case tạo rồi xóa object trong thời gian rất ngắn:

1. Case in-cluster Kubernetes:
   - Object: `configmap/drill-marker-8398`
   - Namespace: `techx-tf4`
   - Thời gian: `2026-07-16 23:47:26 -> 23:47:31 ICT`
   - Actor: `arn:aws:iam::511825856493:user/cdo04-an`
   - Source IP: `116.109.13.201`
   - Tool: `kubectl/v1.35.2 (darwin/arm64)`

2. Case AWS infra ngoài cluster:
   - Object: SSM Parameter `/forensic-drill/mandate04-23228`
   - Thời gian: `2026-07-17 01:17:22 -> 01:17:25 ICT`
   - Actor: `arn:aws:iam::511825856493:user/cdo04-an`
   - Source IP: `116.109.13.201`
   - Tool: `aws-cli/2.34.33` trên macOS arm64

Cả hai case đều do cùng IAM user `cdo04-an` thao tác, cùng source IP `116.109.13.201`, và cùng access key `AKIAXOKZSY7WTLQN55U6`.

## Bảng Tóm Tắt

| Case | Môi trường | Object | Hành động chính | Thời gian ICT | Actor | Source IP |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Kubernetes/EKS | `configmap/drill-marker-8398` | `create -> get -> get -> delete -> get 404` | `2026-07-16 23:47:26 -> 23:47:31` | `arn:aws:iam::511825856493:user/cdo04-an` | `116.109.13.201` |
| 2 | AWS infra ngoài cluster | `/forensic-drill/mandate04-23228` | `PutParameter -> GetParameter -> DeleteParameter` | `2026-07-17 01:17:22 -> 01:17:25` | `arn:aws:iam::511825856493:user/cdo04-an` | `116.109.13.201` |

## Thông Tin Tài Khoản Thao Tác

| Trường | Giá trị |
| --- | --- |
| IAM user | `cdo04-an` |
| ARN | `arn:aws:iam::511825856493:user/cdo04-an` |
| UserId | `AIDAXOKZSY7WTTLW3YONF` |
| Access key xuất hiện trong log | `AKIAXOKZSY7WTLQN55U6` |
| Source IP chung | `116.109.13.201` |

Kết luận về tài khoản:

- Tài khoản `cdo04-an` không bị xóa tại thời điểm audit.
- Lệnh `iam get-user` vẫn trả về user này.
- Object bị xóa trong hai case là object cấu hình, không phải tài khoản IAM.

---

# Case 1: Kubernetes Object Trong Namespace `techx-tf4`

## Phạm Vi Audit

Mốc thời gian ban đầu được yêu cầu là khoảng `01:15 ICT` ngày `2026-07-17`, có thể lệch vài phút. Việc audit được thực hiện theo thứ tự:

1. Query cửa sổ 40 phút quanh mốc `01:15`:
   - Từ `2026-07-17 00:55 ICT`
   - Đến `2026-07-17 01:35 ICT`
   - Kết quả: không thấy event xóa object nào trong namespace `techx-tf4`.

2. Mở rộng phạm vi query để kiểm tra quanh buổi đêm gần mốc nghi vấn:
   - Từ `2026-07-16 23:00 ICT`
   - Đến `2026-07-17 03:00 ICT`
   - Kết quả: tìm thấy event `create/delete` object phù hợp mô tả lúc `2026-07-16 23:47 ICT`.

## Hiện Trường

| Trường | Giá trị |
| --- | --- |
| Object | `configmap/drill-marker-8398` |
| Resource | `configmaps` |
| Namespace | `techx-tf4` |
| API version | `v1` |
| Actor | `arn:aws:iam::511825856493:user/cdo04-an` |
| Principal/UserId | `AIDAXOKZSY7WTTLW3YONF` |
| Access key đã dùng | `AKIAXOKZSY7WTLQN55U6` |
| Source IP | `116.109.13.201` |
| User agent | `kubectl/v1.35.2 (darwin/arm64) kubernetes/fdc9d74` |
| Quyền được allow bởi | `AmazonEKSClusterAdminPolicy` |

## Timeline

| Thời gian ICT | Hành động | Object | Code | AuditID |
| --- | --- | --- | --- | --- |
| `2026-07-16 23:47:26 ICT` | `create` | `configmaps/drill-marker-8398` | `201` | `91bb56e7-29e6-4274-8abc-eb74015ed870` |
| `2026-07-16 23:47:28 ICT` | `get` | `configmaps/drill-marker-8398` | `200` | `4ceaed98-6d38-42f1-95d4-d99aada48ece` |
| `2026-07-16 23:47:29 ICT` | `get` | `configmaps/drill-marker-8398` | `200` | `77b641d5-9f8f-4f4d-9838-b92d6c3a6c4d` |
| `2026-07-16 23:47:30 ICT` | `delete` | `configmaps/drill-marker-8398` | `200` | `8a436a65-6f1a-45cc-af8c-53e10c06827f` |
| `2026-07-16 23:47:31 ICT` | `get` | `configmaps/drill-marker-8398` | `404 NotFound` | `e6d7b979-0012-4042-839b-19881290d0b6` |

## Diễn Biến Chi Tiết

### 1. Tạo Object

- Thời gian: `2026-07-16 23:47:26 ICT`
- Verb: `create`
- Resource: `configmaps`
- Tên object: `drill-marker-8398`
- Namespace: `techx-tf4`
- Response code: `201`
- Actor: `arn:aws:iam::511825856493:user/cdo04-an`
- Source IP: `116.109.13.201`
- AuditID: `91bb56e7-29e6-4274-8abc-eb74015ed870`
- Request URI: `/api/v1/namespaces/techx-tf4/configmaps?fieldManager=kubectl-create&fieldValidation=Strict`

### 2. Đọc Lại Object Sau Khi Tạo

Actor tiếp tục `get` object hai lần:

- `2026-07-16 23:47:28 ICT`, code `200`
- `2026-07-16 23:47:29 ICT`, code `200`

Hai event này xác nhận object đã tồn tại sau khi được tạo thành công.

### 3. Xóa Object

- Thời gian: `2026-07-16 23:47:30 ICT`
- Verb: `delete`
- Resource: `configmaps`
- Tên object: `drill-marker-8398`
- Namespace: `techx-tf4`
- Response code: `200`
- Actor: `arn:aws:iam::511825856493:user/cdo04-an`
- Source IP: `116.109.13.201`
- AuditID: `8a436a65-6f1a-45cc-af8c-53e10c06827f`
- UID của object bị xóa: `029ef762-1aab-41d4-81da-ed33b0b0c70b`

### 4. Xác Minh Object Không Còn Tồn Tại

Ngay sau thao tác xóa, actor thực hiện `get` lại object:

- Thời gian: `2026-07-16 23:47:31 ICT`
- Verb: `get`
- Response code: `404`
- Reason: `NotFound`
- Message: `configmaps "drill-marker-8398" not found`
- AuditID: `e6d7b979-0012-4042-839b-19881290d0b6`

Kiểm tra hiện tại bằng `kubectl`:

```powershell
kubectl -n techx-tf4 get configmap drill-marker-8398
```

Kết quả:

```text
NotFound
```

## Evidence Log

Các log audit quan trọng được trích xuất trực tiếp từ EKS control-plane audit log:

| Time ICT | Verb | Resource | Namespace | Name | Code | User | Source IP | AuditID |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `2026-07-16 23:47:26 ICT` | `create` | `configmaps` | `techx-tf4` | `drill-marker-8398` | `201` | `arn:aws:iam::511825856493:user/cdo04-an` | `116.109.13.201` | `91bb56e7-29e6-4274-8abc-eb74015ed870` |
| `2026-07-16 23:47:28 ICT` | `get` | `configmaps` | `techx-tf4` | `drill-marker-8398` | `200` | `arn:aws:iam::511825856493:user/cdo04-an` | `116.109.13.201` | `4ceaed98-6d38-42f1-95d4-d99aada48ece` |
| `2026-07-16 23:47:29 ICT` | `get` | `configmaps` | `techx-tf4` | `drill-marker-8398` | `200` | `arn:aws:iam::511825856493:user/cdo04-an` | `116.109.13.201` | `77b641d5-9f8f-4f4d-9838-b92d6c3a6c4d` |
| `2026-07-16 23:47:30 ICT` | `delete` | `configmaps` | `techx-tf4` | `drill-marker-8398` | `200` | `arn:aws:iam::511825856493:user/cdo04-an` | `116.109.13.201` | `8a436a65-6f1a-45cc-af8c-53e10c06827f` |
| `2026-07-16 23:47:31 ICT` | `get` | `configmaps` | `techx-tf4` | `drill-marker-8398` | `404` | `arn:aws:iam::511825856493:user/cdo04-an` | `116.109.13.201` | `e6d7b979-0012-4042-839b-19881290d0b6` |

Log chi tiết cho event tạo object:

```json
{
  "eventTimeICT": "2026-07-16 23:47:26 ICT",
  "auditID": "91bb56e7-29e6-4274-8abc-eb74015ed870",
  "verb": "create",
  "requestURI": "/api/v1/namespaces/techx-tf4/configmaps?fieldManager=kubectl-create&fieldValidation=Strict",
  "user": "arn:aws:iam::511825856493:user/cdo04-an",
  "accessKeyId": "AKIAXOKZSY7WTLQN55U6",
  "sourceIPs": ["116.109.13.201"],
  "userAgent": "kubectl/v1.35.2 (darwin/arm64) kubernetes/fdc9d74",
  "objectRef": {
    "resource": "configmaps",
    "namespace": "techx-tf4",
    "name": "drill-marker-8398",
    "apiVersion": "v1"
  },
  "responseStatus": {
    "code": 201
  }
}
```

Log chi tiết cho event xóa object:

```json
{
  "eventTimeICT": "2026-07-16 23:47:30 ICT",
  "auditID": "8a436a65-6f1a-45cc-af8c-53e10c06827f",
  "verb": "delete",
  "requestURI": "/api/v1/namespaces/techx-tf4/configmaps/drill-marker-8398",
  "user": "arn:aws:iam::511825856493:user/cdo04-an",
  "accessKeyId": "AKIAXOKZSY7WTLQN55U6",
  "sourceIPs": ["116.109.13.201"],
  "userAgent": "kubectl/v1.35.2 (darwin/arm64) kubernetes/fdc9d74",
  "objectRef": {
    "resource": "configmaps",
    "namespace": "techx-tf4",
    "name": "drill-marker-8398",
    "apiVersion": "v1"
  },
  "responseStatus": {
    "status": "Success",
    "code": 200,
    "details": {
      "name": "drill-marker-8398",
      "kind": "configmaps",
      "uid": "029ef762-1aab-41d4-81da-ed33b0b0c70b"
    }
  }
}
```

Log xác nhận object không còn tồn tại ngay sau khi xóa:

```json
{
  "eventTimeICT": "2026-07-16 23:47:31 ICT",
  "auditID": "e6d7b979-0012-4042-839b-19881290d0b6",
  "verb": "get",
  "requestURI": "/api/v1/namespaces/techx-tf4/configmaps/drill-marker-8398",
  "user": "arn:aws:iam::511825856493:user/cdo04-an",
  "sourceIPs": ["116.109.13.201"],
  "objectRef": {
    "resource": "configmaps",
    "namespace": "techx-tf4",
    "name": "drill-marker-8398",
    "apiVersion": "v1"
  },
  "responseStatus": {
    "status": "Failure",
    "reason": "NotFound",
    "message": "configmaps \"drill-marker-8398\" not found",
    "code": 404
  }
}
```

## Kết Luận Case 1

Hiện trường khớp nhất với mô tả:

- Ai thao tác: `arn:aws:iam::511825856493:user/cdo04-an`
- Làm gì: tạo `configmap/drill-marker-8398`, đọc lại 2 lần, xóa object, sau đó `get` lại và nhận `404 NotFound`
- Lúc nào: `2026-07-16 23:47:26 -> 23:47:31 ICT`
- Từ IP nào: `116.109.13.201`
- Dùng công cụ nào: `kubectl/v1.35.2 (darwin/arm64)`
- Trạng thái object hiện tại: không còn tồn tại

Kết luận điều tra: đây là thao tác Kubernetes object trong namespace `techx-tf4` của IAM user `cdo04-an`. Object `configmap/drill-marker-8398` đã bị xóa thành công lúc `2026-07-16 23:47:30 ICT`.

---

# Case 2: AWS Infra Ngoài Cluster

## Phạm Vi Audit

Đã audit CloudTrail theo mốc thời gian Việt Nam quanh `01:17` ngày `17/07/2026`, với cửa sổ 10 phút xung quanh:

- Cửa sổ audit: `2026-07-17 01:07 -> 01:27 ICT`
- Tương ứng UTC: `2026-07-16 18:07 -> 18:27 UTC`
- Nguồn log: CloudTrail trong CloudWatch Log Group `/aws/cloudtrail/tf4-general-cloudtrail`
- Case khớp mô tả: AWS Systems Manager Parameter Store

## Hiện Trường

| Trường | Giá trị |
| --- | --- |
| Dịch vụ AWS | AWS Systems Manager Parameter Store |
| Event source | `ssm.amazonaws.com` |
| Object | `/forensic-drill/mandate04-23228` |
| Loại object | SSM Parameter |
| Parameter type | `String` |
| Tier | `Standard` |
| Version khi tạo | `1` |
| Actor | `arn:aws:iam::511825856493:user/cdo04-an` |
| User type | `IAMUser` |
| User name | `cdo04-an` |
| Access key đã dùng | `AKIAXOKZSY7WTLQN55U6` |
| Source IP | `116.109.13.201` |
| User agent | `aws-cli/2.34.33 ... os/macos#25.3.0 ... md/arch#arm64` |

Giá trị parameter không xuất hiện trong CloudTrail vì bị ẩn theo cơ chế bảo mật:

```text
HIDDEN_DUE_TO_SECURITY_REASONS
```

## Timeline

| Thời gian ICT | Hành động | Object | Kết quả | EventID |
| --- | --- | --- | --- | --- |
| `2026-07-17 01:17:22 ICT` | `PutParameter` | `/forensic-drill/mandate04-23228` | Thành công, version `1`, tier `Standard` | `b8f28767-d9c0-41ca-8aa0-878a68b2bca4` |
| `2026-07-17 01:17:24 ICT` | `GetParameter` | `/forensic-drill/mandate04-23228` | Thành công | `f761ed3d-a5f9-49c1-bab8-292238413fa1` |
| `2026-07-17 01:17:25 ICT` | `DeleteParameter` | `/forensic-drill/mandate04-23228` | Thành công | `455cc7cd-17b6-44b6-8f4b-40c4ef55e8dd` |

## Diễn Biến Chi Tiết

### 1. Tạo Parameter

- Thời gian: `2026-07-17 01:17:22 ICT`
- Event name: `PutParameter`
- Event source: `ssm.amazonaws.com`
- Parameter name: `/forensic-drill/mandate04-23228`
- Parameter type: `String`
- Response: version `1`, tier `Standard`
- Actor: `arn:aws:iam::511825856493:user/cdo04-an`
- Source IP: `116.109.13.201`
- EventID: `b8f28767-d9c0-41ca-8aa0-878a68b2bca4`
- RequestID: `f0a586f8-c550-4b10-b538-4b32c6b132d6`

### 2. Đọc Lại Parameter

- Thời gian: `2026-07-17 01:17:24 ICT`
- Event name: `GetParameter`
- Parameter name: `/forensic-drill/mandate04-23228`
- Actor: `arn:aws:iam::511825856493:user/cdo04-an`
- Source IP: `116.109.13.201`
- EventID: `f761ed3d-a5f9-49c1-bab8-292238413fa1`
- RequestID: `56e8a469-9123-45fa-8e0b-ffc7556a05ff`

Event này xác nhận parameter đã tồn tại sau khi được tạo.

### 3. Xóa Parameter

- Thời gian: `2026-07-17 01:17:25 ICT`
- Event name: `DeleteParameter`
- Parameter name: `/forensic-drill/mandate04-23228`
- Actor: `arn:aws:iam::511825856493:user/cdo04-an`
- Source IP: `116.109.13.201`
- EventID: `455cc7cd-17b6-44b6-8f4b-40c4ef55e8dd`
- RequestID: `a96dccde-f0a5-42c9-a6d5-bc978a9ff01e`

CloudTrail không ghi nhận `errorCode` cho event `DeleteParameter`, nên đây là thao tác xóa thành công.

## Kiểm Tra Trạng Thái Hiện Tại

Đã thử kiểm tra trực tiếp bằng SSM API:

```powershell
aws ssm get-parameter --name "/forensic-drill/mandate04-23228"
aws ssm describe-parameters --parameter-filters "Key=Name,Option=Equals,Values=/forensic-drill/mandate04-23228"
```

Tuy nhiên profile audit hiện tại không có quyền:

- `ssm:GetParameter`
- `ssm:DescribeParameters`

Do đó không thể xác minh trực tiếp bằng SSM API với profile này. Dù vậy, CloudTrail đã ghi nhận `DeleteParameter` thành công và không có `errorCode`, nên kết luận forensic là parameter đã bị xóa sau khi tạo.

## Đối Chiếu Với Write Events Trong Cửa Sổ Audit

Trong cửa sổ `2026-07-17 01:07 -> 01:27 ICT`, có nhiều write events nền từ ECS/EKS/Karpenter/SSM Agent, ví dụ:

- `RegisterContainerInstance`
- `UpdateInstanceInformation`
- `RunInstances`
- `CreateNetworkInterface`
- `DeleteLaunchTemplate`

Các event nền này hoặc là service/system activity, hoặc có lỗi `AccessDenied`/`DryRunOperation`, hoặc không tạo/xóa cùng một object cấu hình trong vài giây.

Cặp event khớp chính xác mô tả là:

```text
PutParameter -> GetParameter -> DeleteParameter
```

trên cùng object:

```text
/forensic-drill/mandate04-23228
```

## Evidence Log

Các log audit quan trọng được trích xuất trực tiếp từ CloudTrail:

| Time ICT | EventSource | EventName | Object | User | Source IP | EventID |
| --- | --- | --- | --- | --- | --- | --- |
| `2026-07-17 01:17:22 ICT` | `ssm.amazonaws.com` | `PutParameter` | `/forensic-drill/mandate04-23228` | `arn:aws:iam::511825856493:user/cdo04-an` | `116.109.13.201` | `b8f28767-d9c0-41ca-8aa0-878a68b2bca4` |
| `2026-07-17 01:17:24 ICT` | `ssm.amazonaws.com` | `GetParameter` | `/forensic-drill/mandate04-23228` | `arn:aws:iam::511825856493:user/cdo04-an` | `116.109.13.201` | `f761ed3d-a5f9-49c1-bab8-292238413fa1` |
| `2026-07-17 01:17:25 ICT` | `ssm.amazonaws.com` | `DeleteParameter` | `/forensic-drill/mandate04-23228` | `arn:aws:iam::511825856493:user/cdo04-an` | `116.109.13.201` | `455cc7cd-17b6-44b6-8f4b-40c4ef55e8dd` |

Log chi tiết cho event tạo parameter:

```json
{
  "eventTimeICT": "2026-07-17 01:17:22 ICT",
  "eventSource": "ssm.amazonaws.com",
  "eventName": "PutParameter",
  "user": "arn:aws:iam::511825856493:user/cdo04-an",
  "accessKeyId": "AKIAXOKZSY7WTLQN55U6",
  "sourceIPAddress": "116.109.13.201",
  "userAgent": "aws-cli/2.34.33 ... os/macos#25.3.0 ... md/arch#arm64",
  "requestParameters": {
    "name": "/forensic-drill/mandate04-23228",
    "value": "HIDDEN_DUE_TO_SECURITY_REASONS",
    "type": "String"
  },
  "responseElements": {
    "version": 1,
    "tier": "Standard"
  },
  "eventID": "b8f28767-d9c0-41ca-8aa0-878a68b2bca4",
  "requestID": "f0a586f8-c550-4b10-b538-4b32c6b132d6"
}
```

Log chi tiết cho event xóa parameter:

```json
{
  "eventTimeICT": "2026-07-17 01:17:25 ICT",
  "eventSource": "ssm.amazonaws.com",
  "eventName": "DeleteParameter",
  "user": "arn:aws:iam::511825856493:user/cdo04-an",
  "accessKeyId": "AKIAXOKZSY7WTLQN55U6",
  "sourceIPAddress": "116.109.13.201",
  "userAgent": "aws-cli/2.34.33 ... os/macos#25.3.0 ... md/arch#arm64",
  "requestParameters": {
    "name": "/forensic-drill/mandate04-23228"
  },
  "errorCode": null,
  "eventID": "455cc7cd-17b6-44b6-8f4b-40c4ef55e8dd",
  "requestID": "a96dccde-f0a5-42c9-a6d5-bc978a9ff01e"
}
```

## Kết Luận Case 2

Hiện trường khớp mô tả:

- Ai thao tác: `arn:aws:iam::511825856493:user/cdo04-an`
- Làm gì: tạo SSM Parameter `/forensic-drill/mandate04-23228`, đọc lại, rồi xóa
- Gồm mấy hành động: 3 hành động chính, gồm `PutParameter`, `GetParameter`, `DeleteParameter`
- Lúc nào: `2026-07-17 01:17:22 -> 01:17:25 ICT`
- Từ IP nào: `116.109.13.201`
- Công cụ nào: AWS CLI `2.34.33` trên macOS arm64
- Object hiện tại: theo CloudTrail, đã bị xóa thành công bằng `DeleteParameter`

Kết luận điều tra: đây là thao tác AWS infra ngoài Kubernetes cluster, cụ thể là AWS Systems Manager Parameter Store. IAM user `cdo04-an` đã tạo parameter `/forensic-drill/mandate04-23228`, đọc lại, rồi xóa parameter này trong khoảng 3 giây.

---

# Kết Luận Chung

Hai hiện trường có cùng actor, cùng IP nguồn và cùng access key:

- Actor: `arn:aws:iam::511825856493:user/cdo04-an`
- Access key: `AKIAXOKZSY7WTLQN55U6`
- Source IP: `116.109.13.201`
- Nền tảng client: macOS arm64

Chuỗi hành vi:

1. `2026-07-16 23:47 ICT`: tạo rồi xóa Kubernetes ConfigMap `drill-marker-8398` trong namespace `techx-tf4`.
2. `2026-07-17 01:17 ICT`: tạo rồi xóa AWS SSM Parameter `/forensic-drill/mandate04-23228` ngoài cluster.

Không có bằng chứng cho thấy tài khoản `cdo04-an` bị xóa. Các object cấu hình trong hai case đã bị xóa thành công theo audit log tương ứng.
