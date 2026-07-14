# CDO08 Week 1 - Rubric Ưu Tiên Backlog (Revised - Business Centric)

**Owner:** Hải  
**Reviewer:** Nguyên  
**Status:** Approved  

---

## 1. Nguyên Tắc Thiết Kế Rubric

Để tối ưu hóa hoạt động của sản phẩm dưới góc độ kinh doanh thực tế, Rubric này chuẩn hóa mọi đánh giá rủi ro kỹ thuật (cả Security và Reliability) về một công thức duy nhất tập trung vào **Business & SLO** theo định hướng tại [PITCH_GUIDE](../../requirements/onboarding/PITCH_GUIDE.md):

$$\text{Priority Score} = \text{Rủi ro (Khả năng xảy ra} \times \text{Mức nghiêm trọng)} \times \text{Tác động Business}$$

> [!IMPORTANT]
> **Quy đổi Security & Reliability về Business Impact:**
> - **Độc lập với loại lỗi:** Một lỗi bảo mật hay độ tin cậy đều phải trả lời câu hỏi: *"Nếu lỗi này xảy ra, nó ảnh hưởng thế nào đến túi tiền của khách hàng, doanh thu của công ty, hoặc cam kết SLO?"*
> - **Ưu tiên luồng ra tiền:** Các lỗi trực tiếp đe dọa luồng Checkout (SLO $\ge$ 99.0%) luôn có Business Impact lớn nhất.
> - **Các lỗi tuân thủ (Compliance/Rules):** Nếu không trực tiếp gây sập hệ thống hoặc lộ dữ liệu nhạy cảm của khách hàng (ví dụ: cấu hình flagd sync của BTC), chúng sẽ được xếp ở nhóm ưu tiên thấp hơn (P2/P3) thay vì thổi phồng lên P0.

---

## 2. Tiêu Chí Chấm Điểm (Thang 1 - 5)

### A. Khả năng xảy ra (Likelihood - L)
*   **1 (Hiếm/Lý thuyết):** Chỉ xảy ra trong điều kiện giả định rất sâu, khó có khả năng kích hoạt trong môi trường chạy thật.
*   **3 (Có thể xảy ra):** Có khả năng xảy ra trong vận hành thường ngày, khi triển khai (deploy) hoặc khi lưu lượng tải tăng nhẹ.
*   **5 (Rất dễ xảy ra / Đã xảy ra):** Chắc chắn xảy ra khi hệ thống chịu tải cao hoặc rollout pod mới, hoặc đã có lịch sử sự cố ghi nhận.

### B. Mức nghiêm trọng kỹ thuật & Bảo mật (Severity - S)
*   **1 (Thấp):** Hệ thống chỉ bị degrade nhẹ về mặt cấu hình hoặc log, không lỗi chức năng; lỗ hổng bảo mật hầu như không thể khai thác (CVSS < 3.0).
*   **3 (Trung bình):** Hỏng service phụ hoặc lỗi một phần hệ thống nhưng tự hồi phục nhanh; hoặc lỗ hổng bảo mật nội bộ cần quyền truy cập mạng EKS (CVSS 3.0 - 6.9).
*   **5 (Critical / Sập hệ thống):** Sập hoàn toàn service core (checkout, payment, cart), mất dữ liệu không thể khôi phục; hoặc lỗ hổng bảo mật nghiêm trọng cho phép chiếm quyền quản trị tối cao (Admin/Secret exposure) công khai từ Internet (CVSS 7.0 - 10.0).

### C. Tác động Business, SLO & Uy tín (Business Impact - B)
*   **1 (Nội bộ):** Không ảnh hưởng đến khách hàng, không ảnh hưởng SLO, chỉ ảnh hưởng đến công cụ vận hành nội bộ của team; không có rủi ro bảo mật/uy tín.
*   **3 (Vừa phải):** Ảnh hưởng luồng phụ (reviews, recommendations); hoặc vi phạm nhẹ SLO cart/browse; hoặc lỗi an ninh dạng hardening gap (lộ log không nhạy cảm), không đe dọa tài khoản hay tiền của khách.
*   **5 (Tối cao - Doanh thu & SLO Checkout & Rò rỉ dữ liệu):** Trực tiếp làm hỏng luồng đặt hàng/thanh toán, làm vỡ cam kết [SLO](../../requirements/onboarding/SLO.md) Checkout $\ge$ 99.0%; hoặc làm rò rỉ dữ liệu nhạy cảm của khách hàng (token, thẻ tín dụng); hoặc vi phạm nghiêm trọng luật chơi của BTC có nguy cơ bị truất quyền thi đấu (DQ).

---

## 3. Quy Đổi Cấp Độ Ưu Tiên (Priority Bands)

Công thức tính điểm: **$\text{Score} = (L \times S) \times B$** (Dải điểm từ 1 đến 125).

