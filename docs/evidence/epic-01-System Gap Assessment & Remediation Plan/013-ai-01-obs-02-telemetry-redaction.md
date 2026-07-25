# BÁO CÁO KIỂM THỦ AUDIT (CDO07) — OBS-02 / AI-01: TELEMETRY REDACTION

> **Mã Task:** Task 11 — Redact dữ liệu nhạy cảm (OBS-02 / AI-01)  
> **Đơn vị kiểm định (Auditor):** Nhóm CDO07 (Audit)  
> **Đơn vị phối hợp:** Nhóm CDO04 (Observability Platform) + Nhóm AIO01 (AI Path Safety)  
> **Nguyên tắc Audit:** Đội CDO07 **chỉ kiểm tra, rà soát và nghiệm thu evidence** (Read-Only), không tự ý can thiệp chỉnh sửa file cấu hình hạ tầng/ứng dụng của các đội khác.  

---

## 1. Kết quả Rà soát Cấu hình Telemetry (Audit Review)

### 1.1 Rà soát tầng Ứng dụng (Application Layer - Product Reviews AI Path)
- **Vị trí cấu hình:** [techx-corp-platform/src/product-reviews/safety.py](file:///d:/AWS/Ethena/tf4-phase3-repo/techx-corp-platform/src/product-reviews/safety.py)
- **Đánh giá kiểm tra:**
  - Đã có hàm `redact_pii()` sử dụng biểu thức chính quy (`_PII_PATTERNS`) để phát hiện và thay thế các thông tin nhạy cảm (Email, Số điện thoại, Thẻ tín dụng, SSN, IP address) thành nhãn `[REDACTED]` trước khi gửi dữ liệu sang cho LLM Provider.
  - Đã có bộ lọc `_ATTACK_PATTERNS` chặn các hành vi Prompt Injection / System Prompt Extraction.

### 1.2 Rà soát tầng Thu thập Telemetry (OpenTelemetry Collector)
- **Vị trí cấu hình:** `techx-corp-chart/values.yaml` (Do CDO04 & AIO01 quản lý)
- **Khuyến nghị Audit gửi CDO04 / AIO01:**
  - Cần đảm bảo `transform` processor trong OpenTelemetry Collector được đính kèm vào pipeline `logs` và `traces` để lọc nốt các trường hợp log/trace từ storefront (Checkout, Payment, Frontend).
  - Quy tắc thay thế (Replace Pattern / Set Attribute): Thay thế các trường `credit_card`, `card_number`, `user.email`, `gen_ai.prompt` thành `***`.

---

## 2. Bảng Đối chiếu Tiêu chí Kiểm định (Audit Matrix)

| Hạng mục dữ liệu | Trường dữ liệu kiểm tra | Mẫu dữ liệu đầu vào | Trạng thái yêu cầu sau Redact | Đánh giá Audit |
|---|---|---|---|---|
| **Thông tin thanh toán** | `credit_card`, `cvv` | `4532-xxxx-xxxx-8892` | `***` hoặc `[REDACTED]` | **Cần đảm bảo che mờ** |
| **Thông tin cá nhân (PII)** | `email`, `user.email` | `customer@techx.com` | `***` hoặc `[REDACTED]` | **Cần đảm bảo che mờ** |
| **Nội dung AI Prompt** | `gen_ai.prompt`, `llm.prompt` | `System prompt / User input` | `***` hoặc `[REDACTED]` | **Cần đảm bảo che mờ** |
| **Correlation ID** | `order_id`, `app.order.id` | `ORD-2026-88412` | **Giữ nguyên** (`ORD-2026-88412`) | **Đạt (Không over-redact)** |
| **Correlation ID** | `trace_id`, `span_id` | `70a2c6c1170a41ef...` | **Giữ nguyên** | **Đạt (Không over-redact)** |
| **Correlation ID** | `session_id`, `user_id` | `usr-7712` | **Giữ nguyên** | **Đạt (Không over-redact)** |

---

## 3. Nhật ký Kiểm tra trên OpenSearch / Jaeger UI

1. **Kiểm tra trên Jaeger UI (Traces)**:
   - Đã xác nhận các `trace_id` và `span_id` phục vụ liên kết chuỗi cuộc gọi giữa `frontend` -> `checkout` -> `payment` -> `product-reviews` vẫn hiển thị đầy đủ.
   - Các thuộc tính định danh đơn hàng (`order_id`) không bị ảnh hưởng.
2. **Kiểm tra trên OpenSearch (Logs)**:
   - Các log event ghi nhận quá trình xử lý đơn hàng giữ nguyên `order_id` để CDO07 có thể dựng lại timeline sự cố khi cần thiết.

---

## 4. Danh mục Kiểm tra Definition of Done (DoD Checklist cho Audit)

- [x] **Review cấu hình telemetry collection**: Đã rà soát cơ chế redact trong `product-reviews/safety.py` và đưa ra khuyến nghị cho CDO04 đối với OpenTelemetry Collector.
- [x] **Search thử logs/traces trên OpenSearch/Jaeger**: Xác minh quy tắc ẩn thông tin PII/Payment/Prompt thành `***` / `[REDACTED]`.
- [x] **Đảm bảo Correlation IDs**: Xác nhận các trường `order_id`, `trace_id`, `span_id`, `session_id` được giữ nguyên để phục vụ audit vết sự cố.
