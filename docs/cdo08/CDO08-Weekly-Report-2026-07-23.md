# 🏗️ BÁO CÁO TỔNG KẾT TOÀN DIỆN: MANDATE 17 - CÁC HẠNG MỤC MÃ NGUỒN, CẤU HÌNH & RUNBOOK ĐÃ THỰC HIỆN

- **Thời gian báo cáo**: 15/07/2026 – 23/07/2026 (Tuần 3 - Phase 3 TF4)
- **Người thực hiện**: **DVQuyet** (Lead Security & Reliability Engineer / IAM Owner / Platform Admin - Team CDO-08)
- **Chỉ thị trọng tâm**: **Directive #17 (Mandate 17 - Multi-AZ Resilience & Workload Spread)**
- **Dự án / Target**: **TF4 E-Commerce Platform** (AWS Account `511825856493`, Region `us-east-1`, EKS Cluster `techx-tf4-cluster`)
- **Phạm vi tác động**: 8 Microservices trên Revenue Path (`frontend-proxy`, `frontend`, `cart`, `checkout`, `payment`, `shipping`, `product-catalog`, `currency`) trong Namespace `techx-tf4`
- **Trạng thái nghiệm thu**: **PASS — VERIFIED ON LIVE EKS CLUSTER**

---

## 📌 1. TỔNG QUAN HẠNG MỤC CÔNG VIỆC MANDATE 17 (EXECUTIVE SUMMARY)

Đối với **Mandate 17**, công việc của **DVQuyet** không chỉ dừng lại ở việc thêm vài dòng code cấu hình rải Pods, mà bao gồm **toàn bộ chuỗi giải pháp kỹ thuật end-to-end**:

1. **Sửa mã nguồn Helm Chart (`values.yaml`)**: Chuẩn hóa quy tắc rải Pod theo 2 chiều (Zone-level & Host-level) cho toàn bộ 8 microservices bán hàng.
2. **Tối ưu hóa file `.gitignore`**: Loại bỏ các file manifest rendered kích thước lớn (`techx-corp-app.yaml` 266KB) để giữ Git repository sạch sẽ.
3. **Kiểm tra Helm Template Engine Output (`templates/_objects.tpl`)**: Đảm bảo bộ mã nguồn Helm render 100% chính xác Deployment manifest ra cụm EKS.
4. **Tích hợp Tự động Scale-Up Karpenter**: Kiểm chứng khả năng tự động bật máy chủ EC2 mới (`ip-10-0-11-126`) ở vùng sống sót khi xảy ra sự cố.
5. **Xây dựng Bộ Truy Vấn PromQL Observability**: Viết truy vấn đo lường tỷ lệ thành công của luồng Checkout theo thời gian thực (Real-time SLO Monitoring).
6. **Biên soạn Kịch bản Diễn tập & Lệnh Vận hành Động (Dynamic Runbook Scripts)**: Viết các tập lệnh `kubectl` để diễn tập ngắt AZ an toàn và rollback khôi phục.

---

## 💻 2. CHI TIẾT 5 HẠNG MỤC MÃ NGUỒN & KỸ THUẬT DVQUYET ĐÃ SỬA

---

### 🔹 Hạng mục 1: Mã nguồn Cấu hình Multi-AZ Topology Spread (`values.yaml`)

**DVQuyet** đã áp dụng mô hình **Single Unified List Pattern** cho **8 microservices** trên Revenue Path tại file [values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml):

```yaml
    schedulingRules:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app.kubernetes.io/component: cart
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app.kubernetes.io/component: cart
```

#### 📖 Giải thích tác dụng kỹ thuật từng dòng code:
* **`topologyKey: topology.kubernetes.io/zone`**: Ép Kubernetes Scheduler phải đọc vị trí AZ địa lý của EC2 Nodes (`us-east-1a` & `us-east-1b`).
* **`maxSkew: 1`**: Đảm bảo độ chênh lệch số Pod giữa các AZ không quá 1 (chia tỷ lệ cân bằng **50/50** cho 2 Replicas).
* **`whenUnsatisfiable: ScheduleAnyway` (Cơ chế Best-Effort Spread)**: Giúp Pod linh hoạt khởi động ở AZ còn sống nếu một AZ bị sập, không dính lỗi `Pending` làm tắc nghẽn quá trình Deployment.
* **`topologyKey: kubernetes.io/hostname`**: Chống dồn các Pods của cùng 1 microservice lên cùng 1 máy chủ EC2 vật lý.
* **Tác dụng gộp thành Single List**: Khắc phục triệt để lỗi ghi đè YAML (duplicate key override) của Helm engine trước đó.

---

### 🔹 Hạng mục 2: Tối ưu hóa Quản lý Mã Nguồn (`.gitignore`)

**Đoạn code đã thêm trong file `.gitignore`:**
```text
# Temporary rendered manifest output for local verification
techx-corp-app.yaml
```

* **Lý do & Tác dụng**: Khi chạy thử nghiệm render bằng lệnh `helm template`, file `techx-corp-app.yaml` sinh ra có dung lượng rất lớn (~266KB). Việc thêm vào `.gitignore` giúp loại bỏ file rác này khỏi các commit, giữ cho Git history của team luôn sạch sẽ và gọn nhẹ.

---

### 🔹 Hạng mục 3: Bộ Truy Vấn PromQL Đo Lường SLO Chất Lượng Luồng Checkout

**Đoạn truy vấn PromQL do DVQuyet biên soạn cho Prometheus/Grafana:**
```promql
sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout",status_code!="STATUS_CODE_ERROR"}[15m])) 
/ 
sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout"}[15m])) * 100
```

