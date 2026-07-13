# Task 24 - Bằng chứng CloudTrail StartSession cho CDO04 Mandate 01

## Phạm vi kiểm tra

- Account: `511825856493`
- Region: `us-east-1`
- Event cần kiểm tra: `StartSession`
- Time window kiểm thử: `2026-07-13T16:25:00Z` đến `2026-07-13T16:35:00Z`
- Bastion đã được duyệt: `i-072084d1cf0b2f1c9`
- Role dùng để query: `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/truc.le`

## Lệnh kiểm tra

```bash
aws cloudtrail lookup-events \
  --profile TF4-AuditReadOnlyAndAnalyze \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --start-time '2026-07-13T16:25:00Z' \
  --end-time '2026-07-13T16:35:00Z' \
  --output json
```

Không lưu raw output đầy đủ của CloudTrail vì payload gốc có các field nằm ngoài allowlist evidence, ví dụ `AccessKeyId`, `tokenValue` và `streamUrl`.

## Evidence đã lọc an toàn

```json
[
  {
    "eventID": "8a9650dc-c8a7-4d89-b23f-2791be653b3b",
    "eventName": "StartSession",
    "eventSource": "ssm.amazonaws.com",
    "eventTime": "2026-07-13T16:28:39Z",
    "awsRegion": "us-east-1",
    "recipientAccountId": "511825856493",
    "sourceIPAddress": "117.2.142.253",
    "userIdentity": {
      "type": "AssumedRole",
      "arn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10/nguyen",
      "accountId": "511825856493",
      "principalId": "AROAXOKZSY7WVF3EPHAKY:nguyen",
      "sessionIssuerArn": "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10"
    },
    "requestParameters": {
      "target": "i-072084d1cf0b2f1c9",
      "documentName": null,
      "parameters": null
    },
    "responseElements": {
      "sessionId": "nguyen-cqzlbzsh4onaob6vh2536k3vj4"
    },
    "eventType": "AwsApiCall",
    "managementEvent": true,
    "eventCategory": "Management"
  },
  {
    "eventID": "2ae952a4-1add-452b-ab4c-14fc45a230f6",
    "eventName": "StartSession",
    "eventSource": "ssm.amazonaws.com",
    "eventTime": "2026-07-13T16:27:46Z",
    "awsRegion": "us-east-1",
    "recipientAccountId": "511825856493",
    "sourceIPAddress": "117.2.142.253",
    "userIdentity": {
      "type": "AssumedRole",
      "arn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10/nguyen",
      "accountId": "511825856493",
      "principalId": "AROAXOKZSY7WVF3EPHAKY:nguyen",
      "sessionIssuerArn": "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10"
    },
    "requestParameters": {
      "target": "i-072084d1cf0b2f1c9",
      "documentName": null,
      "parameters": null
    },
    "responseElements": {
      "sessionId": "nguyen-dqvgkfo4di2ta4g9vl5kfqlx8i"
    },
    "eventType": "AwsApiCall",
    "managementEvent": true,
    "eventCategory": "Management"
  },
  {
    "eventID": "983be8ff-62b8-47d7-8ec9-043694c142f2",
    "eventName": "StartSession",
    "eventSource": "ssm.amazonaws.com",
    "eventTime": "2026-07-13T16:27:05Z",
    "awsRegion": "us-east-1",
    "recipientAccountId": "511825856493",
    "sourceIPAddress": "42.116.233.3",
    "userIdentity": {
      "type": "AssumedRole",
      "arn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10/nguyen",
      "accountId": "511825856493",
      "principalId": "AROAXOKZSY7WVF3EPHAKY:nguyen",
      "sessionIssuerArn": "arn:aws:iam::511825856493:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10"
    },
    "requestParameters": {
      "target": "i-072084d1cf0b2f1c9",
      "documentName": "AWS-StartPortForwardingSession",
      "parameters": {
        "localPortNumber": [
          "8089"
        ],
        "portNumber": [
          "18089"
        ]
      }
    },
    "responseElements": {
      "sessionId": "nguyen-5ngengqx66tdy6o8inionxe6q4"
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
| Ai vào? | `userIdentity.arn` | `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10/nguyen` |
| Vào lúc nào? | `eventTime` | `2026-07-13T16:27:05Z`, `2026-07-13T16:27:46Z`, `2026-07-13T16:28:39Z` |
| Từ đâu? | `sourceIPAddress` | `42.116.233.3`, `117.2.142.253` |
| Vào bastion nào? | `requestParameters.target` | `i-072084d1cf0b2f1c9` |
| Đúng account/region không? | `recipientAccountId`, `awsRegion` | `511825856493`, `us-east-1` |

## Kết luận

```text
PASS
```

CloudTrail có các event `StartSession` trong đúng time window đã được duyệt, thuộc account `511825856493`, region `us-east-1`, và trỏ tới đúng bastion đã được duyệt `i-072084d1cf0b2f1c9`. Các event có đủ user ARN, timestamp, source IP và target bastion. Event `983be8ff-62b8-47d7-8ec9-043694c142f2` cũng thể hiện document SSM port-forward `AWS-StartPortForwardingSession` với `portNumber=18089`.

CloudTrail chứng minh được audit trail ở lớp AWS API cho đường truy cập riêng tư qua SSM vào bastion. CloudTrail không chứng minh hành động HTTP cụ thể bên trong Grafana, Jaeger hoặc Load Generator; đây là giới hạn đúng với residual risk đã được nêu trong review CDO07.
