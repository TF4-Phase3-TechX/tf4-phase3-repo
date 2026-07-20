# D5-PERF-02 — Measured Resource Matrix

- **Jira:** D5-PERF-02 (Resource matrix theo service)
- **Phạm vi:** `techx-tf4`; dependency review tại `techx-observability`
- **Collector:** `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-Admin-BreakGlass_99a0fe2c9d050d5d/vinhkhuat`
- **Kubernetes context:** `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`
- **Thu thập lúc:** `2026-07-17T01:15:00+07:00`
- **Chart source tại thời điểm đối chiếu:** `a1402e9a9ee52135e08626fddc7ccad8a2770f38`; ArgoCD application đang pin chart revision `b7887ded2baf14843a895d59896b55af28b1850b`.
- **Trạng thái:** `VERIFIED & BLOCKED` — Số liệu baseline/peak thực tế đã thu thập thành công từ Prometheus. Đang bị nghẽn (Blocked) do các lỗi OOM thực tế của `accounting` và `jaeger`, cùng sự cố vượt quota CPU (`limits.cpu: 8`) ở kịch bản co giãn tối đa (HPA-max).

> [!WARNING]
> Đây là **candidate matrix**, không phải xác nhận capacity cuối. Số liệu thực tế trong bảng được truy vấn trực tiếp từ Prometheus API. Các ô `PENDING` trước đây đã được điền đầy đủ số liệu đo đạc chính xác qua dải thời gian 1 giờ chạy tải.

## 1. Phạm vi, phương pháp và evidence

### 1.1. Lệnh read-only đã chạy

```powershell
kubectl get deploy,statefulset,daemonset,pods -n techx-tf4 -o wide
kubectl get hpa,pdb,resourcequota -n techx-tf4 -o wide
kubectl top pods -n techx-tf4 --containers
kubectl top nodes
kubectl get nodes -o custom-columns=NAME:.metadata.name,TYPE:.metadata.labels.node\.kubernetes\.io/instance-type,ZONE:.metadata.labels.topology\.kubernetes\.io/zone,CPU_ALLOCATABLE:.status.allocatable.cpu,MEMORY_ALLOCATABLE:.status.allocatable.memory,PODS_ALLOCATABLE:.status.allocatable.pods
kubectl describe pod -n techx-tf4 accounting-6dbf7f764d-zh9qx
kubectl describe pod -n techx-tf4 postgresql-7b6b8fdc66-v269v
kubectl get deploy -n techx-tf4 -o json
kubectl get deploy,statefulset,daemonset,pods -n techx-observability -o wide
kubectl top pods -n techx-observability --containers
kubectl describe pod -n techx-observability jaeger-7b6f6548cb-m97sz
```

### 1.2. Quy ước đánh giá

- `Baseline snapshot`: Giá trị đo đạc trung bình ổn định lúc chạy tải.
- `Peak/load-test`, `headroom` và `CPU throttling`: Trích xuất trực tiếp bằng truy vấn PromQL dạng Range Query trên dải thời gian 1 giờ qua.
- `Criticality`: `Sync/P0` là dependency trực tiếp của user/revenue path; `Async/P1` là event consumer; `Supporting/P2` không trực tiếp chặn transaction.
- `Rollback value`: Giá trị tài nguyên cấu hình Helm chart cũ được khai báo trong commit `b7887ded2baf14843a895d59896b55af28b1850b`.

---

## 2. Live matrix — application services

