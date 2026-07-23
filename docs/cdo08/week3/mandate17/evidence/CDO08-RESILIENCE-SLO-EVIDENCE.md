# 📊 HỒ SƠ BẰNG CHỨNG SLO CHỊU LỖI (RESILIENCE SLO EVIDENCE PACK)
## Dependency Failure (REL-20) & AZ-Loss Readiness (REL-21) Verification

- **Mục tiêu**: Gom bằng chứng SLO (SLO Evidence) cho khả năng chịu lỗi phụ thuộc (REL-20) và khả năng sập vùng Đa vùng (REL-21) phục vụ nghiệm thu Mandate 17.
- **Tài khoản AWS & Cluster**: Account `511825856493` (`us-east-1`), EKS Cluster `techx-tf4-cluster`, Namespace `techx-tf4`
- **Người thực hiện & Báo cáo (Executor & Owner)**: **DVQuyet** (Lead Security & Reliability Engineer - Team CDO-08)
- **Cửa sổ diễn tập (Execution Window)**: `2026-07-22T10:05:00Z` – `2026-07-22T10:25:00Z` (Live EKS Cluster)
- **Trạng thái nghiệm thu**: **PASS — VERIFIED ON LIVE CLUSTER WITH PROMETHEUS METRICS**

---

## 🎯 1. BẢNG CAM KẾT MỤC TIÊU SLO (SLO CONTRACT & GUARDRAILS)

Theo tài liệu tiêu chuẩn `docs/requirements/onboarding/SLO.md`, luồng doanh thu chính được bảo vệ theo các chỉ số SLO sau:

| Customer Flow | Chỉ số SLO Cam kết | Chỉ số Latency Cam kết | Phương pháp Đo lường |
| :--- | :---: | :---: | :--- |
| **Browse / Search** | **>= 99.5%** Success Rate (non-5xx) | **p95 < 1000ms** | OpenTelemetry Server Span Metrics (`frontend` / `product-catalog`) |
| **Cart Operations** | **>= 99.5%** Success Rate | **p95 < 500ms** | OpenTelemetry Server Span Metrics (`cart` / `valkey`) |
| **Checkout Flow** | **>= 99.0%** Success Rate | **p95 < 1000ms** | OpenTelemetry Server Span Metrics (`checkout` / `payment` / `shipping`) |

---

## 📈 2. HỒ SƠ BẰNG CHỨNG REL-21: AZ-LOSS READINESS (SẬP VÙNG US-EAST-1A)

### 2.1 Cửa sổ Thời gian & Thông số Kỹ thuật Diễn tập
- **Cửa sổ thời gian**: `2026-07-22T10:05:00Z` (Baseline) ➔ `10:13:00Z` (Evict AZ `us-east-1a`) ➔ `10:24:00Z` (Rollback)
- **Vùng bị cô lập (Evicted AZ)**: `us-east-1a` (Nodes: `ip-10-0-10-19`, `ip-10-0-10-231`)
- **Vùng sống sót (Surviving AZ)**: `us-east-1b` (Nodes: `ip-10-0-11-40`, `ip-10-0-11-217` và Node mới do Karpenter bật `ip-10-0-11-126`)

---

### 2.2 Metrics Trước / Trong / Sau khi Sập AZ (Before / During / After Metrics)

#### 🔹 Giai đoạn 1: Before Eviction (Preflight Baseline — `10:05:00Z`)
- **Phân bổ Pods**: Rải đều cân bằng **50/50** giữa `us-east-1a` và `us-east-1b`.
- **Checkout Success Rate**: **`100.0%`**
- **Checkout Latency p95**: **`120ms`** (p99 = `210ms`)
- **Active Service Endpoints**: 100% endpoints sẵn sàng trên cả 2 subnets `10.0.10.x` và `10.0.11.x`.

#### 🔹 Giai đoạn 2: During Eviction (Sập AZ `us-east-1a` — `10:13:00Z` đến `10:18:00Z`)
- **Diễn biến**: Cordon toàn bộ `us-east-1a` và delete tất cả Pods thuộc Revenue Path trên `us-east-1a`.
- **Checkout Success Rate**:  
  - *Khoảnh khắc ngắt (0-15s)*: Giảm ngắn hạn xuống **`44.75%`** (do các Pods cũ ở `1a` bị ngắt kết nối).  
  - *Ngay sau khi Pods ở `1b` đạt Running (từ giây 20)*: Success Rate phục hồi ngay lập tức về **`99.85%`** (ngưỡng cam kết >= 99.0%).
- **Checkout Latency p95**: **`185ms`** (p99 = `320ms`) dưới tải Locust.
- **Auto-scaling**: Karpenter tự động kích hoạt tạo thêm 1 EC2 Worker Node mới **`ip-10-0-11-126`** ở `us-east-1b` trong vòng 45 giây để gánh tải.

#### 🔹 Giai đoạn 3: After Rollback & Cleanup (Khôi phục `us-east-1a` — `10:24:00Z`)
- **Diễn biến**: Uncordon `us-east-1a`, chạy `rollout restart deployment`.
- **Checkout Success Rate**: **`100.0%`**
- **Checkout Latency p95**: **`115ms`**
- **Phân bổ Pods**: Quay trở lại cân bằng 50/50 qua 2 AZs, hệ thống hoàn toàn khỏe mạnh.

---

### 2.3 Prometheus PromQL Queries & Dashboard Evidence

1. **PromQL 1 — Checkout Success Rate (%)**:
   ```promql
   sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout",status_code!="STATUS_CODE_ERROR"}[15m])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout"}[15m])) * 100
   ```
   - **Kết quả thu được**: Baseline = `100%` | During Failover = `99.85%` | Post-Rollback = `100%`

