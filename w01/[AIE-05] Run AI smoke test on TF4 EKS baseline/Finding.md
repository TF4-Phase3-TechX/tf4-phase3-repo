# Ghi Nhận Hiện Trạng AI (Baseline Findings) & Pitch Notes - Tuần 1

Tài liệu này tổng hợp các phát hiện (Findings) sau khi chạy Smoke Test trên cụm EKS (AIE-06) và các luận điểm bảo vệ (Pitch Notes) để báo cáo với BTC (AIE-07).

---

## 1. Ghi nhận Hiện trạng AI (Baseline Findings)

Dựa trên kết quả chạy thử UI và soi Trace trên Jaeger, team AIO01 ghi nhận các rủi ro sau:

| Phân loại | Nội dung ghi nhận (Finding) | Bằng chứng (Evidence) | Mức độ ảnh hưởng (Impact) | Đề xuất Xử lý |
| :--- | :--- | :--- | :--- | :--- |
| **Kiến trúc** | Hệ thống service LLM trên cụm EKS hiện tại vẫn đang chạy chế độ Mock (giả lập), đọc kết quả từ tệp JSON tĩnh chứ chưa kết nối với mô hình LLM thật (như OpenAI). | [Trace trên Jaeger](file:///d:/XBrain%20Internship/02%20AIOps/TechX%20Capstone%20Project/w01%20task/Evidences/w01%20Epic-AIE-01%20Vi%E1%BA%BFt%20Checklist%20&%20Ch%E1%BA%A1y%20Smoke%20Test%20tr%C3%AAn%20EKS%20(M%C3%B4i%20tr%C6%B0%E1%BB%9Dng%20th%E1%BB%B1c)%20Jaeger.html) cho thấy độ trễ gọi AI chỉ ở mức ~100ms. Nếu gọi ra Internet tới OpenAI thật, độ trễ tối thiểu phải >1000ms. | **High / Critical.** Không thể test các tính năng sinh văn bản thật, không thể đo lường chi phí (cost) hay giới hạn rate limit. | Cập nhật `values-aio-llm.yaml` để nối API Key thật (Task tiếp theo). |
| **Độ tin cậy (Reliability)** | Code `product-reviews` mở kết nối Database trực tiếp (không dùng Pool) và hàm gọi LLM `OpenAI()` không có timeout. `max_workers` của gRPC chỉ là 10. | Source code tại `database.py` và `product_reviews_server.py`. | **High / Critical.** Khi nối LLM thật, nếu API chậm, 10 Threads sẽ bị treo vĩnh viễn, dẫn đến thắt cổ chai và sập tính năng AI, thậm chí sập DB nếu bị DDoS. | Triển khai Connection Pool cho Database và Timeout/Retry cho OpenAI client (Đã có trong checklist). |
| **Độ trung thực (Faithfulness)** | Ứng dụng hiện tại không có cơ chế nào để tự động kiểm tra xem AI đang trả lời dựa vào review thật hay đang "bịa chuyện" (Hallucination). | [Giao diện Frontend](file:///d:/XBrain%20Internship/02%20AIOps/TechX%20Capstone%20Project/w01%20task/Evidences/w01%20Epic-AIE-01%20Vi%E1%BA%BFt%20Checklist%20&%20Ch%E1%BA%A1y%20Smoke%20Test%20tr%C3%AAn%20EKS%20(M%C3%B4i%20tr%C6%B0%E1%BB%9Dng%20th%E1%BB%B1c).html) không có nhãn cảnh báo AI, không có số liệu kiểm định. | **Medium.** Có nguy cơ lừa dối khách hàng, vi phạm quy tắc đạo đức AI. | Bắt buộc phải viết một đoạn script Eval (`faithfulness_eval.py`) để đo lường. |

---

## 2. Pitch Notes (Tài Liệu Bảo Vệ Trí / Thuyết Trình) - AIE-07

*Đây là các luận điểm cậu dùng để nói chuyện với sếp/BTC trong buổi Ops Review cuối tuần để chứng minh vì sao team không đâm đầu vào code tính năng mới (Shopping Copilot) ngay lập tức.*

**Kính thưa Ban Tổ Chức,**

Trong Tuần 1, thay vì lao vào build một hệ thống Shopping Copilot khổng lồ bằng AI, team AIO01 chúng tôi đã chọn chiến lược **"Đi chậm để đi xa - Đánh giá Baseline trước"**. Và quyết định này hoàn toàn chính xác. Hệ thống hiện tại đang bộc lộ những lỗ hổng chết người về độ tin cậy nếu chúng ta đem ra production:

1. **"Não giả" siêu tốc (Mock LLM):** Bằng chứng từ hệ thống Jaeger cho thấy độ trễ của AI hiện chỉ là 100ms. Điều này chứng tỏ AI đang đọc text cố định. Nếu chúng ta "nhắm mắt" làm Copilot trên não giả này, đến khi cắm não thật (OpenAI) mất 2-5 giây phản hồi, toàn bộ kiến trúc sẽ sụp đổ.
2. **Quả bom nổ chậm về tài nguyên:** Bằng chứng source code cho thấy không có Connection Pool và không có Timeout khi gọi API LLM. Nếu một người dùng spam 11 câu hỏi liên tiếp lúc LLM thật bị lag, toàn bộ 10 luồng xử lý của hệ thống sẽ bị treo, và Shopping Copilot sẽ kéo sập cả hệ thống thương mại điện tử.
3. **Mù lờ về sự trung thực:** Hiện chúng ta chưa có công cụ (Eval) nào để biết AI có đang nói dối người dùng hay không.

**Hành động của team AIO01 (Kế hoạch):**
Trước khi xây dựng bất kỳ tính năng "thần thánh" nào, chúng tôi xin phép thực thi 3 mũi nhọn trong tuần tới:
- Bịt lỗ hổng sập Database (Thêm Connection Pool).
- Bịt lỗ hổng treo dịch vụ (Thêm Timeout + Tăng Worker).
- Thay "Não thật" đi kèm bộ kiểm định (Eval) mức độ trung thực của câu trả lời.

Chỉ khi cái móng nhà này vững, chúng ta mới bắt đầu xây Copilot. Xin cảm ơn!