| Priority | Khoảng điểm | Quy tắc quyết định kinh doanh |
| :--- | :---: | :--- |
| **P0 (Critical / Blocker)** | **$\ge$ 60** | **Bắt buộc xử lý ngay.** Trực tiếp gây sập checkout, mất dữ liệu đơn hàng (order) đang giao dịch, hoặc trừ tiền khách nhưng không tạo được đơn. |
| **P1 (High)** | **30 - 59** | **Kế hoạch Tuần 2-3.** Các lỗ hổng bảo mật nghiêm trọng (như lộ admin UI), hoặc các rủi ro có thể gây nghẽn hiệu năng luồng thanh toán khi tải cao. |
| **P2 (Medium)** | **12 - 29** | **Cải tiến dần.** Các cấu hình bảo mật nội bộ (securityContext, shared SA), thiếu dữ liệu giám sát sau restart, hoặc các cấu hình kiểm thử (flagd sync). |
| **P3 (Low)** | **< 12** | **Xem xét sau.** Dọn dẹp tài liệu, tối ưu CORS trace telemetry. |

---

## 4. Vai Trò Của Bằng Chứng (Evidence Confidence - E)

Độ tin cậy của bằng chứng (Evidence Confidence) được đánh giá theo thang từ **1 đến 5**:
*   **1 (Giả thiết):** Phỏng đoán lý thuyết, chưa tìm thấy bất kỳ cấu hình hay mã nguồn cụ thể nào liên quan.
*   **2 (Cơ sở yếu):** Chỉ mới dự đoán dựa trên hành vi bên ngoài của app, chưa kiểm chứng được file code hoặc config.
*   **3 (Bằng chứng tĩnh - Static Config):** Chỉ ra được chính xác dòng cấu hình bị thiếu/sai trong Helm chart (`values.yaml`, template) hoặc dòng mã nguồn trong source code Git.
*   **4 (Bằng chứng tĩnh + đối chiếu EKS):** Có cấu hình tĩnh trong repo Git và đã đối chiếu chạy thực tế trên cụm EKS thông qua các lệnh `kubectl` cơ bản (ví dụ: chạy lệnh `kubectl get deploy` thấy `replicas: 1` hoặc `kubectl get sa` không có annotation).
*   **5 (Bằng chứng động - Runtime Telemetry):** Có dữ liệu trực quan thực tế tại thời điểm chạy: Logs báo lỗi cụ thể, trace trên Jaeger chứng minh bottleneck/latency, hoặc metrics trên Prometheus/Grafana chỉ ra SLO bị vỡ.

> [!TIP]
> **Cơ chế Gatekeeper:**
> - Nếu một phát hiện có **Priority Score thuộc nhóm P0/P1** nhưng **Evidence thấp (1 - 2)**, trạng thái review bắt buộc phải là **`Needs Info`**. Team không được phép deploy sửa đổi lớn khi chưa thu thập đủ bằng chứng runtime chứng minh lỗi.
> - Khi **Evidence $\ge$ 3**, trạng thái sẽ chuyển thành **`Approved`** để triển khai.

---

## 5. Ví Dụ Minh Họa Áp Dụng

### Ví dụ 1: Kafka publish thất bại sau khi thanh toán thành công (CDO08-REL-07)
*   **Likelihood (L):** 3 (Có thể xảy ra khi Kafka chịu tải hoặc rớt kết nối).
*   **Severity (S):** 4 (Lỗi không đồng bộ dữ liệu giữa Payment và Checkout).
*   **Business Impact (B):** 5 (Trừ tiền khách nhưng đơn hàng thất bại $\rightarrow$ Khách hàng khiếu nại, ảnh hưởng nghiêm trọng đến doanh thu/uy tín).
*   **Score:** $(3 \times 4) \times 5 = 60 \rightarrow$ **P0**. (Evidence = 4 $\rightarrow$ Approved).

### Ví dụ 2: Thiếu probes trên checkout path (CDO08-REL-02)
*   **Likelihood (L):** 4 (Deploy/restart pod mới chắc chắn đẩy traffic vào pod chưa ready).
*   **Severity (S):** 4 (Checkout request bị fail liên tục trong quá trình rollout).
*   **Business Impact (B):** 5 (Ảnh hưởng trực tiếp đến doanh thu và SLO checkout).
*   **Score:** $(4 \times 4) \times 5 = 80 \rightarrow$ **P0**. (Evidence = 4 $\rightarrow$ Approved).

### Ví dụ 3: `flagd` central sync bị vô hiệu hóa (CDO08-REL-08)
*   **Likelihood (L):** 3 (BTC kiểm tra cấu hình hoặc thay đổi flag cấu hình).
*   **Severity (S):** 2 (Lỗi control plane, app vẫn hoạt động bình thường bằng file config local fallback).
*   **Business Impact (B):** 2 (Không ảnh hưởng đến khách hàng hay luồng checkout thực tế, chỉ ảnh hưởng đến việc đồng bộ kịch bản kiểm thử của BTC).
*   **Score:** $(3 \times 2) \times 2 = 12 \rightarrow$ **P2**. (Evidence = 5 $\rightarrow$ Approved).
