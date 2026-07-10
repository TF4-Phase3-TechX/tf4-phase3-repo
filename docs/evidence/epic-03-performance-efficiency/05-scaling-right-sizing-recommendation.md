# PERF-05: Khuyến nghị scaling và right-sizing

Ngày rà soát: 2026-07-10

## 1. Mục tiêu và phạm vi

Tài liệu này đối chiếu cấu hình trong repository với bằng chứng runtime của Week 1 để xác định việc nào có thể triển khai ngay và việc nào cần thêm số liệu.

Nguồn chính:

- `techx-corp-chart/values.yaml`
- `techx-corp-chart/templates/_objects.tpl`
- `deploy/values-app-stamp.yaml`
- `deploy/values-observability.yaml`
- `deploy/quota.yaml`
- `infra/terraform/eks.tf`
- `docs/evidence/epic-03-performance-efficiency/04-runtime-performance-evidence.md`
- `docs/evidence/epic-03-performance-efficiency/runtime/`

Phạm vi hiện tại gồm application release trong namespace `techx-tf4` và observability release trong namespace `techx-observability`. Workflow deploy tách hai release này. Vì vậy, resource plan và quota phải được đánh giá riêng theo từng namespace.

## 2. Kết quả kiểm tra implementation

### 2.1. Resource configuration hiện tại

Chart render trực tiếp `.resources` của từng component vào container spec tại `techx-corp-chart/templates/_objects.tpl:67-68`.

Các application component đang có memory limit nhưng không khai báo CPU request hoặc CPU limit. Phần lớn cũng không viết memory request trong `values.yaml`. Tuy nhiên, cần hiểu đúng Kubernetes semantics: khi container chỉ có memory limit và namespace không có `LimitRange` tạo mặc định khác, Kubernetes có thể đặt memory request bằng chính memory limit. Vì vậy không nên kết luận scheduler hoàn toàn không nhìn thấy memory request. Vấn đề thực tế là request có thể bị mặc định bằng limit mà không dựa trên measured usage, còn CPU request vẫn thiếu.

Một số cấu hình cần chú ý:

| Component | Cấu hình trong repository | Kết luận |
|---|---|---|
| `accounting` | memory limit `120Mi` tại `values.yaml:186-188` | Runtime từng có `OOMKilled`; phải xử lý trước khi giảm tài nguyên |
| `checkout` | `GOMEMLIMIT=16MiB`, memory limit `20Mi` tại `values.yaml:277-281` | Headroom cấu hình khoảng `4MiB`; đây là config-based risk, chưa phải OOM đã được xác nhận |
| `frontend` | memory limit `250Mi` tại `values.yaml:403-405` | Chưa có CPU request; chưa đủ số liệu để chốt request/limit mới |
| `product-reviews` | memory limit `100Mi` tại `values.yaml:628-630` | Chưa có CPU request; mức tăng đề xuất phải dựa trên load test |
| `payment` | memory limit `140Mi` tại `values.yaml:556-558` | Tài liệu cũ ghi `60Mi`, không còn đúng |
| `llm` | không có `resources` tại `values.yaml:817-830` | Có thể chạy ở QoS `BestEffort` nếu không có default từ namespace |
| `load-generator` | memory limit `1500Mi` và `LOCUST_AUTOSTART=true` tại `values.yaml:498-535` | Có thể tạo tải nền và chiếm phần lớn capacity được quota cho phép |

Không nên dùng một baseline `50m/64Mi` cho tất cả service còn lại. Runtime, ngôn ngữ và vai trò của `kafka`, PostgreSQL, Valkey, `recommendation`, `accounting` và các stateless service khác nhau rõ rệt. Stateful workload cũng không nên được gộp vào nhóm application service khi right-size.

### 2.2. Runtime evidence hiện có

Bằng chứng Week 1 cho thấy:

