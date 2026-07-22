# Kế Hoạch Triển Khai Tasks Week 3 - AIO (Đình Thông Trần)

Tài liệu này tổng hợp danh sách các tasks và kế hoạch triển khai chi tiết cho **Week 3** của nhóm AIO1, tập trung vào **AI Mandate #15 (Trustworthy AIOps Detection)** và **AI Mandate #7b (AIOps Detection · Chạy thật + Đo đạc)**. 

---

## 1. Danh Sách Các Tasks Week 3 (Jira Assigned)

| Mã Task | Tên Task | Trạng Thái | Người Thực Hiện | Mục Tiêu Chính |
|---|---|---|---|---|
| **TF4AIO-80** | AI MANDATE #15 | In Progress | Trần Đình Thông | Xây dựng hệ thống phát hiện sự cố (AIOps Detector) chạy liên tục trên cụm, phân biệt được hệ thống tải cao (busy) và hệ thống lỗi (broken). |
| **TF4AIO-72** | AI MANDATE #7b | In Progress | Đội AIO | Chạy thực nghiệm end-to-end (E2E), đo đạc các chỉ số Precision, Recall và Lead-time (MTTD) khi bơm sự cố. |
| **TF4AIO-77** | [Mandate 07][AIE] Run e2e live run and measure precision/recall | In Progress | Trần Đình Thông | Thực thi kịch bản diễn tập sự cố (failure drill) thực tế trên staging/production để lấy minh chứng alert cho chặng 7b. |

---

## 2. Kế Hoạch Triển Khai Chi Tiết (Implementation Plan)

### 🎯 TF4AIO-80: AI MANDATE #15 — Trustworthy AIOps Detection

#### 1. Định nghĩa "Normal" vs "Anomalous" (Phân biệt Busy vs Broken)
Hệ thống detector phải so sánh các thông số hiện tại với **độ lệch chuẩn động (robust baseline)** của chính dịch vụ đó, thay vì dùng các ngưỡng cứng (static thresholds) dễ gây báo động giả khi hệ thống tải cao.
*   **Latency p95:** Safety floor là `1,000 ms`.
    *   *Normal:* Dưới 1,000 ms hoặc biến động nhẹ quanh Median lịch sử 30 phút.
    *   *Anomalous (Acute):* Hiện tại $\ge 1,000$ ms và tỷ lệ tăng so với baseline $\ge 1.5$ lần, HOẶC z-score $\ge 3$ đồng thời EWMA residual $\ge 1.0$.
    *   *Anomalous (Gradual):* Xu hướng tăng tuyến tính (linear trend) liên tục trong 6 chu kỳ đo, tốc độ tăng $\ge 25\%$ kể cả khi chưa chạm ngưỡng safety floor 1,000 ms.
*   **Request Error Rate / LLM Error Rate:** Safety floor là `5%`.
    *   *Normal:* Tỷ lệ lỗi dưới 5%. Các chu kỳ có lưu lượng cực thấp (dưới 20 requests/5 phút đối với app hoặc dưới 5 calls/5 phút đối với LLM) sẽ được bỏ qua để tránh gây sai số tỷ lệ.
    *   *Anomalous:* Tỷ lệ lỗi $\ge 5\%$ kèm theo z-score/EWMA tăng mạnh.

#### 2. Kiến trúc & Luồng xử lý của Detector Pod
*   Detector được đóng gói thành một workload chạy liên tục trong cụm EKS (Namespace `techx-tf4`).
*   **Luồng xử lý (Control Flow):**
    ```text
    Prometheus (Scrape metrics) 
      -> Detector (Poll mỗi 45 giây)
      -> Median/MAD Filter (Lọc nhiễu đột biến trong quá trình học baseline)
      -> Kiểm tra 2 luồng phát hiện (Acute-floor path & Gradual-drift path)
      -> Bắn cảnh báo qua Alertmanager tới Slack/Email (nếu lỗi kéo dài >= 2 chu kỳ đo)
    ```
*   **Output cảnh báo (Incident Summary):** Mỗi incident sinh ra phải đi kèm thông tin chi tiết: Tên dịch vụ lỗi, loại sự cố (Latency/Error), RCA (Root Cause Analysis) định vị dịch vụ phát thải lỗi, độ tin cậy (Confidence score), mã câu truy vấn PromQL để debug nhanh và link Grafana Explore tương ứng.

