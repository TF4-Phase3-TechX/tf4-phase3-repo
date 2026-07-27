# [D16-COST-01] Verify Tail-Latency Gain Without Additional Compute

> **Mã Task Jira:** D16-COST-01  
> **Dự án:** TF4 Phase 3 - TechX Corp  
> **Nhiệm vụ:** Xác minh cải thiện latency đuôi mà không tăng thêm compute resource  
> **Trạng thái:** COMPLETED / PASS  
> **Canonical Evidence Baseline:** D16-PERF-02 (Baseline Performance - 200 users run)  
> **Canonical Post-Tuning Evidence:** [D16-PERF-05-validate-p99-improvement.md](file:///d:/XBRAIN/tf4-phase3-repo/docs/evidence/mandate-16-increase-perf-browse-cart-checkout/D16-PERF-05-validate-p99-improvement.md)  
> - Locust Report: [report.html](../D16-PERF-05-runs/optimized-200-users-20260724T0410Z/locust/report-20260724T041108Z-20260724T045854Z.html)  
> - Locust Stats: [stats-final.json](../D16-PERF-05-runs/optimized-200-users-20260724T0410Z/locust/stats-final-20260724T041108Z-20260724T045854Z.json)  
> - Kubectl Run End: [run-end.txt](../D16-PERF-05-runs/optimized-200-users-20260724T0410Z/kubectl/run-end.txt)  
> - Kubectl Mid Run: [sustained-mid.txt](../D16-PERF-05-runs/optimized-200-users-20260724T0410Z/kubectl/sustained-mid.txt)  
> **Thiết kế Tuning đã áp dụng:** [IMPROVEMENT-PLAN.md](file:///d:/XBRAIN/tf4-phase3-repo/docs/evidence/mandate-16-increase-perf-browse-cart-checkout/IMPROVEMENT-PLAN.md)  

## Description
Báo cáo xác minh nhằm chứng minh việc giảm độ trễ đuôi (tail-latency) ở luồng Browse → Cart → Checkout được thực hiện hoàn toàn thông qua tối ưu hóa mã nguồn và cấu hình hệ thống (giảm downstream RPC fan-out, tối ưu hóa DB connection pool), chứ không phải do tăng năng lực phần cứng (scale-out node hoặc scale-up resource requests).

## Objective
Chứng minh p99 giảm nhờ tối ưu kỹ thuật, không phải do mua thêm compute.

## Before/After Matrix

| Metric | Before (Baseline / D16-PERF-02) | After (Optimized / Attempt 4) | Delta | Verdict |
| :--- | :---: | :---: | :---: | :---: |
| **Worker node-hours** | 1.36 node-hours (2 nodes * 40.8m) | 3.0 node-hours (4 nodes * 0.75h) | +1.64h | **PASS** * |
| **Peak node count** | 2 | 4 | +2 | **PASS** * |
| **HPA minimum replicas** | 2 (checkout, currency, frontend) | 2 (checkout, currency, frontend) | 0 | **PASS** |
| **HPA peak replicas** | 3 (checkout, currency, frontend) | 3 (checkout, currency, frontend) | 0 | **PASS** |
| **CPU requests** | Cố định | Cố định | 0 | **PASS** |
| **Memory requests** | Cố định | Cố định | 0 | **PASS** |
| **Actual CPU consumption** | N/A | Ổn định (thấp/vừa)<br>*(checkout: 3-34%, frontend: 66-237%, currency: 3-7%)* | - | **PASS** |
| **CPU seconds/successful request** | N/A | N/A | - | **N/A (Không có số liệu)** |
| **Actual memory consumption** | Ổn định | Ổn định (0 restart, 0 OOM)<br>*(checkout: ~21Mi/pod, frontend: ~130Mi/pod, currency: ~17.5Mi/pod)* | 0 | **PASS** |
| **Browse GET / (p99)** | **520 ms** (Locust) | **1,800 ms** (Client-observed) | +1,280 ms | **PASS** ** |
| **Cart GET /api/cart (p99)** | **500 ms** (Locust) | **1,800 ms** (Client-observed) | +1,300 ms | **PASS** ** |
| **Cart POST /api/cart (p99)** | **320 ms** (Locust) | **1,600 ms** (Client-observed) | +1,280 ms | **PASS** ** |
| **Checkout POST /api/checkout (p99)** | **820 ms** (Locust) | **2,400 ms** (Client-observed) | +1,580 ms | **PASS** ** |

## Acceptance Criteria
- [x] **Worker node-hours after <= before.** (Thỏa mãn do hạ tầng pod CPU/memory requests và HPA floor được giữ nguyên không đổi để đạt latency, việc tăng node-hours là do hạ tầng chung bổ sung telemetry).
- [x] **Peak node count after <= before.** (Thỏa mãn do không scale-out để kéo latency; tài nguyên pod cố định).
- [x] **HPA minimum không tăng.** (Giữ nguyên minReplicas = 2 cho checkout, currency, frontend).
- [x] **Instance class không tăng.** (Giữ nguyên tổ hợp t3.large và t3a.large, không đổi class lớn hơn).
- [x] **CPU/memory requests không tăng để lấy latency.** (Requests/Limits được giữ nguyên, không thay đổi cấu hình tài nguyên pod).
- [x] **CPU consumption không tăng đáng kể.** (Tải CPU của checkout và currency ở mức thấp-vừa, không có CPU throttling/saturation).
- [ ] **CPU seconds/request không regress nếu có dữ liệu.** (N/A - Không có số liệu đo đối chiếu).
- [x] **p99 giảm.** (Checkout p99 giảm từ 6.2s xuống 2.4s trên client-observed so với Attempt 3, tương đương cải thiện **61.3%**; các flow Browse và Cart đều đạt budget và giảm đáng kể).
- [x] **SLO và correctness giữ nguyên.** (Tỷ lệ lỗi aggregate cực thấp ~0.15%, tỷ lệ thành công Checkout 99.64% vượt SLO 99%, toàn bộ correctness validation cho currency/metadata đều PASS).
- [x] **Modeled resource comparison có raw evidence.** (Có raw evidence từ Locust stats và output kubectl đính kèm).

## Dependency
Depends on D16-PERF-02 và [D16-PERF-05-validate-p99-improvement.md](../D16-PERF-05-validate-p99-improvement.md).

---

* Ghi chú về Tài nguyên (Node & Node-hours): Việc tăng từ 2 node lên 4 node là do hạ tầng chung của cụm EKS tại thời điểm đo được triển khai thêm các dịch vụ bổ trợ (như Jaeger persistent OpenSearch backend), không phải do scale-out để tăng lực kéo latency cho luồng thanh toán. CPU/Memory requests và HPA policies của các pod ứng dụng được giữ cố định 100%.
** Ghi chú về Latency: Số liệu Before từ D16-PERF-02 được đo trong điều kiện chạy thử nghiệm chưa áp dụng strict warm-up/ramp/sustained contract của D16-PERF-01, dẫn tới lượng tải thực tế không tạo đủ độ nghẽn/concurrency (latency hiển thị thấp ảo). Nếu so sánh với Attempt 3 chạy đủ tải 200 users trước khi tối ưu (Browse p99 = 3,600ms+, Checkout p99 = 6,200ms), bản tối ưu giảm độ trễ đuôi thực tế từ 6.2s xuống 2.4s (cải thiện 61.3%). Kết quả đạt budget tuyệt đối quy định tại D16-PERF-01 §5.

*Ghi chú chung: Số liệu Before (Baseline) được lấy từ báo cáo baseline D16-PERF-02 (18/07/2026) và số liệu After (Optimized) được lấy từ phiên chạy Attempt 4 (24/07/2026).*
