**Rollback Steps to Mock LLM:**
Trong trường hợp AI thật gặp sự cố (Timeout, Rate Limit, Model Lỗi), thực hiện ngay các bước sau để trả hệ thống về Mock LLM:
1. Gỡ bỏ biến `OPENAI_API_KEY` khỏi cấu hình Environment / Kubernetes Secret của service `product-reviews`.
2. Cập nhật (hoặc xóa) `LLM_BASE_URL` để nó không trỏ về OpenAI/Gemini nữa (tự động trỏ về `http://llm:8000`).
3. Cập nhật (hoặc xóa) `LLM_MODEL` để nó quay về tên model mock mặc định.
4. Restart pod `product-reviews` (`kubectl rollout restart deployment product-reviews` hoặc qua Makefile).