#### 3. Chốt chặn Remediation (Khắc phục tự động)
*   Mặc định biến môi trường `REMEDIATION_MODE=dry-run`. Detector không được phép tự ý thay đổi hệ thống.
*   Chỉ khi được bật `REMEDIATION_MODE=live` và có **token phê duyệt hợp lệ** (không quá hạn), hệ thống mới kích hoạt rollback thông qua việc tương tác với Kubernetes API để khôi phục ReplicaSet cũ.
*   Sau khi rollback, hệ thống phải chạy xác thực (Verification) trong 5 phút. Nếu p95 không phục vụ lại bình thường hoặc error rate storefront $\ge 1\%$, hệ thống phải tự khôi phục lại pod template cũ và nâng mức cảnh báo cho SRE/On-call.
*   **Tuyệt đối không tự ý thay đổi cấu hình flagd để xử lý sự cố.**

---

### 🎯 TF4AIO-72 & TF4AIO-77: Diễn Tập E2E & Đo Đạc Chỉ Số (Mandate 7b / 15)

#### 1. Phương pháp bơm sự cố diễn tập (Controlled Failure Drill)
*   Quy trình diễn tập được CDO phê duyệt và không sử dụng các lệnh sửa đổi cụm trực tiếp (như `kubectl edit/patch` các ConfigMap/Deployment).
*   **Cách thức thực hiện:** 
    *   Sử dụng cơ chế thay đổi cấu hình qua GitOps (ArgoCD) để kích hoạt cờ lỗi giả định (như `llmRateLimitError=on` hoặc `llmInaccurateResponse=on`) trong tệp `demo.flagd.json`.
    *   Sử dụng công cụ Locust/grpcurl để tạo tải hoặc gọi trực tiếp API assistant nhằm kiểm chứng luồng hoạt động.
    *   Sau khi ghi nhận đủ bằng chứng, tiến hành revert GitOps PR về trạng thái ban đầu và chờ ArgoCD báo `Synced/Healthy`.

#### 2. Đo đạc các chỉ số vận hành AIOps
Thực hiện chạy chuỗi 3 kịch bản liên tiếp để tính toán chất lượng của Detector:
1.  **Scenario A (Sự cố đơn lẻ):** Bơm lỗi latency/error trên 1 dịch vụ.
2.  **Scenario B (Nhiễu đè sự cố - Masking):** Bơm một đợt spike nhiễu tải cao ngắn hạn, sau đó bơm lỗi nhỏ kéo dài ở dịch vụ khác. Kiểm tra xem detector có lọc bỏ được spike nhiễu và phát hiện đúng lỗi nhỏ kia hay không.
3.  **Scenario C (Tải cao bình thường - Busy Normal):** Tăng lượng truy cập storefront nhưng không bơm lỗi. Detector không được phép phát cảnh báo.

*   **Chỉ số tính toán:**
    *   **Recall:** Tỷ lệ số sự cố phát hiện được trên tổng số sự cố thực tế bơm vào (Mục tiêu: $100\%$).
    *   **Precision:** Tỷ lệ số lần cảnh báo đúng trên tổng số lần hệ thống phát cảnh báo (Mục tiêu: $\ge 90\%$).
    *   **Lead-Time / MTTD:** Thời gian trung bình từ lúc sự cố bắt đầu xuất hiện cho đến khi detector phát ra cảnh báo đầu tiên (Mục tiêu: $< 2$ phút).

---

## 3. Các Minh Chứng Cần Chuẩn Bị Khi Nộp Bài (Grading Deliverables)

Khi hoàn tất diễn tập và code, các minh chứng sau phải được đính kèm vào Jira ticket `AI MANDATE #15` / `TF4AIO-80`:
1.  **Link PR/Commit:** Chứa mã nguồn của detector pod, các tệp Helm values cấu hình, và bộ test cases.
2.  **Lệnh chạy kiểm thử và Replay:** Câu lệnh chạy replay tự động bộ kịch bản lỗi để chấm điểm cục bộ.
3.  **Ảnh chụp màn hình (Screenshots/Logs):**
    *   Ảnh thông báo alert gửi về kênh Slack/Email on-call với đầy đủ nội dung thông tin incident, PromQL và link debug.
    *   Logs của detector thể hiện việc lọc Median/MAD và phân biệt thành công các kịch bản.
4.  **Tài liệu ADR ký tên (ADR-007):** Quyết định thiết kế kiến trúc detector, các tham số cấu hình MAD/EWMA hạt giống (seeds), và phân tích độ nhạy (sensitivity analysis).