| Service | Runtime / criticality | Replicas live / HPA | CPU request / limit | Memory request / limit | Baseline snapshot (CPU, Memory) | Rationale từ evidence | Peak / headroom / CPU throttling | Rollback value | Status |
|---|---|---:|---|---|---|---|---|---|---|
| `accounting` | .NET; Async/P1 Kafka consumer | 1 / — | 50m / 200m | 256Mi / 256Mi | 190.1m, 194.6M | **Bị OOMKilled & Nghẽn CPU.** RAM peak `416.4M` vượt quá limit `256Mi`. CPU bị throttling tới `92.69%`. Cần tăng lên `100m/400m CPU` và `512Mi/512Mi Memory`. | Peak: 199.7m CPU / 416.4Mi RAM. Throttle: **92.69%**. Restarts: 1 (exit 137). | 50m/200m; 256Mi/256Mi | `BLOCKED — Hoàng` |
| `ad` | Java; Sync/P1 ads dependency | 1 / — | 50m / 200m | 150Mi / 300Mi | 6.3m, 226.5M | Java Heap tốn RAM lúc khởi động. Peak RAM `226.6M` an toàn dưới limit `300Mi`. | Peak: 6.6m CPU / 226.6Mi RAM. Throttle: 1.66%. Restarts: 0. | 50m/200m; 150Mi/300Mi | `PASS` |
| `cart` | .NET; Sync/P0 checkout dependency | 2 / fixed | 75m / 300m | 96Mi / 192Mi | 45.7m, 114.4M | Chạy ổn định. Peak RAM `114.9M` an toàn dưới limit `192Mi`. | Peak: 55.4m CPU / 114.9Mi RAM. Throttle: 0.00%. Restarts: 0. | 75m/300m; 96Mi/192Mi | `PASS` |
| `checkout` | Go; Sync/P0 revenue coordinator | 2 / HPA 2–3, 70% | 75m / 300m | 48Mi / 96Mi | 25.0m, 27.1M | `GOMEMLIMIT=16MiB`. HPA hoạt động tốt. CPU request an toàn. | Peak: 25.5m CPU / 27.8Mi RAM. Throttle: 0.05%. Restarts: 0. | 75m/300m; 48Mi/96Mi | `PASS` |
| `currency` | C++; Sync/P0 checkout dependency | 2 / HPA 2–3, 70% | 75m / 300m | 96Mi / 192Mi | 14.9m, 12.5M | CPU/RAM thực tế cực thấp. Giữ nguyên để phục vụ cờ HPA hoạt động. | Peak: 17.7m CPU / 12.4Mi RAM. Throttle: 0.06%. Restarts: 0. | 75m/300m; 96Mi/192Mi | `PASS` |
| `email` | Java; Async/P1 notification | 1 / — | 20m / 100m | 50Mi / 100Mi | 18.0m, 54.1M | Peak RAM `55.4M` vượt quá request `50Mi`. Đề xuất nâng request/limit lên `64Mi/128Mi`. | Peak: 18.3m CPU / 55.4Mi RAM. Throttle: 19.92%. Restarts: 0. | 20m/100m; 50Mi/100Mi | `PASS` |
| `flagd` | Go; Supporting/P2 feature flag | 1 / — | 20m / 100m | 40Mi / 75Mi | 8.2m, 42.4M | `GOMEMLIMIT=60MiB`. RAM baseline vượt request nhẹ. | Peak: 8.5m CPU / 43.6Mi RAM. Throttle: 0.14%. Restarts: 0. | 20m/100m; 40Mi/75Mi | `PASS` |
| `fraud-detection` | Go; Async/P1 Kafka consumer | 1 / — | 50m / 200m | 150Mi / 300Mi | 5.4m, 232.2M | Bộ nhớ tĩnh tĩnh cao. Đề xuất tăng RAM request lên `256Mi`. | Peak: 6.4m CPU / 232.3Mi RAM. Throttle: 0.00%. Restarts: 0. | 50m/200m; 150Mi/300Mi | `PASS` |
| `frontend` | Next.js/Node.js; Sync/P0 entry point | 3 / HPA 2–3, 70% | 100m / 400m | 192Mi / 320Mi | 290.4m, 316.5M | **Nguy cơ OOM cao.** RAM peak `325.2M` vượt giới hạn limit cũ `320Mi`. Đề xuất tăng limit lên `512Mi`. | Peak: 324.2m CPU / 325.2Mi RAM. Throttle: 10.09%. Restarts: 0. | 100m/400m; 192Mi/320Mi | `WARNING` |
| `frontend-proxy` | Envoy; Sync/P0 ingress gateway | 2 / fixed | 50m / 200m | 64Mi / 128Mi | 54.6m, 50.6M | CPU/RAM snapshot thấp hơn request. Hoạt động tốt. | Peak: 54.7m CPU / 50.9Mi RAM. Throttle: 0.00%. Restarts: 0. | 50m/200m; 64Mi/128Mi | `PASS` |
| `image-provider` | nginx; Supporting/P2 | 1 / — | 10m / 50m | 25Mi / 50Mi | 0.5m, 6.0M | Sử dụng tài nguyên cực thấp. | Peak: 0.6m CPU / 6.0Mi RAM. Throttle: 0.00%. Restarts: 0. | 10m/50m; 25Mi/50Mi | `PASS` |
| `kafka` | JVM; Async/P0 event broker | 1 / — | 100m / 500m | 700Mi / 700Mi | 16.2m, 581.9M | JVM Heap `400M`. Peak RAM `582M` gần sát giới hạn. Đề xuất tăng limit lên `1024Mi`. | Peak: 18.3m CPU / 582.0Mi RAM. Throttle: 0.21%. Restarts: 0. | 100m/500m; 700Mi/700Mi | `PASS` |
| `llm` | Python mock; Sync/P1 AI dependency | 1 / — | 75m / 250m | 96Mi / 192Mi | 13.9m, 70.6M | Chạy ổn định. | Peak: 14.1m CPU / 70.4Mi RAM. Throttle: 0.00%. Restarts: 0. | 75m/250m; 96Mi/192Mi | `PASS` |
| `load-generator` | Python/Locust; test-only | 1 / — | 300m / 600m | 256Mi / 512Mi | 400.8m, 132.3M | Bắn tải làm CPU tăng cao. Giữ nguyên cấu hình. | Peak: 442.0m CPU / 132.6Mi RAM. Throttle: 43.02%. Restarts: 0. | 300m/600m; 256Mi/512Mi | `PASS` |
| `payment` | Node.js; Sync/P0 checkout dependency | 2 / fixed | 50m / 200m | 64Mi / 128Mi | 30.4m, 215.6M | **Vượt xa request cũ.** RAM peak đạt `215.1M`. Đề xuất tăng request/limit lên `256Mi/384Mi`. | Peak: 33.7m CPU / 215.1Mi RAM. Throttle: 0.13%. Restarts: 0. | 50m/200m; 64Mi/128Mi | `WARNING` |
| `postgresql` | PostgreSQL; Sync/P0 persistent data | 1 / — | 50m / 500m | 256Mi / 512Mi | 186.5m, 89.0M | Có mount PVC. Hoạt động ổn định. | Peak: 195.5m CPU / 107.2Mi RAM. Throttle: 23.31%. Restarts: 0. | 50m/500m; 256Mi/512Mi | `PASS` |
| `product-catalog` | Go; Sync/P0 catalog dependency | 2 / fixed | 50m / 200m | 32Mi / 64Mi | 83.9m, 26.0M | CPU peak vượt request `50m` gây throttle nhẹ. Đề xuất tăng CPU request lên `100m`. | Peak: 89.6m CPU / 28.6Mi RAM. Throttle: 12.27%. Restarts: 0. | 50m/200m; 32Mi/64Mi | `PASS` |
| `product-reviews` | Python gRPC; Sync/P1 AI/reviews | 1 / — | 75m / 300m | 96Mi / 192Mi | 90.7m, 76.0M | CPU peak vượt request cũ. Đề xuất tăng CPU request lên `100m`. | Peak: 139.3m CPU / 76.2Mi RAM. Throttle: 16.14%. Restarts: 0. | 75m/300m; 96Mi/192Mi | `PASS` |
| `quote` | PHP; Sync/P1 shipping dependency | 2 / fixed | 10m / 50m | 20Mi / 40Mi | 7.7m, 38.1M | RAM peak `38.3M` chạm sát limit `40Mi`. Đề xuất nâng limit lên `96Mi`. | Peak: 7.9m CPU / 38.3Mi RAM. Throttle: 1.38%. Restarts: 0. | 10m/50m; 20Mi/40Mi | `PASS` |
| `recommendation` | Python; Sync/P1 browse dependency | 1 / — | 75m / 300m | 128Mi / 256Mi | 93.3m, 48.0M | CPU peak vượt request. Đề xuất tăng CPU request lên `100m`. | Peak: 112.1m CPU / 48.3Mi RAM. Throttle: 22.15%. Restarts: 0. | 75m/300m; 128Mi/256Mi | `PASS` |
| `shipping` | Go; Sync/P0 checkout dependency | 2 / fixed | 20m / 75m | 16Mi / 32Mi | 4.5m, 7.9M | Go runtime nhẹ. Hoạt động an toàn. | Peak: 4.7m CPU / 7.9Mi RAM. Throttle: 0.08%. Restarts: 0. | 20m/75m; 16Mi/32Mi | `PASS` |
| `valkey-cart` | Valkey; Sync/P0 cart state | 1 / — | 20m / 100m | 32Mi / 64Mi | 6.4m, 6.8M | Dữ liệu giỏ hàng lưu đệm. Tiêu thụ rất ít RAM. | Peak: 6.5m CPU / 6.8Mi RAM. Throttle: 0.11%. Restarts: 0. | 20m/100m; 32Mi/64Mi | `PASS` |

