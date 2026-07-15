# PERF-04 Evidence: Grafana Resource Pressure

Capture time: 2026-07-09 14:20 +07:00

## Mục tiêu

Thu thập bằng chứng runtime để xác định Grafana có bị thiếu RAM hay không.

## Lệnh kiểm tra pod detail

```powershell
kubectl describe pod -n techx-observability -l app.kubernetes.io/name=grafana
```

## Kết quả quan trọng

```text
Name:             grafana-5669788d6c-jhfmw
Namespace:        techx-observability
Status:           Running
Node:             ip-10-0-10-231.ec2.internal/10.0.10.231
```

Container chính `grafana`:

```text
State:           Running
Last State:      Terminated
  Reason:        OOMKilled
  Exit Code:     137
Restart Count:   7
Limits:
  memory:  300Mi
Requests:
  memory:  300Mi
GOMEMLIMIT: 314572800 (limits.memory)
```

Events:

```text
Warning  Unhealthy  Liveness probe failed: Get "http://10.0.10.185:3000/api/health": connect: connection refused
Warning  BackOff    Back-off restarting failed container grafana
Warning  Unhealthy  Readiness probe failed: Get "http://10.0.10.185:3000/api/health": connect: connection refused
```

## Đo CPU/RAM runtime

Dùng Grafana Explore hoặc Prometheus UI để kiểm tra CPU/memory của Grafana và worker nodes. Lưu screenshot hoặc kết quả PromQL cùng thời gian quan sát để đối chiếu với restart/OOM evidence.

```promql
sum(rate(container_cpu_usage_seconds_total{namespace="techx-observability", container!=""}[5m])) by (pod)
sum(container_memory_working_set_bytes{namespace="techx-observability", container!=""}) by (pod)
```

Kết quả resource evidence hiện tại được đối chiếu cùng container state và restart history bên dưới.

## Kết luận

Grafana có bằng chứng thiếu RAM rõ ràng:

- Container chính `grafana` từng bị `OOMKilled`.
- Exit code `137` xác nhận container bị kill do vượt giới hạn memory.
- Restart count của container chính là `7`.
- Memory request/limit hiện tại chỉ `300Mi`.
- Readiness/liveness probe từng fail do Grafana không kịp hoặc không thể phục vụ `/api/health` sau khi bị restart.

Vì vậy, tăng memory limit/request cho Grafana là hướng xử lý hợp lý, không chỉ là phỏng đoán.

## Khuyến nghị

Quick fix phù hợp cho Week 1:

```yaml
grafana:
  resources:
    requests:
      memory: 512Mi
    limits:
      memory: 768Mi
```

Nếu cần tiết kiệm hơn, có thể thử trước:

```yaml
grafana:
  resources:
    requests:
      memory: 512Mi
    limits:
      memory: 512Mi
```

Sau mỗi thay đổi memory, cần đo lại bằng Grafana/Prometheus và kiểm tra pod state/restart history.

Acceptance criteria:

- Không còn `OOMKilled`.
- Restart count không tăng thêm sau khi tăng memory.
- Grafana `/grafana/` vẫn trả `HTTP 200 OK`.

