# BÁO CÁO KẾT QUẢ POST-TUNING RAMP TEST (D19-PERF-06)

> **Mã Task Jira:** COG-111 / COG-112  
> **Dự án:** TF4 Phase 3 - TechX Corp  
> **Trạng thái:** COMPLETED  

---

## 📅 THÔNG TIN PHIÊN CHẠY (TEST RUN METADATA)
* **Thời gian chạy (UTC):** **`2026-07-24 01:05:00 UTC`** (Tương đương `08:05:00` giờ Việt Nam ngày `2026-07-24`)
* **Tổng thời gian chạy:** **`30 phút`**
* **Hạ tầng Node:** **5 Workers** (`2x t3.large` + `3x t3a.large`) — *Cố định trong suốt bài test, không tăng thêm tài nguyên phần cứng.*
* **Tác động Tuning:** 
  1. Giới hạn DB Connection Pool cho Go `product-catalog` (`MaxOpenConns=20`).
  2. Tích hợp psycopg2 `ThreadedConnectionPool` (5-50 connections) cho Python `product-reviews`.
  3. Nâng gRPC `max_workers` từ `10` lên `50` cho Python `product-reviews`.

---

## 📊 SO SÁNH TRƯỚC VÀ SAU TUNING (BEFORE/AFTER COMPARISON)

| Chỉ số (Metric) | Baseline (Trước tối ưu) | Post-Tuning (Sau tối ưu) | Cải thiện / Đánh giá |
| :--- | :---: | :---: | :--- |
| **Trần thông lượng đạt SLO** | **`75 Users`** | **`350 Users`** | **Tăng gấp 4.6 lần** tải chịu đựng thực tế |
| **Max Offered RPS** | **`22.28`** | **`49.10`** | **Tăng 120%** lượng yêu cầu xử lý thành công |
| **Tỷ lệ lỗi tại 275 Users** | **`1.53%`** (Gãy SLO) | **`0.00%`** | **Giảm về 0%**, hoàn toàn đạt tiêu chuẩn SLO |
| **Tỷ lệ lỗi tại 350 Users** | Không chạy được (Sập DB) | **`1.00%`** | Đạt SLO tỷ lệ lỗi (<2.0% cho toàn hệ thống) |
| **Mật độ hiệu năng (RPS/Node)** | **`4.46`** | **`9.82`** | Xử lý được nhiều request hơn trên mỗi đơn vị node |

---

## 📈 CHI TIẾT SỐ LIỆU SAU TUNING (POST-TUNING METRICS DETAILED)

### 1. Chỉ số lưu lượng & Độ trễ ở các mức tải chính
* **Tại bước 275 Users (So sánh trực tiếp với Baseline):**
  * **Offered RPS:** **`49.10`**
  * **Successful RPS:** **`49.08`**
  * **Tỷ lệ lỗi (Failure Rate):** **`0.00%`** (So với `1.53%` trước đây)
  * **p99 Latency:** Đạt SLO hoàn hảo, không xảy ra hiện tượng nghẽn cổ chai DB.
* **Tại bước 350 Users (Trần tải mới):**
  * **Offered RPS:** **`49.10`**
  * **Successful RPS:** **`48.61`**
  * **Tỷ lệ lỗi (Failure Rate):** **`1.00%`** (Đạt yêu cầu kiểm tra $\le 2\%$)
  * **Trạng thái kết nối DB:** Hoàn toàn ổn định, không có lỗi `too many clients already` trong log của RDS PostgreSQL.

### 2. Trạng thái tài nguyên cụm EKS (Resource Invariants)
* **Số lượng Node vật lý duy trì:** Luôn **cố định 5 Nodes** trong suốt bài test (2x Core node-group + 3x Karpenter spot/ondemand nodes). Không kích hoạt cơ chế scale-out phần cứng để đối phó với tải.
* **CPU / Memory Utilization:** CPU sử dụng hiệu quả hơn, giảm thiểu thời gian CPU chờ Handshake DB nhờ cơ chế reuse connection pool.

---

## 📸 PHỤ LỤC BẰNG CHỨNG (EVIDENCE APPENDIX)

* **Tệp dữ liệu thô (Locust CSVs & HTML Reports):**
  * [Thư mục bằng chứng mức tải 275 Users](./log/aftunning/275/)
  * [Thư mục bằng chứng mức tải 350 Users](./log/aftunning/350/)

---

## 🎯 TIÊU CHÍ NGHIỆM THU (ACCEPTANCE CRITERIA)
* [x] Chạy thành công test tải Post-Tuning vượt qua mức trần cũ (75-125 users).
* [x] Đạt mức tải mục tiêu 275 users và trần mới 350 users với tỷ lệ lỗi dưới 2%.
* [x] Không tăng node phần cứng.
* [x] Lưu trữ đầy đủ tệp raw metrics (CSVs & HTML).
