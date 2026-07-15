# TF4AIO-41: Detect AI-specific LLM timeout/error Evidence

## 1. Mục tiêu (Objective)
Phát hiện các sự cố liên quan đến LLM (timeout, error, rate limit - 429) trong luồng AI-path dựa trên các tín hiệu quan trắc (metric, log, trace).

## 2. Triển khai (Implementation)
Đã tạo module `llm_timeout_detector.py` sử dụng logic truy vấn kết hợp:
* **Metrics (Prometheus):** Tìm kiếm tỷ lệ lỗi gọi LLM (`status=~"error|timeout|429"`) lớn hơn 5% trong cửa sổ 5 phút: `sum(rate(..error..[5m])) / sum(rate(..all..[5m])) > 0.05`.
* **Logs (OpenSearch):** Sử dụng Lucene Query String filter `kubernetes.labels.app:"product-reviews" AND (message:*timeout* OR message:*429* OR message:*rate limit*) AND message:(*llm* OR *openai* OR *bedrock*)` để bắt các ngoại lệ sinh ra do model provider.

## 3. Khoảng trống tín hiệu (Missing Signal Gaps & Limitations)
- **Traces (Jaeger):** Mặc dù Jaeger đang có mặt trong stack (theo task TF4AIO-12), OpenTelemetry span events cho LLM failures đôi khi không mang `status_code = error` nếu SDK bên thứ ba tự động fallback (handled gracefully). Cần phải đảm bảo ứng dụng set `span.set_status(Status(StatusCode.ERROR))` khi request đến LLM thất bại thì trace mới hữu dụng.
- **Cost Metrics:** Hiện chưa map tín hiệu "budget exhausted" (hết hạn mức) một cách trực tiếp ở metric, chỉ bắt được thông qua log.
- **Provider Outage:** Nếu API provider sập hoàn toàn (connection reset), hệ thống cần phân biệt giữa network internal và network external.

## 4. Bằng chứng (Evidence Links)
- Mã nguồn detector: `techx-corp-platform/src/aiops-detector/w2-prototype/llm_timeout_detector.py`

### 4.1. Kết quả chạy thử nghiệm MVP (Mock Output)
Kết quả output JSON từ Detector khi có tín hiệu lỗi đồng thời từ cả Metric và Log (OpenSearch):

```json
{
  "timestamp": "2026-07-15T15:40:00Z",
  "rule": "ai_llm_timeout_error",
  "service": "product-reviews",
  "environment": "production",
  "tenant_id": "default",
  "severity": "high",
  "evidence": {
    "metrics_found": 1,
    "logs_found": 15,
    "metric_details": [
      {
        "metric": {
          "__name__": "aiops_llm_calls_total",
          "environment": "production",
          "service": "product-reviews",
          "status": "error"
        },
        "value": [1689408000.0, "0.12"]
      }
    ],
    "log_details": [
      {
        "_index": "logs-product-reviews",
        "_source": {
          "message": "openai.error.Timeout: Request timed out: HTTPSConnectionPool(host='api.openai.com', port=443): Read timed out.",
          "kubernetes": {"labels": {"app": "product-reviews"}}
        }
      }
    ]
  }
}
```