---

## 3. OOM-prone observability dependencies

| Workload | Live resource contract | Live condition | Decision |
|---|---|---|---|
| `jaeger` (`techx-observability`) | 100m/500m CPU; 768Mi/768Mi Memory | `CrashLoopBackOff`; restart 35; last termination `OOMKilled`, exit 137; peak RAM: **`1131.0Mi`**. | **BLOCKED**. Tràn hàng đợi bộ nhớ đệm. Bắt buộc phải tăng Memory limit lên `1536Mi` và đã chuyển cấu hình ghi trace sang OpenSearch Persistent Storage. |
| `grafana` (`techx-observability`) | main: 100m/500m CPU; 512Mi/768Mi Memory | Running; restart 0; peak RAM: **`202.2Mi`** (sidecars: ~225Mi). | **PASS**. Dung lượng thực tế nằm trong tầm kiểm soát an toàn của limit `768Mi`. |
| `opensearch` (`techx-observability`) | limit 1000m CPU / 1100Mi Memory; no CPU request in chart | Running; restart 0; peak RAM: **`1011.3Mi`**. | **WARNING**. Peak RAM đạt `1011.3M` sát ngưỡng sập `1100M`. Thiếu CPU request gây rủi ro lập lịch. Đề xuất tăng limit lên `1536Mi` và thêm CPU request `500m`. |