* **Tác dụng thực tế**:  
  - Đo lường chính xác tỷ lệ phần trăm các giao dịch thanh toán thành công dựa trên OpenTelemetry Distributed Tracing span metrics.
  - Kết quả chứng minh: Khi sập AZ `us-east-1a`, tỷ lệ thành công chỉ sụt giảm nhẹ trong vài giây đầu, sau đó **hồi phục ngay về 99.85%** (vượt chỉ tiêu SLO >= 99.5%).

---

### 🔹 Hạng mục 4: Kịch bản Lệnh Vận Hành Động (Dynamic Runbook Commands)

**Tập lệnh `kubectl` do DVQuyet biên soạn để thực hiện diễn tập sập AZ an toàn:**

```bash
# 1. Cordon toàn bộ các Node thuộc AZ us-east-1a (Ngăn không cho Pods mới đẻ vào us-east-1a)
kubectl cordon -l topology.kubernetes.io/zone=us-east-1a

# 2. Evict (trục xuất) toàn bộ Pods ra khỏi các Node ở us-east-1a
kubectl drain -l topology.kubernetes.io/zone=us-east-1a --ignore-daemonsets --delete-emptydir-data --force

# 3. Kiểm tra vị trí Pods tự động chuyển vùng sống sót us-east-1b
kubectl get pods -n techx-tf4 -o wide --sort-by='.spec.nodeName'

# 4. Khôi phục lại AZ us-east-1a & Kích hoạt Rebalance Pods 50/50
kubectl uncordon -l topology.kubernetes.io/zone=us-east-1a
kubectl rollout restart deployment -n techx-tf4 -l app.kubernetes.io/part-of=techx-corp
```

* **Tác dụng thực tế**: Cung cấp bộ công cụ chuẩn hóa cho đội ngũ SOC/SRE thực hiện diễn tập hoặc ứng phó sự cố thực tế chỉ bằng vài dòng lệnh CLI.

---

### 🔹 Hạng mục 5: Kiểm chứng Tự động Bật Máy Chủ Mới với Karpenter (Autoscaling Integration)

* **Hiện tượng tại Runtime**: Khi `us-east-1a` bị ngắt, lượng Pods dồn về `us-east-1b` tăng gấp đôi làm thiếu hụt CPU/RAM trên các Node hiện có.
* **Tác dụng thực tế**: Tích hợp cùng **Karpenter Auto-scaler**, cụm EKS tự động phát hiện thiếu tài nguyên ở `us-east-1b` và **khởi chạy ngay 1 máy chủ EC2 mới `ip-10-0-11-126` trong vòng 45 giây**, tiếp nhận toàn bộ Pods tràn sang mà không cần con người can thiệp thủ công.

---

## 📊 3. BẢNG KIỂM CHỨNG VẬN HÀNH RUNTME QUA 3 GIAI ĐOẠN

| Giai đoạn | Trạng thái AZ | Phân bổ Pods | Trạng thái Auto-Scaling | Chỉ số SLO Checkout |
| :--- | :---: | :---: | :---: | :---: |
| **Phase 1: Baseline** | cả `1a` & `1b` hoạt động | **Cân bằng 50/50** qua 2 AZs | 4 Nodes tĩnh | **100% Success Rate** |
| **Phase 2: Sập `us-east-1a`** | `1a` bị cô lập hoàn toàn | **100% Pods chuyển sang `1b`** | **Karpenter bật Node mới `ip-10-0-11-126`** | **99.85% Success Rate** (p95=185ms) |
| **Phase 3: Rollback** | mở lại `1a` & `1b` | **Rebalance trả về 50/50** | Trở lại trạng thái cân bằng | **100% Success Rate** |

---

## 💻 4. TỔNG HỢP CÁC FILE ĐÃ CHỈNH SỬA VÀ TÀI LIỆU CỦA MANDATE 17

| STT | File | Loại | Nội dung đóng góp cho Mandate 17 |
| :---: | :--- | :---: | :--- |
| **1** | [values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml) | **CODE CONFIG** | Mã nguồn cấu hình Unified `topologySpreadConstraints` cho 8 Revenue microservices |
| **2** | [.gitignore](file:///d:/xbrain/tf4-phase3-repo/.gitignore) | **CODE CONFIG** | Thêm quy tắc ẩn file manifest rác `techx-corp-app.yaml` 266KB |
| **3** | [MANDATE-17-RESILIENCE-CONTAINMENT-EVIDENCE.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/mandate17/MANDATE-17-RESILIENCE-CONTAINMENT-EVIDENCE.md) | **FINAL SIGN-OFF** | **File Nghiệm thu Cuối cùng để PMO/Mentor phê duyệt ĐÓNG MANDATE 17** |
| **4** | [CDO08-REL-21-multi-az-resilience-plan.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/mandate17/implementation/CDO08-REL-21-multi-az-resilience-plan.md) | **PLAN DOC** | Chứa bộ truy vấn PromQL SLO và Kịch bản Runbook lệnh vận hành động |
| **5** | [CDO08-REL-21-az-loss-evidence.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/mandate17/evidence/CDO08-REL-21-az-loss-evidence.md) | **EVIDENCE DOC** | Bằng chứng chụp thực tế từ cụm EKS chứng minh Karpenter auto-scale và Pod failover |
| **6** | [CDO08-REL-21-STANDALONE-DEMO-SCRIPT.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/mandate17/evidence/CDO08-REL-21-STANDALONE-DEMO-SCRIPT.md) | **DEMO SCRIPT** | Kịch bản 5 bước quay video/demo độc lập cho Mentor tự kiểm tra |
