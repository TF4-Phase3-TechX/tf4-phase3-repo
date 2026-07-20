# [D16-COST-01] Verify Tail-Latency Gain Without Additional Compute

## 1. Objective
Chứng minh p99 latency giảm nhờ tối ưu kỹ thuật, không phải do mua thêm compute.

## 2. Before/After Matrix

| Metric | Before (Baseline) | After (Optimized) | Delta | Verdict |
| :--- | :---: | :---: | :---: | :---: |
| **Worker node-hours** | *[Pending Run]* | *[Pending Run]* | - | - |
| **Peak node count** | 2 | 2 | 0 | **PASS** |
| **HPA minimum replicas** | 2 (checkout, currency, frontend) | 2 (checkout, currency, frontend) | 0 | **PASS** |
| **HPA peak replicas** | 3 (checkout, currency, frontend) | 3 (checkout, currency, frontend) | 0 | **PASS** |
| **CPU requests** | Cố định | Cố định | 0 | **PASS** |
| **Memory requests** | Cố định | Cố định | 0 | **PASS** |
| **Actual CPU consumption** | *[Pending Run]* | *[Pending Run]* | - | - |
| **CPU seconds/successful request** | *[Pending Run]* | *[Pending Run]* | - | - |
| **Actual memory consumption** | *[Pending Run]* | *[Pending Run]* | - | - |
| **Browse p99** | 520 ms | *[Pending Run]* | - | - |
| **Cart p99** | 500 ms | *[Pending Run]* | - | - |
| **Checkout p99** | 820 ms | *[Pending Run]* | - | - |

## 3. Acceptance Criteria Checklist

- [ ] **Worker node-hours after <= before.**
- [x] **Peak node count after <= before.**
- [x] **HPA minimum không tăng.**
- [x] **Instance class không tăng.**
- [x] **CPU/memory requests không tăng để lấy latency.**
- [ ] **CPU consumption không tăng đáng kể.**
- [ ] **CPU seconds/request không regress nếu có dữ liệu.**
- [ ] **p99 giảm.**
- [ ] **SLO và correctness giữ nguyên.**
- [ ] **Modeled resource comparison có raw evidence.**

---

*Ghi chú: Báo cáo sẽ được điền đầy đủ số liệu After ngay sau khi bản code tối ưu hóa được deploy thành công lên cụm EKS và chạy bài test tải 200 users.*