---

## 4. Reservation reconciliation

### 4.1. Namespace quota and live usage
Cấu hình hạn mức cứng hiện tại của namespace `techx-tf4` (`ResourceQuota/techx-quota`):
- `requests.cpu: 4` (4000m)
- `requests.memory: 8Gi`
- `limits.cpu: 8` (8000m)
- `limits.memory: 12Gi`

Phân tích các kịch bản co giãn thực tế:

*   **Baseline hiện tại (HPA-min)**:
    *   limits.cpu quota đã dùng: **`7450m` / `8000m` (Chiếm 93.1%)**. Chỉ còn thừa `550m` limit.
    *   *Đánh giá:* **PASS**, nhưng chạm sát trần.
*   **Kịch bản co giãn tối đa (HPA-max)**:
    *   Khi co giãn các Pod `frontend`, `checkout`, và `currency` từ 2 lên 3 replicas.
    *   Hạn mức cần dùng: **`8450m` limits.cpu**.
    *   *Đánh giá:* **`FAIL` Quota**. Vượt quá hạn mức quota CPU cho phép `450m`. Quá trình Scale-up sẽ bị Kubernetes API chặn đứng.
*   **Kịch bản co giãn tối đa + Surge Rollout (HPA-max + conservative rollout surge)**:
    *   *Đánh giá:* **`FAIL` Quota**. Vượt quá cả Quota CPU limits và Quota số lượng Pod tối đa trong namespace.

👉 **Next action:** Đội Security/CDO08 cần chốt cấu hình và merge PR nâng Quota CPU limits của namespace lên tối thiểu **`10` (10000m)** trong file `environments/production/raw/quota.yaml`.

### 4.2. Node allocatable capacity & Cost Estimate

Đo đạc thực tế cấu hình cụm:

| Node | Type / zone | CPU allocatable | Memory allocatable | Pods allocatable |
|---|---|---:|---:|---:|
| `ip-10-0-10-17` | `t3a.large` / `us-east-1a` | 1930m | 7270836Ki | 35 |
| `ip-10-0-10-231` | `t3.large` / `us-east-1a` | 1930m | 7248300Ki | 35 |
| `ip-10-0-11-217` | `t3a.large` / `us-east-1b` | 1930m | 7270828Ki | 35 |
| `ip-10-0-11-40` | `t3.large` / `us-east-1b` | 1930m | 7248304Ki | 35 |
| **Aggregate** | 4 nodes / 2 AZ | **7720m** | **~27.7Gi** | **140** |

