# ADR-009: Bounded Retry, Circuit Breaker, and Honest Fallback for LLM Integration

- Date: 2026-07-26
- Status: **Accepted**
- Owner: Lead AIOps/SRE

## Context
Dịch vụ `product-reviews` hiện tại phụ thuộc trực tiếp vào AWS Bedrock (LLM) để tổng hợp đánh giá và cung cấp tính năng Shopping Copilot. Trong môi trường Production, các cuộc gọi mạng đến LLM tiềm ẩn rủi ro rất cao về độ trễ (latency spikes), giới hạn tốc độ (429 Rate Limit), hoặc lỗi 5xx. 
Cấu hình hiện tại (`max_attempts: 0`) khiến hệ thống quá mỏng manh, dẫn đến lỗi "Silent Failure" (chết ngầm) hoặc treo giao diện người dùng. Việc thiếu cơ chế cô lập lỗi (Fault Isolation) có thể gây ra thảm họa sụp đổ dây chuyền (Cascading Failure) làm cạn kiệt Connection Pool của toàn bộ hệ thống gRPC khi Bedrock gặp sự cố.

## Decision
Chúng tôi quyết định áp dụng chiến lược **Phòng thủ theo chiều sâu (Defense-in-Depth)** với 4 lớp kiến trúc sau:

1. **Capped Retry & Backoff (Tầng SDK):** Cấu hình AWS Boto3 Client sử dụng `retries={"max_attempts": 3, "mode": "standard"}`. Chế độ "standard" tự động áp dụng thuật toán Exponential Backoff và Jitter để cứu vãn các lỗi chớp nhoáng (Transient errors) mà không gây ra bão thử lại (Retry Storm).
2. **Circuit Breaker (Tầng Application):** Triển khai Ngắt mạch cục bộ (In-memory Circuit Breaker) với ngưỡng `5 lỗi / 30 giây` và `cooldown 60 giây`. Mạch CHỈ mở khi gặp lỗi hạ tầng (Timeout/5xx), BỎ QUA các lỗi về ảo giác của mô hình (Malformed JSON) để tránh mở mạch oan uổng.
3. **Honest Fallback (Tầng UI/UX):** Khi Circuit Breaker mở hoặc nhận mã lỗi từ Backend, Frontend tuyệt đối không bịa đặt dữ liệu (Fabrication) hoặc văng lỗi 500. Chuyển sang hiển thị "Đèn trạng thái 3 màu" (Xanh/Vàng/Đỏ) và thông báo: *"Hệ thống AI đang gặp gián đoạn tạm thời"* (Graceful Degradation).
4. **External Fault Injection (Tầng Chaos Engineering):** Bác bỏ phương án dùng "Magic Keywords" nhúng vào mã nguồn. Bắt buộc sử dụng hạ tầng Feature Flags (`flagd` với cờ `llmRateLimitError` và `llmInaccurateResponse`) để bơm lỗi từ bên ngoài ranh giới ứng dụng, đảm bảo tính nguyên bản của mã nghiệp vụ (Code Purity).

## Alternatives considered
- **Tự viết vòng lặp `while True` để retry:** Bị từ chối vì rủi ro tạo ra "Retry Storm" đánh sập hạ tầng mạng nội bộ.
- **Ngắt mạch cả khi LLM trả về JSON rác:** Bị từ chối vì JSON rác là lỗi của Mô hình (Model Hallucination), không phải lỗi hạ tầng. Ngắt mạch sẽ làm gián đoạn oan các request hợp lệ khác.
- **Dùng Magic Keywords (vd: `fault:timeout`) để test:** Bị từ chối vì vi phạm nguyên tắc cách ly mã kiểm thử khỏi mã Production, rủi ro bảo mật nghiêm trọng nếu người dùng vô tình gõ trúng.

## Consequences
- **Positive:** Giới hạn được bán kính ảnh hưởng (Blast Radius) khi AWS Bedrock sập. Hệ thống tự động phục hồi. Đội ngũ AIOps/SRE có tín hiệu đo lường (Telemetry) rõ ràng để chẩn đoán. Trải nghiệm người dùng được bảo vệ.
- **Negative (Trade-off):** Cấu hình `max_attempts: 3` kết hợp Backoff đồng nghĩa với việc đối với những request bị nghẽn mạng, người dùng sẽ phải chịu **độ trễ (Latency) cao hơn (có thể lên tới 5-10 giây)** trước khi hệ thống chính thức bỏ cuộc và hiển thị thông báo Fallback. Chúng tôi chấp nhận đánh đổi Latency để lấy Reliability (Độ tin cậy).