- Application pods từng ở trạng thái `Running`, nhưng `accounting`, `checkout` và `load-generator` có restart history.
- `accounting` từng bị `OOMKilled`. Evidence ở các thời điểm khác nhau ghi restart count khác nhau, nên restart count phải luôn đi kèm timestamp, pod name và nguồn lệnh.
- `checkout` có 4 restart trong snapshot ngày 2026-07-09. Nguyên nhân đã ghi nhận là Kafka chưa sẵn sàng lúc startup, không phải OOM.
- Grafana trong namespace `techx-observability` từng bị `OOMKilled`, exit code `137`, restart count `7`, với request/limit `300Mi` trong runtime evidence.
- `kubectl top` không dùng được vì cluster chưa có `metrics.k8s.io`; repository cũng không triển khai `metrics-server`.
- Grafana và Prometheus có dashboard/PromQL để xem trend, nhưng repository chưa có bộ dữ liệu 48 đến 72 giờ đủ để xác nhận toàn bộ giá trị right-sizing trong bảng cũ.

Kết luận: các con số request/limit trong tài liệu cũ chỉ là giả thuyết để thử nghiệm. Chúng chưa phải cấu hình đã được đo và phê duyệt.

## 3. Ưu tiên right-sizing

### P0: xử lý sự cố đã có bằng chứng

#### `accounting`

- Không giảm memory.
- Điều tra peak memory, .NET runtime, OpenTelemetry instrumentation và consumer workload.
- Có thể thử memory request/limit trong khoảng `200Mi` đến `256Mi`, nhưng đây là trial value, không phải mức đã xác nhận.
- Sau rollout, theo dõi ít nhất 24 giờ và xác nhận không có `OOMKilled` mới, restart count không tăng và Kafka consumer vẫn xử lý bình thường.

#### `checkout`

- Init container `wait-for-kafka` đã có trong repository tại `values.yaml:282-285`. Vì vậy tài liệu không nên tiếp tục mô tả việc thêm bước chờ Kafka như một thay đổi chưa tồn tại.
- Tăng memory chỉ nên được thử sau khi render manifest và quan sát runtime. Mức khởi đầu hợp lý để thử là request `32Mi`, limit `64Mi`, đồng thời đặt `GOMEMLIMIT` khoảng 80% limit, ví dụ `50MiB`.
- Xác nhận lại startup behavior, p95/p99, error rate và restart count sau rollout.

#### Grafana

- Không giảm memory khi đã có bằng chứng `OOMKilled` ở `300Mi`.
- Trial value `request=512Mi`, `limit=768Mi` có thể dùng để kiểm chứng reliability. Cấu hình này chưa có trong `values.yaml` và chưa được xác nhận bằng runtime sau rollout.

### P1: bổ sung measured requests

Thứ tự thực hiện:

1. Ghi nhận CPU và memory theo pod bằng Prometheus/Grafana trong 48 đến 72 giờ.
2. Tách baseline idle và controlled load test.
3. Lấy p50, p95, peak, restart và `OOMKilled` theo từng container.
4. Chọn memory request theo mức sử dụng ổn định có headroom; đặt memory limit theo peak và behavior của runtime.
5. Chọn CPU request từ measured usage; chỉ thêm CPU limit khi đã đánh giá nguy cơ throttling cho latency-sensitive service.
6. Render manifest và kiểm tra tổng request/limit theo namespace trước khi deploy.

CPU limit không phải cách bảo đảm service không tranh chấp CPU. CPU request ảnh hưởng scheduling và CPU share khi có contention, còn CPU limit có thể gây throttling. Vì vậy, critical path cần CPU request được đo trước; CPU limit phải được kiểm chứng bằng latency và throttling metrics.

## 4. ResourceQuota và admission

`deploy/quota.yaml` đặt:

```yaml
requests.cpu: "4"
requests.memory: 8Gi
limits.cpu: "8"
limits.memory: 12Gi
pods: "40"
```

File này là manifest mẫu/manual. Workflow `.github/workflows/deploy.yaml` không apply `deploy/quota.yaml`, và repository không có `LimitRange` để tạo CPU request/limit mặc định.

Nếu quota này được apply vào namespace chứa application release, pod mới thiếu CPU request hoặc CPU limit có thể bị admission từ chối. Vì vậy trạng thái "pods đang Running" không chứng minh quota tương thích, vì quota có thể chưa được áp dụng.

