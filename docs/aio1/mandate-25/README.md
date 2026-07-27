# Mandate 25: Khả năng Phục hồi LLM và Kỹ thuật Hỗn loạn (Chaos Engineering)

## Mục tiêu
Triển khai cơ chế phòng thủ 4 lớp vững chắc (Boto3 Capped Retry, Circuit Breaker, Honest Fallback, Feature Flags) nhằm bảo vệ AI Copilot khỏi sự mất ổn định và giới hạn tốc độ (rate limits) của LLM.

## Chi tiết Triển khai
1. **Boto3 Capped Retry**: Được triển khai trong `bedrock_adapter.py` để tự động thử lại các lỗi chớp nhoáng tối đa 3 lần trước khi báo lỗi nhằm ngăn tình trạng treo vô hạn.
2. **Circuit Breaker (Cầu dao ngắt mạch)**: Được triển khai để ngắt mạch và từ chối nhanh các yêu cầu tiếp theo khi nhà cung cấp LLM gặp sự cố (sử dụng thư viện `pybreaker`).
3. **Honest Fallback (Thoái lui trung thực)**: Giao diện người dùng hiển thị một thông báo thoái lui an toàn thay vì sập hoặc hiện ra lỗi chung chung.
4. **Chaos Engineering (OpenFeature/flagd)**: Tích hợp các cờ tính năng (feature flags) của `flagd` (`llmRateLimitError`, `llmInaccurateResponse`) trực tiếp vào bộ chuyển đổi LLM để bơm giả lập lỗi `ThrottlingException` và lỗi JSON rác phục vụ kiểm thử.

## Bằng chứng (Evidence)
Quá trình chạy thử nghiệm chaos engineering đã được xác minh thông qua kịch bản `inject_mandate25_faults.sh`. Bằng chứng về việc mở cầu dao và thực thi logic UI thoái lui có thể tìm thấy tại:
- `evidence/MANDATE25_CHAOS_EVIDENCE.log`

## PRs liên quan
- Nhánh: `aio01/feat/mandate25-resilience`
