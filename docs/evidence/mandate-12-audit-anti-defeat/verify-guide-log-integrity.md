# Hướng Dẫn Xác Minh Toàn Vẹn Log (Log File Integrity Verification Guide)
## Mã Task: Task 43 (MANDATE-12 · CDO07 · Auditability)

Tài liệu này đóng vai trò là hướng dẫn quy trình xác minh và ghi nhận bằng chứng dạng văn bản (text-based evidence) cho tính toàn vẹn của hệ thống CloudTrail logs, phục vụ việc đối chiếu trực tiếp với Mentor hoặc xuất báo cáo (export task evidence).

---

## 1. Thông Tin Chung & Thiết Lập Cấu Hình

| Thông tin | Giá trị | Ghi chú |
|---|---|---|
| **Dịch vụ xác minh** | AWS CloudTrail | Theo dõi API activity |
| **Cơ chế bảo vệ** | S3 Object Lock & SHA-256 Digest | Chống sửa/xóa & Phát hiện giả mạo |
| **CloudTrail Name** | `tf4-general-cloudtrail` | Trail chính của EKS cluster |
| **CloudTrail ARN** | `arn:aws:cloudtrail:us-east-1:511825856493:trail/tf4-general-cloudtrail` | Cố định của hệ thống |
| **AWS CLI Profile** | `tf4` | Profile SSO đã đăng nhập |
| **Vùng hoạt động (Region)**| `us-east-1` | Nơi chứa cụm chính |

---

## 2. Quy Trình Xác Minh Từng Bước (CLI Commands)

Thực hiện chạy tuần tự 3 câu lệnh sau trên môi trường terminal để lấy thông tin bằng chứng văn bản.

### Bước 2.1: Xác thực danh tính hoạt động
Đảm bảo bạn đang sử dụng đúng profile đăng nhập SSO của dự án.
*   **Câu lệnh:**
    ```bash
    aws sts get-caller-identity --profile tf4
    ```
*   **Mẫu kết quả thành công (Text Evidence):**
    ```json
    {
        "UserId": "AROAXXXXXXXXXXXXXXXXX:username@techx-corp.com",
        "Account": "511825856493",
        "Arn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_.../username"
    }
    ```

### Bước 2.2: Xác thực tính năng bảo mật mật mã đã kích hoạt
Kiểm tra cấu hình của CloudTrail để đảm bảo flag `LogFileValidationEnabled` đã được bật (`true`).
*   **Câu lệnh:**
    ```bash
    aws cloudtrail describe-trails --profile tf4 \
      | jq '.trailList[] | select(.Name=="tf4-general-cloudtrail") | {Name: .Name, LogFileValidationEnabled: .LogFileValidationEnabled}'
    ```
*   **Mẫu kết quả thành công (Text Evidence):**
    ```json
    {
      "Name": "tf4-general-cloudtrail",
      "LogFileValidationEnabled": true
    }
    ```

### Bước 2.3: Thực hiện chạy đối chiếu chữ ký số (Validate)
Chạy câu lệnh quét và kiểm tra các gói log đã được ký số của AWS trong một khoảng thời gian nhất định.
*   **Câu lệnh thực hiện (Demo/Báo cáo):**
    ```bash
    aws cloudtrail validate-logs \
      --trail-arn arn:aws:cloudtrail:us-east-1:511825856493:trail/tf4-general-cloudtrail \
      --start-time "2026-07-20T01:00:00Z" \
      --end-time "2026-07-20T03:00:00Z" \
      --profile tf4
    ```

---

## 3. Bằng Chứng Thực Tế (Actual Text Evidence Run - 20/07/2026)

Dưới đây là log ghi nhận chạy thực tế thành công của kỹ sư vận hành vào lúc **10:14:53+07:00 ngày 20/07/2026** (được lưu trữ dưới dạng text để thay thế cho ảnh chụp màn hình khi xuất báo cáo):

```text
Validating log files for trail arn:aws:cloudtrail:us-east-1:511825856493:trail/tf4-general-cloudtrail between 2026-07-20T01:00:00Z and 2026-07-20T03:00:00Z

Results requested for 2026-07-20T01:00:00Z to 2026-07-20T03:00:00Z
Results found for 2026-07-20T01:00:00Z to 2026-07-20T02:34:08Z:

2/2 digest files valid
70/70 log files valid

No log files were found with invalid digests.
No digest files were found that did not have a corresponding metadata record.
No log files were found that did not have a valid metadata record.

Validation completed.
```

---

## 4. Giải Trình Cơ Chế Chống "Làm mỏng / Sửa log" cho Mentor

Khi Mentor yêu cầu trình bày lý thuyết để chứng minh tính tin cậy của log:

1.  **Cơ chế Validation (Mật mã hóa):** 
    AWS sử dụng thuật toán ký số **SHA256withRSA**. Các file digest chứa mã hash SHA-256 của các file log thô, sau đó được ký số bằng khóa riêng của CloudTrail. Khi chạy lệnh `validate-logs`, AWS CLI tải public key về và kiểm tra xem mã hash thực tế của log có khớp với mã hash được lưu trữ trong file digest hay không. Nếu hacker sửa dù chỉ 1 ký tự, mã hash sẽ thay đổi và validation sẽ thất bại ngay lập tức (`invalid digest`).
2.  **Cơ chế Chaining (Chống mất/xóa log):**
    Mỗi file digest mới đều có trường `previousDigestHashValue` chứa mã hash của file digest giờ trước đó. Cấu trúc này tạo thành một chuỗi liên kết liên tục (block-chain style). Nếu kẻ tấn công xóa một file log hoặc xóa một file digest, chuỗi liên kết sẽ bị đứt quãng, lệnh validate sẽ cảnh báo có khoảng trống dữ liệu (`missing/invalid metadata record`).
3.  **Cơ chế Bất biến vật lý (S3 Object Lock Compliance):**
    Ngăn chặn hacker xóa hoàn toàn file log hoặc file digest từ gốc S3. Toàn bộ bucket log được cấu hình Object Lock ở chế độ **Compliance Mode** trong 90 ngày, khiến cho ngay cả Root Account cũng không thể rút ngắn thời hạn hay xóa đi để phi tang dấu vết.
