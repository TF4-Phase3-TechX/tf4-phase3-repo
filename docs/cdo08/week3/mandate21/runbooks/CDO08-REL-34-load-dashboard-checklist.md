# 📋 CDO08-REL-34: Load Generator & Dashboard Operational Checklist
## Mandate 21: Single-AZ Loss Drill Readiness

- **Owner**: **Đinh Viết Quyết (DVQuyet) — Lead Security & Reliability Engineer**
- **Môi trường**: EKS Production `techx-tf4-cluster` | AWS Account `511825856493` | Region `us-east-1`
- **Mục tiêu**: Chuẩn hóa quy trình thiết lập tải, kênh truy cập private tunnel, bảng theo dõi dashboard và công thức đo RTO phục vụ đợt diễn tập sập AZ đột ngột.

---

## 1. 🔑 Kênh Truy Cập Private Portals (Cloudflare Access & SSM Fallback)

### 🌐 Happy Path: Truy Cập Trực Tiếp qua Cloudflare Access (Khuyên dùng)
Hệ thống vận hành được định tuyến bảo mật qua Cloudflare Access. Người vận hành truy cập trực tiếp bằng các liên kết sau (happy path):
* **Grafana Dashboard**: [https://grafana.techx-tf4.site/grafana](https://grafana.techx-tf4.site/grafana)
* **Locust Load Generator**: [https://loadgen.techx-tf4.site/](https://loadgen.techx-tf4.site/)
* **Jaeger Tracing**: [https://jaeger.techx-tf4.site/jaeger/ui](https://jaeger.techx-tf4.site/jaeger/ui)

---

### 🚨 Fallback / Break-Glass: SSM Tunnel qua Bastion Host
Trong trường hợp kênh Cloudflare Access gặp sự cố hoặc cần break-glass, sử dụng **SSM Port Forwarding Session** kết nối đến Bastion Host `tf4-portal-bastion` (`i-0690c5a0beb93845d`).

> 💡 **Mẹo tra cứu Instance ID động**:
> ```bash
> BASTION_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=tf4-portal-bastion" --query "Reservations[0].Instances[0].InstanceId" --output text)
> ```

#### 💻 Lệnh Mở Tunnel (Chạy trên Terminal Máy Cá Nhân)

```bash
# 1. Port-Forward Grafana (Local Port 3000 -> Remote Port 13000)
aws ssm start-session \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  --target i-0690c5a0beb93845d \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["13000"],"localPortNumber":["3000"]}'

# 2. Port-Forward Locust Load Generator (Local Port 8089 -> Remote Port 18089)
aws ssm start-session \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  --target i-0690c5a0beb93845d \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["18089"],"localPortNumber":["8089"]}'

# 3. Port-Forward Jaeger Distributed Tracing (Local Port 16686 -> Remote Port 16686)
aws ssm start-session \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  --target i-0690c5a0beb93845d \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["16686"],"localPortNumber":["16686"]}'
```

#### 🌐 Địa Chỉ Truy Cập Sau Khi Mở Tunnel Fallback
* **Grafana Dashboard**: [http://localhost:3000](http://localhost:3000)
* **Locust Load Generator**: [http://localhost:8089](http://localhost:8089)
* **Jaeger Tracing**: [http://localhost:16686](http://localhost:16686)

---

## 2. ⚡ Cấu Hình Load-Generator Profile Cho Diễn Tập

Tải phải được duy trì liên tục và ổn định trong suốt đợt diễn tập sập AZ.

### 📋 Thông Số Profile Chuẩn Hóa
* **Target URL**: `http://frontend-proxy:8080` (Luồng nội bộ cụm EKS)
* **Number of Users**: `200`
* **Spawn Rate**: `5` users/sec
* **Run Time**: `20m` (Đủ cho thời gian ngắt AZ + auto-failover + khôi phục)
* **User Behavior**: Mô phỏng đầy đủ luồng `Browse -> Cart -> Checkout`

### 💻 Lệnh Chạy Tải In-Cluster (Hoặc Kích Hoạt Qua Helm / Tunnel)

```bash
# Kích hoạt tải Locust Headless trong cụm EKS
kubectl exec -it deployment/load-generator -n techx-tf4 -- \
  locust --headless \
    -u 200 -r 5 \
    --run-time 20m \
    --host http://frontend-proxy:8080
```

---

## 3. 📊 Bảng Danh Sách Panel Dashboard Bắt Buộc Theo Dõi & Quay Màn Hình

Đợt diễn tập sập AZ đột ngột sử dụng bảng dashboard chuyên dụng: **Single-AZ Loss Drill (Mandate 21)**. Trong suốt quá trình diễn tập, màn hình quay phải hiển thị rõ các nhóm Panel sau trên Grafana:

| Nhóm Panel | Panel Description | Nguồn Metric / Query Focus | Trạng thái Kỳ vọng |
| :--- | :--- | :--- | :--- |
| **Business SLO** | **Checkout/Frontend/Cart Success Rate (%)** | OTel Tracing / PromQL (Checkout target $\ge 99\%$) | Duy trì $\ge 99.0\%$, chấp nhận sụt giảm tức thời $< 1\text{m}$ |
| **Business SLO** | **Latency p95 & p99 (ms)** | HTTP Span Duration Metrics | p95 $< 1000\text{ms}$ |
| **Business SLO** | **HTTP Error Rate (5xx)** | Proxy / App Status Codes | Mức $0\%$ (hoặc $< 0.1\%$ transient spike) |
| **Load** | **Requests Per Second (RPS)** | Frontend Proxy HTTP Rate | Giữ mức ổn định theo 200 Locust users |
| **Load** | **Active Users & Req/Err Count** | Load-generator metrics / Simulated users | Hiển thị 200 active users, count request/error tăng đều |
| **K8s Runtime** | **Pod Ready, Restart, Replicas** | `kube_pod_status_phase` / restarts | Replicas duy trì đầy đủ, restart rate không tăng đột biến |
| **K8s Runtime** | **HPA Current vs Max Replicas** | `kube_horizontalpodautoscaler_status` | HPA hoạt động ổn định khi dồn tải |
| **K8s Runtime** | **Pod Placement theo AZ/node** | `kube_pod_info` * `kube_node_labels` | Pods tự reschedule từ AZ sập sang AZ sống |
| **Node/AZ Health** | **Node Count theo AZ (Ready/NotReady)** | `kube_node_labels` / `topology.kubernetes.io/zone` | AZ bị sập biến mất Node, AZ sống tăng Node (Karpenter scale) |
| **Node/AZ Health** | **CPU/Memory pressure** | `kube_node_status_condition` / Node resource util | Không bị nghẽn CPU/RAM trên các node AZ còn sống |
| **Managed Data** | **RDS PostgreSQL Primary Role** | `postgresql_backends` / Active connections | Primary AZ tự chuyển đổi từ AZ sập sang AZ sống, connections hồi phục |
| **Managed Data** | **Valkey Health & Clients** | `redis_up` / `redis_connected_clients` | Valkey node failover tự động |
| **Managed Data** | **MSK Health & Consumer Lag** | `kafka_consumergroup_lag` | Đơn hàng được tiêu thụ bình thường, không lag |
| **RPO/RTO Markers**| **Failure Start / SLO Dip / Recovery** | Timestamps & timeline markers | Xác định chính xác RTO từ lúc sập đến khi khôi phục |
| **RPO/RTO Markers**| **Total Placed Orders / Event Count** | Transaction counter | Đối chiếu Postgres/Kafka/S3 để verify RPO = 0 |

---

## 4. 📐 Công Thức PromQL & Quy Trình Tính RTO Thực Tế

**Recovery Time Objective (RTO)** là khoảng thời gian tính từ khi chỉ số SLO bị suy giảm (SLO Dip) cho đến khi chỉ số hồi phục hoàn toàn về mức cam kết ($\ge 99.0\%$).

### 🔍 Truy Vấn PromQL Tính Checkout Success Rate (Real-time 1m Window)

```promql
sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout",status_code!="STATUS_CODE_ERROR"}[1m])) 
/ 
sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout"}[1m])) * 100
```

### 🔍 Truy Vấn PromQL Tính Latency p95

```promql
histogram_quantile(0.95, sum(rate(traces_span_metrics_calls_duration_seconds_bucket{service_name="frontend",span_name="POST /api/checkout"}[1m])) by (le)) * 1000
```

### ⏱️ Quy Trình Xác Định RTO Thực Tế:
1. **$T_{\text{dip}}$ (Thời điểm rớt SLO)**: Mốc thời gian (Timestamp UTC) khi Checkout Success Rate rơi xuống dưới `99.0%` hoặc Latency p95 vượt quá `1000ms`.
2. **$T_{\text{recover}}$ (Thời điểm khôi phục)**: Mốc thời gian (Timestamp UTC) khi Checkout Success Rate quay lại và duy trì ổn định trên `99.0%` liên tục trong 3 phút.
3. **$\text{RTO Actual} = T_{\text{recover}} - T_{\text{dip}}$**.

---

## 5. ✅ Checklist Chuẩn Bị Trước Giờ G

- [ ] Đã kiểm tra kết nối qua đường dẫn Cloudflare Access (Grafana, Locust, Jaeger) hoạt động bình thường.
- [ ] Đã chuẩn bị sẵn terminal mở SSM Tunnel (Grafana, Locust, Jaeger) làm kênh Fallback dự phòng.
- [ ] Đã mở sẵn Grafana dashboard chuyên dụng **Single-AZ Loss Drill (Mandate 21)** ở chế độ Auto-Refresh `5s`.
- [ ] Đã bật Locust Load Generator với 200 users và xác nhận RPS ổn định.
- [ ] Đã mở công cụ quay màn hình (OBS / Screen Recorder) sẵn sàng ghi hình kèm đồng hồ thời gian thực (UTC clock).
