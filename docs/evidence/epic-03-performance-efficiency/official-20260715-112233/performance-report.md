# Báo Cáo Nghiệm Thu Bảo Trì EKS Không Downtime (Directive #3)

* **Mã lần chạy (RUN_ID):** `official-20260715-112233`
* **Thời gian bắt đầu (T0):** `11:05:00 UTC` (18:05:00 GMT+7)
* **Thời gian kết thúc (T1):** `11:26:00 UTC` (18:26:00 GMT+7)
* **Tổng thời gian kiểm thử:** 21 phút (Đạt điều kiện tối thiểu 15 phút ở trạng thái ổn định).
* **Tải giả lập:** 200 người dùng đồng thời (Locust Swarm).

---

## 📊 Kết Quả Đánh Giá Chỉ Số SLO

| Chỉ số / SLO | Mục tiêu (Target) | Kết quả thực tế | Trạng thái (PASS/FAIL) |
| :--- | :--- | :--- | :--- |
| **Storefront Latency (p95)** | < 1000 ms (1 giây) | **~303 ms** (Max đỉnh điểm) | **PASS** |
| **Browse/Search Success Rate**| ≥ 99.5% | **100%** (Hoàn hảo) | **PASS** |
| **Cart Success Rate** | ≥ 99.5% | **100%** (Hoàn hảo) | **PASS** |
| **Checkout Success Rate** | ≥ 99.0% | **100%** (Hoàn hảo) | **PASS** |
| **Độ trễ trung bình (p50)** | N/A | **~14.9 ms** | **PASS** |

---

## 🔍 Nhật Ký Bảo Trì & Khả Năng Tự Phục Hồi (Resilience Timeline)

1. **Trước bảo trì (Pre-maintenance):**
   * Hệ thống chạy ổn định ở mức tải nền.
   * Xem ảnh chụp baseline tại [Baseline](./dashboard/photo_2026-07-15_18-25-45.jpg).
2. **Kích hoạt tải & Duy trì trạng thái ổn định:**
   * Tải Locust tăng dần từ 0 lên 200 users và duy trì ổn định. RPS đạt mức ~50 requests/sec.
3. **Thực hiện hành động bảo trì (During maintenance):**
   * Node `ip-10-0-10-231.ec2.internal` được drain bằng lệnh:
     `kubectl drain ip-10-0-10-231.ec2.internal --ignore-daemonsets --delete-emptydir-data --force`
   * Toàn bộ các Pod ứng dụng và nghiệp vụ chính (Frontend, Checkout, Cart) bị trục xuất khỏi node.
   * Xem ảnh checkpoint trong lúc bảo trì tại [During Maintenance](./dashboard/photo_2026-07-15_18-26-04.jpg).
4. **Karpenter Tự Cứu & Hệ Thống Tự Phục Hồi:**
   * Karpenter phát hiện Pods bị Pending và tự động gọi API AWS EKS scale-up **2 nodes mới** là `ip-10-0-10-113.ec2.internal` và `ip-10-0-11-89.ec2.internal`.
   * Các Pod di cư sang node mới thành công và chuyển về trạng thái `Running`.
   * **Không xảy ra lỗi (Error Rate = 0%) và độ trễ p95 luôn giữ dưới 303ms trong suốt quá trình dịch chuyển Pod.**
5. **Hậu bảo trì & Ổn định hoàn toàn:**
   * Node ban đầu được uncordon đưa về trạng thái bình thường.
   * Load test được tắt sau 21 phút.
   * Xem ảnh chụp hệ thống ổn định hoàn toàn tại [Post-Maintenance & Stabilized](./dashboard/photo_2026-07-15_18-26-08.jpg).

---

## 📌 Kết Luận
Bài kiểm chứng **đạt kết quả PASS toàn diện**. Hệ thống EKS kết hợp Karpenter chứng minh khả năng tự phục hồi, dịch chuyển pod và giãn nở tài nguyên động thông minh mà không gây ra bất kỳ gián đoạn dịch vụ nào đối với người dùng cuối dưới điều kiện tải cao (200 concurrent users).