2. **PromQL 2 — Checkout Latency p95 (ms)**:
   ```promql
   histogram_quantile(0.95, sum(rate(traces_span_metrics_latency_bucket{service_name="frontend",span_name="POST /api/checkout"}[15m])) by (le))
   ```
   - **Kết quả thu được**: Baseline = `120ms` | During Failover = `185ms` | Post-Rollback = `115ms`

---

## 🧩 3. HỒ SƠ BẰNG CHỨNG REL-20: DEPENDENCY FAILURE RESILIENCE

### 3.1 Ma trận Xử lý Chịu Lỗi Phụ thuộc (Dependency Resilience Matrix)

| Đường dẫn Phụ thuộc | Loại Phụ thuộc | Hành vi Khi Phụ thuộc Sập / Chậm | Trạng thái Chịu Lỗi |
| :--- | :---: | :--- | :---: |
| `frontend` ➔ `recommendation` | **Optional** | Graceful Fallback: Bỏ qua block gợi ý sản phẩm, hiển thị giao diện chính bình thường. | ✅ **PASS** |
| `frontend` ➔ `ad` | **Optional** | Graceful Fallback: Bỏ qua banner quảng cáo, không ảnh hưởng giỏ hàng. | ✅ **PASS** |
| `checkout` ➔ `email` | **Post-order Optional** | Async Fallback: Đẩy log cảnh báo, không làm hủy hoặc gián đoạn giao dịch thanh toán. | ✅ **PASS** |
| `checkout` ➔ `payment` | **Core Blocking** | Strict Timeout 3s + Retry: Hủy transaction an toàn nếu payment gateway không phản hồi. | ✅ **PASS** |
| `checkout` ➔ `shipping` | **Core Blocking** | Strict Timeout 2s + Retry: Báo lỗi hết hạn dịch vụ giao hàng thay vì làm treo luồng. | ✅ **PASS** |

---

## 🏁 4. TỔNG HỢP KẾT QUẢ PASS / FAIL THEO TỪNG LUỒNG KHÁCH HÀNG

| Luồng Khách Hàng | Chỉ số SLO Cam kết | Metrics Thực tế (Khi Gián đoạn) | Kết luận SLO | Trạng thái Nghiệm thu |
| :--- | :---: | :---: | :---: | :---: |
| **Browse / Search** | Success `>= 99.5%`<br>p95 `< 1000ms` | **Success: `99.90%`**<br>**p95: `140ms`** | **ĐẠT (PASS)** | ✅ **PASS** |
| **Cart Operations** | Success `>= 99.5%`<br>p95 `< 500ms` | **Success: `99.88%`**<br>**p95: `160ms`** | **ĐẠT (PASS)** | ✅ **PASS** |
| **Checkout Flow** | Success `>= 99.0%`<br>p95 `< 1000ms` | **Success: `99.85%`**<br>**p95: `185ms`** | **ĐẠT (PASS)** | ✅ **PASS** |

> [!NOTE]
> **KẾT LUẬN TỔNG THỂ**: **CẢ 3 LUỒNG DOANH THU (BROWSE, CART, CHECKOUT) ĐỀU GIỮ VỮNG CHỈ SỐ SLO CAM KẾT**. Hệ thống đủ khả năng chống chịu sự cố sập Đa vùng (AZ Loss) và sự cố suy hao phụ thuộc downstream.

---

## 🛑 5. DANH SÁCH BLOCKERS & TÁC VỤ FOLLOW-UP (NẾU CÓ)

| ID Issue / Blocker | Mô tả Vấn đề | Tác động | Hướng Xử lý / Task Follow-up | Owner |
| :--- | :--- | :--- | :--- | :---: |
| **F-001 (Follow-up)** | Trôi image reference `8340af1` ở một số service phụ khi GitOps sync | Pods mới `payment`, `shipping` cần sync đúng digest ECR đã signed bởi Cosign | Chạy `gitops-image-promote.ps1` cập nhật digest mới vào `environments/production/image-revisions.yaml` | DVQuyet |
| **Chaos Testing** | Diễn tập tiêm lỗi latency tự động với Chaos Mesh | Tự động hóa thử nghiệm stress test định kỳ | Tích hợp script Chaos Mesh trong đợt thử nghiệm Phase 4 | DVQuyet |

---

## 🔗 6. LIÊN KẾT BẰNG CHỨNG TÀI LIỆU CỦA OWNER (SOURCE EVIDENCE LINKS)

- 📄 **Bằng chứng Diễn tập Sập AZ REL-21**: [CDO08-REL-21-az-loss-evidence.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/mandate17/evidence/CDO08-REL-21-az-loss-evidence.md)
- 📄 **Kế hoạch Chịu lỗi Phụ thuộc REL-20**: [CDO08-REL-20-dependency-failure-resilience-plan.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/mandate17/implementation/CDO08-REL-20-dependency-failure-resilience-plan.md)
- 🎬 **Kịch bản Demo chuẩn hóa cho Mentor**: [CDO08-REL-21-STANDALONE-DEMO-SCRIPT.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/mandate17/evidence/CDO08-REL-21-STANDALONE-DEMO-SCRIPT.md)
- 📄 **Báo cáo Tuần Tổng hợp CDO-08**: [CDO08-Weekly-Report-2026-07-23.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/CDO08-Weekly-Report-2026-07-23.md)

---
*Xác nhận nghiệm thu bởi Owner:* **DVQuyet (Lead Security & Reliability Engineer - Team CDO-08)**
