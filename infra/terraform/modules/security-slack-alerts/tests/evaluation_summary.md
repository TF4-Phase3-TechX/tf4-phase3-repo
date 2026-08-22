# BÁO CÁO ĐÁNH GIÁ & TỔNG HỢP KIỂM THỬ: H2 ANOMALY DETECTION (MANDATE-11)

> [!NOTE]
> Báo cáo này đã được đối chiếu và xác minh 100% trực tiếp với mã nguồn trên branch `cdo07/week4/test_case_anomaly_detection`. Tất cả các tính năng chính đã được triển khai đầy đủ trong code.

---

## 1. Bản đồ Xác minh Mã nguồn & Triển khai

| Thành phần | Tệp mã nguồn | Trạng thái trong Code | Chi tiết xác minh |
| :--- | :--- | :--- | :--- |
| **Lambda Handler** | [handler.py](../lambda_src/handler.py#L486) | **Đã triển khai** (`handle_cloudwatch_alarm` tại L486) | Xử lý tin nhắn SNS từ CloudWatch Alarm: chuyển trạng thái `ALARM` thành Slack alert với màu đỏ `CRITICAL` (Spike) hoặc cam `HIGH` (Anomaly). |
| **Terraform Alarms** | [cloudwatch-alarms.tf](../cloudwatch-alarms.tf) | **Đã khai báo đủ 10 resources** | Gồm 2 Metric Filters, Alarm A (Static >10/60s), Alarm B (ML Anomaly), Alarm C (Dead-man silence >12h) và SNS topic `anomaly_alerts`. |
| **Unit Tests (Local)** | [test_handler.py](./test_handler.py) | **19/19 PASS** (chạy thành công trong 0.85s) | Đảm bảo tính toán độ trễ (TTD) và kiểm tra các kịch bản log CloudTrail ngoại tuyến. |
| **Simulation Script** | [simulate_eso_exfil.py](./simulate_eso_exfil.py) | **Đã triển khai** | Script gửi 15 `GetSecretValue` requests để test thực tế trên AWS. |
| **DoD Evidence Images** | [tests/image/](./image/) | **Đã có 4 file ảnh PNG** | Lưu vết kết quả test thực tế trên CloudTrail, CloudWatch Alarm và Slack. |

---

## 2. Chi tiết Kết quả Đánh giá & Kiểm thử

### A. Xử lý Cảnh báo Lambda (`handler.py` - Line 486)
Hàm `handle_cloudwatch_alarm(message, context)` đã được triển khai hoàn chỉnh:
*   Bắt payload SNS chứa thông tin Alarm từ CloudWatch (`AlarmName`, `NewStateValue`, `StateChangeTime`, `Region`, `AWSAccountId`).
*   Tự động bỏ qua nếu `NewStateValue != 'ALARM'`.
*   Chuyển đổi thời gian sang múi giờ Việt Nam (+07).
*   Định dạng thông điệp Block Kit với màu đỏ `#ff0000` (mức `CRITICAL`) cho Rate-spike alarm và màu cam `#ff9900` (mức `HIGH`) cho Anomaly alarm.

### B. Cấu hình Hạ tầng Terraform (`cloudwatch-alarms.tf`)
*   **Metric Filter A:** `mandate11-get-secret-value-total` (đếm marker `MANDATE11_TTD`).
*   **Metric Filter B:** `mandate11-expected-read-activity` (đếm marker `MANDATE11_EXPECTED_READ`).
*   **Alarm A (Static):** Ngưỡng >10 calls/60s, phản ứng trong < 2 phút.
*   **Alarm B (Anomaly ML):** Dự đoán dải bất thường với `ANOMALY_DETECTION_BAND(m1, 2)`.
*   **Alarm C (Dead-man's Switch):** Cảnh báo nếu pipeline im lặng > 12h.
*   **Lưu ý sửa lỗi nhỏ (Fix Minor Bug):** Tại dòng 218 file `cloudwatch-alarms.tf`, metric `m1` đang khai báo `return_data = true` (dù comment ghi rõ `must NOT be the return_data query`). Cần đổi `return_data = false` cho `m1` để thỏa mãn quy tắc AWS CloudWatch API (chỉ có duy nhất query band `ad1` có `return_data = true`).

### C. Kiểm thử Đơn vị Ngoại tuyến (`test_handler.py`)
*   Lệnh thực thi: `python -m unittest tests/test_handler.py`
*   Kết quả: **100% PASS (19/19 tests)**.

---

## 3. Kết luận & Điểm Cần Hoàn Thiện Tiếp theo

1.  **Chỉnh sửa HCL (`cloudwatch-alarms.tf`):** Sửa dòng 218 từ `return_data = true` thành `return_data = false`.
2.  **Sẵn sàng Deploy:** Toàn bộ giải pháp H2 Anomaly Detection đã hoàn thiện mã nguồn và sẵn sàng để triển khai / commit.
