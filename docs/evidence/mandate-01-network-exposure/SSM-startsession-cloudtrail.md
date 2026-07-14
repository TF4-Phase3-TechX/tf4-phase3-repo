# CDO07 - Bằng chứng CloudTrail StartSession cho Mandate 01

**Team thực hiện:** CDO07
**Người thực hiện:** Lê Trung Trực
**Người kiểm tra:** Bùi Thành Nghĩa
**Ngày thực hiện:** 2026-07-14

## Phạm vi kiểm tra

- Account: `511825856493`
- Region: `us-east-1`
- Event cần kiểm tra: `StartSession`
- Bastion: `i-072084d1cf0b2f1c9`

## Lệnh kiểm tra

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --max-results 2 \
  --output json
```

Không lưu raw output đầy đủ của CloudTrail vì payload gốc có các trường nằm ngoài allowlist evidence, ví dụ `AccessKeyId`, `tokenValue` và `streamUrl`.

## Evidence đã lọc an toàn

```json
[
  {
    "eventID": "1b2792e7-22d6-4745-90aa-78aba1d2a6dd",
    "eventName": "StartSession",
    "eventSource": "ssm.amazonaws.com",
    "eventTime": "2026-07-14T00:08:32Z",
    "awsRegion": "us-east-1",
    "recipientAccountId": "511825856493",
    "sourceIPAddress": "118.68.56.162",
    "userIdentity": {
      "type": "AssumedRole",
      "arn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/quang.tranminh",
      "accountId": "511825856493",
      "principalId": "AROAXOKZSY7W74IQD5ZRM:quang.tranminh",
      "sessionIssuerArn": "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882"
    },
    "requestParameters": {
      "target": "i-072084d1cf0b2f1c9",
      "documentName": "AWS-StartPortForwardingSession",
      "parameters": {
        "localPortNumber": ["8089"],
        "portNumber": ["18089"]
      }
    },
    "responseElements": {
      "sessionId": "quang.tranminh-ilpxvkhghl9vs9ia2xfdyp4dka"
    },
    "eventType": "AwsApiCall",
    "managementEvent": true,
    "eventCategory": "Management"
  },
  {
    "eventID": "6c350b8d-c222-409e-b1d5-dbe5bb2b27b5",
    "eventName": "StartSession",
    "eventSource": "ssm.amazonaws.com",
    "eventTime": "2026-07-14T00:07:14Z",
    "awsRegion": "us-east-1",
    "recipientAccountId": "511825856493",
    "sourceIPAddress": "118.68.56.162",
    "userIdentity": {
      "type": "AssumedRole",
      "arn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/quang.tranminh",
      "accountId": "511825856493",
      "principalId": "AROAXOKZSY7W74IQD5ZRM:quang.tranminh",
      "sessionIssuerArn": "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882"
    },
    "requestParameters": {
      "target": "i-072084d1cf0b2f1c9",
      "documentName": "AWS-StartPortForwardingSession",
      "parameters": {
        "localPortNumber": ["8089"],
        "portNumber": ["18089"]
      }
    },
    "responseElements": {
      "sessionId": "quang.tranminh-7r4p58odr7r33byegkqyecifba"
    },
    "eventType": "AwsApiCall",
    "managementEvent": true,
    "eventCategory": "Management"
  }
]
```

## Đối chiếu yêu cầu audit

| Câu hỏi audit | Field bằng chứng | Kết quả |
|---|---|---|
| Ai vào? | `userIdentity.arn` | `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/quang.tranminh` |
| Vào lúc nào? | `eventTime` | `2026-07-14T00:07:14Z`, `2026-07-14T00:08:32Z` |
| Từ đâu? | `sourceIPAddress` | `118.68.56.162` |
| Vào bastion nào? | `requestParameters.target` | `i-072084d1cf0b2f1c9` |
| Đúng account/region không? | `recipientAccountId`, `awsRegion` | `511825856493`, `us-east-1` |

## Kết luận

```text
PASS
```

CloudTrail có các event `StartSession` trong khoảng thời gian xác minh hiện tại, thuộc account `511825856493`, region `us-east-1`, và trỏ tới đúng bastion đã được duyệt `i-072084d1cf0b2f1c9`. Các event có đủ user ARN, timestamp, source IP và target bastion, thể hiện document SSM port-forward `AWS-StartPortForwardingSession`.

CloudTrail chứng minh được audit trail ở lớp AWS API cho đường truy cập riêng tư qua SSM vào bastion. CloudTrail không chứng minh hành động HTTP cụ thể bên trong Grafana, Jaeger hoặc Load Generator; đây là giới hạn đúng với residual risk đã được nêu trong review CDO07.
