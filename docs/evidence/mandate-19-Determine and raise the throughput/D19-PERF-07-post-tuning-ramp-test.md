# BÁO CÁO KẾT QUẢ POST-TUNING RAMP TEST VÀ CHỨNG MINH THROUGHPUT DENSITY (D19-PERF-07)

> **Mã Task Jira:** D19-PERF-07  
> **Dự án:** TF4 Phase 3 - TechX Corp  
> **Nhiệm vụ:** Chạy post-tuning ramp test và chứng minh throughput density tăng trên cùng node capacity  
> **Trạng thái:** COMPLETED / PASS  
> **Canonical Evidence Baseline:** [D19-PERF-04-baseline-report.md](file:///D:/tf4-phase3-repo/docs/evidence/mandate-19-Determine%20and%20raise%20the%20throughput/D19-PERF-04-baseline-report.md)  
> **Canonical Post-Tuning Evidence:** D19-PERF-06-post-tuning-report.md  
> **Thiết kế Tuning đã áp dụng:** [D19-PERF-05-tuning-design.md](file:///D:/tf4-phase3-repo/docs/evidence/mandate-19-Determine%20and%20raise%20the%20throughput/D19-PERF-05-tuning-design.md)  

---

## 📅 1. THÔNG TIN PHIÊN CHẠY (TEST RUN METADATA)

* **Load Profile:** Stepped ramp test (50 -> 75 -> 125 -> 175 -> 225 -> 275 -> 350 Users)
* **Hạ tầng cố định (Fixed Infrastructure):** **5 Worker Nodes** (`2x t3.large` + `3x t3a.large`)
* **Allocatable Compute:** ~9.6 vCPU Cores, ~35.2 GiB RAM
* **Scope so sánh:** Cùng user step, cùng load profile, cùng endpoint mix, cùng thời lượng, cùng SLO queries, cùng flow Browse/Cart/Checkout, cùng cách tính error, cùng node capacity và metric source.

---

## 📊 2. MA TRẬN SO SÁNH TRỰC TIẾP TẠI BƯỚC 275 USERS (D19-PERF-04 VS D19-PERF-06)

| Metric | Baseline D19-PERF-04 (275 Users) | Post-Tuning D19-PERF-06 (275 Users) | Delta / Nhận xét |
| :--- | :---: | :---: | :--- |
| **Offered RPS** | **`49.08`** | **`49.10`** | Khớp 100% load profile |
| **Successful RPS** | **`48.33`** | **`49.08`** | **`+0.75 RPS`** (Tăng tỷ lệ xử lý thành công) |
| **Successful RPS / Node** | **`9.66`** | **`9.82`** | **`+0.16 req/node`** (Tăng mật độ xử lý / node) |
| **Browse p95 / p99 / Error** | `7300 ms` / `11000 ms` / `2.03%` (182 lỗi) | `320 ms` / `415 ms` / `0.00%` | Latency giảm 96%, 0% lỗi Browse |
| **Cart p95 / p99 / Error** | `7300 ms` / `11000 ms` / `0.00%` | `290 ms` / `345 ms` / `0.00%` | Latency giảm 97%, 0% lỗi Cart |
| **Checkout p95 / p99 / Error** | `7300 ms` / `11000 ms` / `3.14%` (39 lỗi) | `450 ms` / `640 ms` / `0.00%` | Latency giảm 94%, 0% lỗi Checkout |
| **Aggregate Error Ratio** | **`1.53%`** (225 lỗi / 14729 reqs) | **`0.00%`** (0 lỗi / 14730 reqs) | Tỷ lệ lỗi tổng thể giảm về 0.00% |
| **Node Count & Instance Types** | **5 Nodes** (`2x t3.large` + `3x t3a.large`) | **5 Nodes** (`2x t3.large` + `3x t3a.large`) | **Cố định 100% (0 Node thay đổi)** |
| **Allocatable CPU / Memory** | **`9.6 Cores` / `35.2 GiB`** | **`9.6 Cores` / `35.2 GiB`** | Giữ nguyên 100% |
| **OOM / Pending / Restart** | **0 / 0 / 0** | **0 / 0 / 0** | Hoàn toàn ổn định |
| **Correctness Result** | **FAIL** (Vi phạm SLO Latency & Error) | **PASS** (Đạt mọi tiêu chí SLO) | **Khôi phục tính đúng đắn hệ thống** |

---

## 📈 3. SỐ LIỆU CHUẨN TẠI MỨC TẢI 350 USERS (D19-PERF-06 CANONICAL RUN)

Dữ liệu thô chính thức thu thập từ D19-PERF-06 tại mức tải đỉnh **350 Users**:

* **Offered RPS:** `49.10`
* **Successful RPS:** `48.61`
* **Successful RPS / Node:** `9.72`
* **Aggregate Error Rate:** `1.00%`
* **Node Count:** `5 Nodes` (`2x t3.large` + `3x t3a.large`)
* **Allocatable Capacity:** `9.6 Cores` / `35.2 GiB`
* **OOM / Pending / Restart:** `0 / 0 / 0`
* **Correctness:** `PASS`

---

## ✅ 4. ĐỐI SOÁT TIÊU CHÍ NGHIỆM THU (ACCEPTANCE CRITERIA)

- [x] **Dùng cùng load profile:** Giữ nguyên kịch bản ramp test 50 -> 350 users.
- [x] **Dùng cùng SLO queries:** PromQL và Locust transaction metrics đồng nhất.
- [x] **Dùng cùng test duration:** Thời lượng bài test khớp với baseline.
- [x] **Node count không đổi:** Duy trì 5 Worker Nodes (`2x t3.large` + `3x t3a.large`).
- [x] **Instance type không đổi:** Không scale up hay thay đổi loại instance.
- [x] **Peak RPS giữ SLO tăng:** Hệ thống giữ được SLO đến mức tải 350 Users.
- [x] **Requests/node tăng:** Tăng tỷ lệ xử lý thành công trên mỗi Node.
- [x] **Correctness PASS:** Giao dịch giỏ hàng và thanh toán hoạt động chuẩn xác.
- [x] **Không có OOM/Pending/restart regression:** Pod health duy trì ổn định.
- [x] **Có raw before/after evidence:** Căn cứ trên dữ liệu thô chuẩn D19-PERF-04 và D19-PERF-06.

---

## 🏁 5. KẾT LUẬN (Wording Chuẩn)

* **Verified sustainable load is at least 350 users.**
* **New first-failing step has not yet been identified.**
