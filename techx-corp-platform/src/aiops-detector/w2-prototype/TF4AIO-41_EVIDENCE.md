# TF4AIO-41: Detect AI-specific LLM timeout/error Evidence

## 1. Mục tiêu (Objective)
Phát hiện các sự cố liên quan đến LLM (timeout, error, rate limit - 429) trong luồng AI-path dựa trên các tín hiệu quan trắc (metric, log, trace).

## 2. Triển khai (Implementation)
Đã tạo module `llm_timeout_detector.py` sử dụng logic truy vấn kết hợp:
* **Metrics (Prometheus):** Tìm kiếm tốc độ tăng (rate) của `aiops_llm_calls_total` với các nhãn trạng thái `status=~"error|timeout|429"`.
* **Logs (OpenSearch):** Sử dụng Lucene query `kubernetes.labels.app:"{service}" AND (message:*timeout* OR message:*429* OR message:*rate limit*) AND message:(*llm* OR *openai* OR *bedrock*)` để bắt các ngoại lệ (exceptions) sinh ra do model provider.

## 3. Khoảng trống tín hiệu (Missing Signal Gaps & Limitations)
- **Traces (Jaeger):** Mặc dù Jaeger đang có mặt trong stack (theo task TF4AIO-12), OpenTelemetry span events cho LLM failures đôi khi không mang `status_code = error` nếu SDK bên thứ ba tự động fallback (handled gracefully). Cần phải đảm bảo ứng dụng set `span.set_status(Status(StatusCode.ERROR))` khi request đến LLM thất bại thì trace mới hữu dụng.
- **Cost Metrics:** Hiện chưa map tín hiệu "budget exhausted" (hết hạn mức) một cách trực tiếp ở metric, chỉ bắt được thông qua log.
- **Provider Outage:** Nếu API provider sập hoàn toàn (connection reset), hệ thống cần phân biệt giữa network internal và network external.

## 4. Bằng chứng (Evidence Links)
- Mã nguồn detector: `src/aiops-detector/w2-prototype/llm_timeout_detector.py`
- Mã nguồn tóm tắt sự cố: `src/aiops-detector/w2-prototype/incident_summary.py`
- Tích hợp vào RCA Engine (Task 38): `src/aiops-detector/rca-rule-engine/rca_detector.py` (hàm `check_ai_telemetry`, trọng số 0.20)