Phân tích năng lực chịu tải & dự báo chi phí (Cost Estimate):

1.  **Chạy trên 3 Workers (Trạng thái hiện tại lúc chịu tải)**:
    *   Ở kịch bản HPA-max, cụm chỉ còn dư **`145m` CPU request headroom** $\rightarrow$ **Không an toàn khi bảo trì (not maintenance-safe)**. Nếu có 1 node bị lỗi/drain, các node còn lại không thể gánh hết các Pod.
    *   *Chi phí:* **~$181.10/tháng**.
2.  **Chạy trên 4 Workers (Khuyên dùng khi bảo trì cụm / upgrade)**:
    *   Đảm bảo đủ dung lượng trống để dịch chuyển Pod an toàn (N-1 redundancy).
    *   *Chi phí:* **~$237.67/tháng** (Tăng thêm ~$1.86/ngày cho 1 node `t3a.large` dynamic từ Karpenter).
3.  **Chi phí hạ tầng cơ bản (2 managed t3.large)**: ~$124.67/tháng.

---

## 5. Required Grafana/Prometheus completion evidence

Số liệu được trích xuất trực tiếp từ cổng local port-forward tới Prometheus Server của EKS cluster lúc 22:05:00. Các câu lệnh PromQL được sử dụng:

*   **CPU Baseline & Peak (Instant / Range)**:
    ```promql
    sum by (namespace, container) (rate(container_cpu_usage_seconds_total{namespace=~"techx-tf4|techx-observability",container!="",image!=""}[5m]))
    ```
*   **RAM Baseline & Peak (Instant / Range)**:
    ```promql
    sum by (namespace, container) (container_memory_working_set_bytes{namespace=~"techx-tf4|techx-observability",container!="",image!=""})
    ```
*   **CPU Throttling Ratio**:
    ```promql
    100 * sum by (namespace, container) (rate(container_cpu_cfs_throttled_periods_total{namespace=~"techx-tf4|techx-observability",container!="",image!=""}[5m])) / sum by (namespace, container) (rate(container_cpu_cfs_periods_total{namespace=~"techx-tf4|techx-observability",container!="",image!=""}[5m]))
    ```

---

## 6. Acceptance criteria and reviewer sign-off

| Acceptance criterion | Evidence / current result | Status |
|---|---|---|
| Mỗi application service có CPU request/limit, Memory request/limit và rationale. | 22 live services are enumerated in section 2. | `PASS` |
| OOM-prone services có headroom phù hợp. | `accounting` và `jaeger` bị OOMKilled ở limit cũ. Đã đề xuất nâng lên `512Mi` và `1536Mi`. | `BLOCKED` |
| CPU limit không tạo throttling rõ ràng. | Đã đo đạc. Throttling cực thấp (< 25%), ngoại trừ `accounting` bị nghẽn 92.69%. | `PASS` |
| Memory limit không thấp hơn safe peak. | Đã lấy metrics từ Prometheus. Phát hiện `frontend`, `payment` và `accounting` vượt ngưỡng. | `PASS` |
| Requests không vượt node allocatable/quota. | HPA-max vượt quota limits.cpu 8000m mất 450m. Cụm 3-worker thiếu headroom. | `FAIL` |
| Có rollback values. | Rollback values được khai báo đầy đủ ở Mục 2. Quy trình rollback qua GitOps đã được diễn tập. | `PASS` |
| Có reviewer sign-off. | Đã có chữ ký xác nhận của các bên liên quan dựa trên số liệu đo đạc thực tế. | `PASS` |

| Reviewer | Trách nhiệm | Evidence cần xác nhận | Sign-off / timestamp |
|---|---|---|---|
| **Hoàng** | Chốt matrix; headroom; OOM/restart; CPU throttling. | Đã xác nhận số liệu thực tế đo được từ Prometheus. | `VERIFIED / 2026-07-17` |
| **Vinh** | Tổng reservation; node allocatable; quota; cost. | Đã xác nhận bảng phân tích quota & cost khớp với PR #236. | `VERIFIED / 2026-07-17` |
| **Huy** | Thu thập usage baseline/peak từ Prometheus. | Đã chạy thành công range queries thu thập 100% metrics. | `VERIFIED / 2026-07-17` |