Cần kiểm tra bằng:

```bash
kubectl -n techx-tf4 get resourcequota,limitrange
kubectl apply --dry-run=server -n techx-tf4 -f <rendered-app-manifest>
```

Nếu team muốn áp dụng quota cho cả `techx-tf4` và `techx-observability`, phải có hai manifest hoặc cơ chế apply rõ ràng cho từng namespace. Đồng thời cần tính tổng request/limit của app release và observability release riêng biệt.

Acceptance criteria:

- Rendered manifests có CPU/memory request và limit phù hợp với policy.
- Server-side dry-run không bị lỗi quota.
- Tổng resource không vượt quota của namespace.
- Rollout hoàn tất và pod không có `FailedScheduling` hoặc admission error.

## 5. HPA

Repository hiện không có manifest `HorizontalPodAutoscaler`, không có `metrics-server` và `metrics.k8s.io` đang unavailable trong runtime evidence. Vì vậy HPA CPU cho `frontend` hoặc `checkout` chưa thể hoạt động chỉ bằng cách thêm `minReplicas`, `maxReplicas` và target CPU.

HPA theo CPU utilization cần:

- CPU request cho mọi container trong pod được tính metric.
- Resource Metrics API, thường do `metrics-server` cung cấp, hoặc một adapter tương thích nếu dùng custom metrics.
- Deployment có readiness/liveness behavior đủ ổn định.
- Load test xác nhận scale-out và scale-in không làm tăng error rate.

Ngoài ra, `max_size=4` trong EKS managed node group chỉ đặt giới hạn Auto Scaling Group. Repository chưa cài Cluster Autoscaler hoặc Karpenter, nên không nên claim node group sẽ tự scale từ 2 lên 4 theo pending pods.

Đề xuất thử nghiệm sau khi hoàn tất prerequisites:

| Service | minReplicas thử nghiệm | maxReplicas thử nghiệm | CPU target ban đầu | Ghi chú |
|---|---:|---:|---:|---|
| `frontend` | 2 | 5 | 70% | Chỉ áp dụng sau khi có CPU request và Metrics API |
| `checkout` | 2 | 4 | 75% | Kiểm tra Kafka producer behavior, idempotency và downstream capacity |

Các con số trên là test parameters, không phải capacity plan đã được xác nhận.

## 6. Kế hoạch triển khai

### Giai đoạn 1: reliability trước

1. Xử lý `accounting` OOM và xác minh trong 24 giờ.
2. Kiểm chứng memory trial cho `checkout` và Grafana.
3. Tắt synthetic traffic ngoài controlled load test.
4. Ghi lại pod name, timestamp, restart count và `OOMKilled` sau mỗi rollout.

### Giai đoạn 2: resource baseline

1. Thu thập PromQL trong 48 đến 72 giờ.
2. Đề xuất request/limit theo từng service, không dùng một giá trị chung cho tất cả.
3. Render hai release và tính tổng resource theo namespace.
4. Chạy server-side dry-run với ResourceQuota.

### Giai đoạn 3: autoscaling

1. Cài và kiểm chứng Resource Metrics API hoặc custom metrics adapter.
2. Bổ sung HPA bằng `autoscaling/v2`.
3. Chạy controlled load test.
4. Kiểm tra desired/current replicas, p95/p99, error rate, throttling, restart và node headroom.
5. Chỉ đánh giá node autoscaling sau khi có Cluster Autoscaler hoặc Karpenter.

## 7. Trạng thái

| Hạng mục | Trạng thái |
|---|---|
| Phân tích resource configuration | Đã đối chiếu với repository |
| Giá trị request/limit mới | Chưa được implement hoặc runtime-verified |
| ResourceQuota compatibility | Chưa được kiểm chứng; quota không nằm trong deploy workflow |
| HPA | Chưa được implement; thiếu Metrics API và CPU requests |
| Node autoscaling | Chưa được implement; Terraform chỉ cấu hình ASG min/desired/max |

Tài liệu này là recommendation có điều kiện. Chỉ đánh dấu hoàn tất sau khi có config change, rendered manifest, rollout evidence và số liệu trước/sau thay đổi.
