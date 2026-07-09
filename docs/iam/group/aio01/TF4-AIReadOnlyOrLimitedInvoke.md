# Permission Set: TF4-AIReadOnlyOrLimitedInvoke

Tài liệu này chi tiết hóa quyền hạn của Permission Set `TF4-AIReadOnlyOrLimitedInvoke`. Đây là tập hợp quyền dành riêng cho các kỹ sư và chuyên gia AI/ML, cho phép gọi và kiểm định các mô hình ngôn ngữ lớn (LLMs) được chỉ định và theo dõi hiệu suất của chúng.

## 📄 Nội dung Policy (JSON)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AIServiceObservabilityReadOnly",
            "Effect": "Allow",
            "Action": [
                "cloudwatch:Describe*",
                "cloudwatch:Get*",
                "cloudwatch:List*",
                "logs:Describe*",
                "logs:Get*",
                "logs:FilterLogEvents",
                "logs:StartQuery",
                "logs:StopQuery",
                "logs:GetQueryResults",
                "eks:DescribeCluster",
                "eks:ListClusters"
            ],
            "Resource": "*"
        },
        {
            "Sid": "LimitedBedrockInvokeAndAudit",
            "Effect": "Allow",
            "Action": [
                "bedrock:ListFoundationModels",
                "bedrock:GetFoundationModel",
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:GetGuardrail",
                "bedrock:ListGuardrails",
                "bedrock:GetAgent",
                "bedrock:ListAgents"
            ],
            "Resource": [
                "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-*",
                "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-*"
            ]
        },
        {
            "Sid": "ReadOnlyApprovedAISecrets",
            "Effect": "Allow",
            "Action": [
                "secretsmanager:DescribeSecret",
                "secretsmanager:GetSecretValue"
            ],
            "Resource": [
                "arn:aws:secretsmanager:us-east-1:511825856493:secret:tf4/aio/*"
            ]
        },
        {
            "Sid": "AIEvalBucketAccess",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::tf4-ai-eval-bucket",
                "arn:aws:s3:::tf4-ai-eval-bucket/*"
            ]
        }
    ]
}
```

---

## 🔍 Giải thích chi tiết Quyền hạn

Policy này gồm 4 Statements với mục đích cụ thể:

### 1. `AIServiceObservabilityReadOnly` (Giám sát hoạt động AI)
* **Hành động**: Các phương thức đọc logs/metrics trên CloudWatch, CloudWatch Logs và mô tả EKS Cluster.
* **Mô tả**: Cho phép theo dõi hiệu năng hệ thống chạy ứng dụng AI, kiểm tra lỗi ứng dụng thông qua logs phát sinh trên Kubernetes (EKS Cluster) hoặc logs từ dịch vụ gọi API.
* **Mục đích**: Giám sát sức khỏe dịch vụ và debug các sự cố hệ thống liên quan tới AI.

### 2. `LimitedBedrockInvokeAndAudit` (Gọi và Kiểm toán Mô hình Bedrock giới hạn)
* **Hành động**: Gọi mô hình (`InvokeModel`, `InvokeModelWithResponseStream`), xem danh sách mô hình (`ListFoundationModels`, `GetFoundationModel`), xem cấu hình rào chắn bảo vệ (`GetGuardrail`, `ListGuardrails`) và Agent (`GetAgent`, `ListAgents`).
* **Tài nguyên**: Giới hạn đối với các mô hình ngôn ngữ được AWS cung cấp tại vùng `us-east-1`:
  * Anthropic Claude 3.5 Sonnet: `arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-*`
  * Meta Llama 3: `arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-*`
* **Mô tả**: Cho phép người dùng chạy thử nghiệm và tương tác trực tiếp với các dòng mô hình Claude 3.5 Sonnet và Llama 3 qua API hoặc AWS console, đồng thời có quyền kiểm toán các thành phần bổ trợ như Guardrails và Agents.
* **Mục đích**: Hỗ trợ việc nghiên cứu phát triển các tính năng AI thế hệ mới (GenAI) trên các mô hình đã được phê duyệt.

### 3. `ReadOnlyApprovedAISecrets` (Đọc các thông tin mật liên quan tới AI)
* **Hành động**: `secretsmanager:DescribeSecret`, `secretsmanager:GetSecretValue`
* **Tài nguyên**: Các secret lưu tại AWS Secrets Manager vùng `us-east-1`, tài khoản `511825856493` có tiền tố path là `tf4/aio/*` (`arn:aws:secretsmanager:us-east-1:511825856493:secret:tf4/aio/*`).
* **Mô tả**: Cho phép lấy giá trị bảo mật (API keys, DB credentials, token, v.v.) của riêng các dịch vụ AIOps/AI đã được phê duyệt.
* **Mục đích**: Cho phép ứng dụng/người dùng lấy các khóa bảo mật cần thiết để chạy dịch vụ AI.

### 4. `AIEvalBucketAccess` (Truy cập dữ liệu đánh giá mô hình)
* **Hành động**: `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`
* **Tài nguyên**: Bucket `tf4-ai-eval-bucket` và các đối tượng bên trong (`arn:aws:s3:::tf4-ai-eval-bucket`, `arn:aws:s3:::tf4-ai-eval-bucket/*`).
* **Mô tả**: Cấp quyền đọc, ghi (tạo mới/ghi đè) và liệt kê tệp tin trong bucket dành riêng cho kiểm thử và đánh giá kết quả AI.
* **Mục đích**: Lưu trữ dữ liệu test cases, kết quả đầu ra của mô hình và các báo cáo đánh giá (Evaluation reports).

---
[⬅️ Quay lại nhóm AIO01](README.md) | [🏡 Quay lại trang chủ IAM Docs](../../README.md)
