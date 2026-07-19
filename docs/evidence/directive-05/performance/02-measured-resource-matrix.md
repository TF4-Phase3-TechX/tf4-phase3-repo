# D5-PERF-02 — Measured Resource Matrix

- **Jira:** D5-PERF-02 (Resource matrix theo service)
- **Phạm vi:** `techx-tf4`; dependency review tại `techx-observability`
- **Collector:** `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-Admin-BreakGlass_99a0fe2c9d050d5d/vinhkhuat`
- **Kubernetes context:** `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`
- **Thu thập lúc:** `2026-07-16T21:40:10+07:00`
- **Chart source tại thời điểm đối chiếu:** `a1402e9a9ee52135e08626fddc7ccad8a2770f38`; ArgoCD application đang pin chart revision `b7887ded2baf14843a895d59896b55af28b1850b`.
- **Trạng thái:** `BLOCKED` — live snapshot đã thu thập, nhưng chưa có Grafana baseline/peak/load-test time-series và đang có OOMKilled mới ở `accounting` cùng Jaeger CrashLoopBackOff.

> [!WARNING]
> Đây là **candidate matrix**, không phải xác nhận capacity cuối. `kubectl top` chỉ là instant snapshot, không thể chứng minh safe peak, memory headroom dài hạn hoặc CPU throttling. Những ô `PENDING` không được thay thế bằng số ước lượng.

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

Resource contract trong bảng là **effective live Deployment PodSpec**, không phải chỉ copy từ `values.yaml`. Giá trị đã đối chiếu với `techx-corp-chart/values.yaml`; các workload hiện tại khớp bốn resource fields tại runtime.

### 1.2. Quy ước đánh giá

- `Baseline snapshot`: giá trị `kubectl top` tại thời điểm trên; với nhiều replicas, biểu diễn `min–max`.
- `Peak/load-test`, `headroom` và `CPU throttling`: chỉ `PASS` sau khi Huy cung cấp Prometheus/Grafana raw result hoặc screenshot có time range, workload label và load-test metadata.
- `Criticality`: `Sync/P0` là dependency trực tiếp của user/revenue path; `Async/P1` là event consumer; `Supporting/P2` không trực tiếp chặn transaction.
- `Rollback value`: vì Jira này chưa deploy thay đổi, chính là live values phải quay lại nếu candidate matrix được áp dụng sau này. Rollback thực hiện bằng revert GitOps values về Git/Argo revision đã nêu, sau đó ArgoCD reconcile; `revisionHistoryLimit: 10` chỉ là lớp hỗ trợ ReplicaSet, không thay GitOps rollback.

## 2. Live matrix — application services

| Service | Runtime / criticality | Replicas live / HPA | CPU request / limit | Memory request / limit | Baseline snapshot (CPU, Memory) | Rationale từ evidence | Peak / headroom / CPU throttling | Rollback value | Status |
|---|---|---:|---|---|---|---|---|---|---|
| `accounting` | .NET; Async/P1 Kafka consumer | 1 / — | 50m / 200m | 256Mi / 256Mi | 197m, 182Mi | Memory snapshot còn 74Mi dưới limit nhưng pod vừa `OOMKilled`, exit 137, restart 1 lúc 21:15:58. Historical: [C0G-18](../../epic-03-performance-efficiency/runtime/c0g-18/accounting-oomkilled-monitoring.md). | `BLOCKED`: cần ≥24h working-set trend, `deriv`, `predict_linear`, restart count; không coi 1 snapshot là headroom. | 50m/200m; 256Mi/256Mi | `BLOCKED — Hoàng` |
| `ad` | Java; Sync/P1 ads dependency | 1 / — | 50m / 200m | 150Mi / 300Mi | 5m, 226Mi | Memory cao hơn request nhưng còn 74Mi dưới limit; CPU idle. | `PENDING — Huy` | 50m/200m; 150Mi/300Mi | `PENDING` |
| `cart` | .NET; Sync/P0 checkout dependency | 2 / fixed | 75m / 300m | 96Mi / 192Mi | 25–54m, 51–62Mi | Replica/PDB/topology spread đã chạy; snapshot usage thấp hơn request/limit. | `PENDING — Huy` | 75m/300m; 96Mi/192Mi | `PENDING` |
| `checkout` | Go; Sync/P0 revenue coordinator | 2 / HPA 2–3, 70% | 75m / 300m | 48Mi / 96Mi | 14–18m, 13Mi | `GOMEMLIMIT=16MiB`; request CPU bắt buộc cho HPA bởi [template](../../../../techx-corp-chart/templates/hpa.yaml). | `PENDING — Huy`; current HPA target 21%/70%. | 75m/300m; 48Mi/96Mi | `PENDING` |
| `currency` | C++; Sync/P0 checkout dependency | 2 / HPA 2–3, 70% | 75m / 300m | 96Mi / 192Mi | 1–22m, 5–6Mi | HPA enabled; snapshot far below configured limit. | `PENDING — Huy`; current HPA target 15%/70%. | 75m/300m; 96Mi/192Mi | `PENDING` |
| `email` | Java; Async/P1 notification | 1 / — | 20m / 100m | 50Mi / 100Mi | 27m, 54Mi | Snapshot memory vượt request nhưng còn 46Mi dưới limit; cần peak trước khi tăng request/limit. | `PENDING — Huy` | 20m/100m; 50Mi/100Mi | `PENDING` |
| `flagd` | Go; Supporting/P2 feature flag | 1 / — | 20m / 100m | 40Mi / 75Mi | 10m, 42Mi | `GOMEMLIMIT=60MiB`; snapshot vượt request, còn 33Mi dưới limit. | `PENDING — Huy` | 20m/100m; 40Mi/75Mi | `PENDING` |
| `fraud-detection` | Go; Async/P1 Kafka consumer | 1 / — | 50m / 200m | 150Mi / 300Mi | 6m, 232Mi | Memory snapshot vượt request, only 68Mi below limit; async backlog/peak must be measured. | `PENDING — Huy` | 50m/200m; 150Mi/300Mi | `PENDING` |
| `frontend` | Next.js/Node.js; Sync/P0 entry point | 3 / HPA 2–3, 70% | 100m / 400m | 192Mi / 320Mi | 35–158m, 101–114Mi | HPA is currently maxed at 3 replicas; target is 114%/70%, therefore CPU demand needs peak/throttle/latency correlation. | `BLOCKED — Huy/Hoàng`: HPA max reached; throttling and load p95 evidence absent. | 100m/400m; 192Mi/320Mi | `BLOCKED` |
| `frontend-proxy` | Envoy; Sync/P0 ingress gateway | 2 / fixed | 50m / 200m | 64Mi / 128Mi | 27–32m, 24–25Mi | PDB/topology spread; CPU/memory snapshot below request. | `PENDING — Huy` | 50m/200m; 64Mi/128Mi | `PENDING` |
| `image-provider` | nginx; Supporting/P2 | 1 / — | 10m / 50m | 25Mi / 50Mi | 1m, 5Mi | Low instant usage; no basis to reduce safe limit. | `PENDING — Huy` | 10m/50m; 25Mi/50Mi | `PENDING` |
| `kafka` | JVM; Async/P0 event broker | 1 / — | 100m / 500m | 700Mi / 700Mi | 15m, 580Mi | `KAFKA_HEAP_OPTS=-Xms400M -Xmx400M`; only 120Mi snapshot margin. Limit=request protects scheduling but needs load peak. | `PENDING — Huy` | 100m/500m; 700Mi/700Mi | `PENDING` |
| `llm` | Python mock; Sync/P1 AI dependency | 1 / — | 75m / 250m | 96Mi / 192Mi | 14m, 70Mi | Mock backend; usage below request but real model/provider substitution is out of scope. | `PENDING — Huy` | 75m/250m; 96Mi/192Mi | `PENDING` |
| `load-generator` | Python/Locust; test-only | 1 / — | 300m / 600m | 256Mi / 512Mi | 304m, 126Mi | CPU snapshot exceeds request as it generates traffic; exclude it from production user-path sizing, include it in namespace quota. | `PENDING — Huy` | 300m/600m; 256Mi/512Mi | `PENDING` |
| `payment` | Node.js; Sync/P0 checkout dependency | 2 / fixed | 50m / 200m | 64Mi / 128Mi | 15–16m, 104–105Mi | Memory exceeds request and has only 23–24Mi snapshot margin; payment is revenue-critical. | `PENDING — Huy/Hoàng` | 50m/200m; 64Mi/128Mi | `PENDING` |
| `postgresql` | PostgreSQL; Sync/P0 persistent data | 1 / — | 50m / 500m | 256Mi / 512Mi | 181m, 89Mi | Current pod has 0 restarts; historical OOM was probable shared-node contention with Jaeger, not confirmed solely by Postgres resource: [C0G-39](../../epic-03-performance-efficiency/runtime/c0g-39/postgresql-oomkilled-investigation.md). PVC is present live. | `PENDING — Huy/Hoàng`: require peak, node placement and Jaeger recovery evidence. | 50m/500m; 256Mi/512Mi | `PENDING` |
| `product-catalog` | Go; Sync/P0 catalog dependency | 2 / fixed | 50m / 200m | 32Mi / 64Mi | 9–71m, 12–13Mi | `GOMEMLIMIT=16MiB`; one replica CPU > request in snapshot, so do not lower request from this sample. | `PENDING — Huy` | 50m/200m; 32Mi/64Mi | `PENDING` |
| `product-reviews` | Python gRPC; Sync/P1 AI/reviews | 1 / — | 75m / 300m | 96Mi / 192Mi | 87m, 75Mi | CPU snapshot > request; calls LLM and PostgreSQL. | `PENDING — Huy` | 75m/300m; 96Mi/192Mi | `PENDING` |
| `quote` | PHP; Sync/P1 shipping dependency | 2 / fixed | 10m / 50m | 20Mi / 40Mi | 4–5m, 19Mi | Memory sits near request; needs shipping-flow peak. | `PENDING — Huy` | 10m/50m; 20Mi/40Mi | `PENDING` |
| `recommendation` | Python; Sync/P1 browse dependency | 1 / — | 75m / 300m | 128Mi / 256Mi | 54m, 48Mi | CPU snapshot below request but non-trivial; no evidence to normalize downward. | `PENDING — Huy` | 75m/300m; 128Mi/256Mi | `PENDING` |
| `shipping` | Go; Sync/P0 checkout dependency | 2 / fixed | 20m / 75m | 16Mi / 32Mi | 2–3m, 3Mi | `quote` dependency; low instant usage only. | `PENDING — Huy` | 20m/75m; 16Mi/32Mi | `PENDING` |
| `valkey-cart` | Valkey; Sync/P0 cart state | 1 / — | 20m / 100m | 32Mi / 64Mi | 7m, 6Mi | Persistent cart store; low instant usage only. | `PENDING — Huy` | 20m/100m; 32Mi/64Mi | `PENDING` |

## 3. OOM-prone observability dependencies

| Workload | Live resource contract | Live condition | Decision |
|---|---|---|---|
| `jaeger` (`techx-observability`) | 100m/500m CPU; 768Mi/768Mi Memory | `CrashLoopBackOff`; restart 35; last termination `OOMKilled`, exit 137; pod is on `ip-10-0-11-217`. | `BLOCKED`. Do not raise limit automatically: historical evidence identifies in-memory trace behavior as a contributing risk ([C0G-19](../../epic-03-performance-efficiency/runtime/c0g-19/jaeger-grafana-oom.md)). Hoàng must diagnose current configuration/peak before final sign-off. |
| `grafana` (`techx-observability`) | main: 100m/500m CPU; 512Mi/768Mi Memory; three sidecars have own resources | Running, restart 0; main snapshot 11m/201Mi; sidecars total 4m/~225Mi. | `PENDING`. Need full Pod-level memory peak including sidecars before confirming headroom. |
| `opensearch` (`techx-observability`) | limit 1000m CPU / 1100Mi Memory; no main request in chart source | Running; snapshot 163m/935Mi. | `BLOCKED` for observability capacity: snapshot leaves 165Mi below limit and missing request affects scheduler reservation. This is a separate remediation candidate, not a silent default. |

## 4. Reservation reconciliation

### 4.1. Namespace quota and live usage

| Scenario | Pods | CPU requests | Memory requests | CPU limits | Memory limits | Verdict |
|---|---:|---:|---:|---:|---:|---|
| `HPA-min` (frontend 2, checkout 2, currency 2) | 31 | 1905m | 3491Mi | 7450m | 5893Mi | Fits current `techx-quota` hard limits. |
| **Live now** (frontend is 3 because HPA target 114%/70%) | 32 | 2005m | 3683Mi | 7850m | 6213Mi | Fits, but only **150m CPU-limit** remaining. |
| `HPA-max` (frontend 3, checkout 3, currency 3) | 34 | 2155m | 3827Mi | 8450m | 6501Mi | **`BLOCKED`**: exceeds `limits.cpu: 8` by 450m. The quota will reject required scale-up unless changed through reviewed GitOps. |

Live `ResourceQuota/techx-quota`: `pods 32/40`, `requests.cpu 2005m/4`, `requests.memory 3683Mi/8Gi`, `limits.cpu 7850m/8`, `limits.memory 6213Mi/12Gi`.

The reconciliation uses live quota status because it reflects the effective scheduler/quota resource model, including workload lifecycle behavior. The HPA-max delta from live is one `checkout` and one `currency` Pod: `+150m CPU request`, `+144Mi Memory request`, `+600m CPU limit`, `+288Mi Memory limit`.

### 4.2. Node allocatable capacity

| Node | Type / zone | CPU allocatable | Memory allocatable | Pods allocatable |
|---|---|---:|---:|---:|
| `ip-10-0-10-17` | `t3a.large` / `us-east-1a` | 1930m | 7270836Ki | 35 |
| `ip-10-0-10-231` | `t3.large` / `us-east-1a` | 1930m | 7248300Ki | 35 |
| `ip-10-0-11-217` | `t3a.large` / `us-east-1b` | 1930m | 7270828Ki | 35 |
| `ip-10-0-11-40` | `t3.large` / `us-east-1b` | 1930m | 7248304Ki | 35 |
| **Aggregate** | 4 nodes / 2 AZ | **7720m** | **~27.7Gi** | **140** |

`HPA-max` requests fit **aggregate** allocatable capacity, but this is not a scheduler-placement or N-1 guarantee: topology spread, existing cross-namespace workloads, and per-node resource distribution still apply. Vinh must validate these constraints and the cost implication before sign-off.

## 5. Required Grafana/Prometheus completion evidence

Huy must attach query output/screenshot, time range, timezone, exact workload labels and test metadata for baseline, peak and approved load-test window. Required queries include:

```promql
sum by (namespace, pod, container) (
  rate(container_cpu_usage_seconds_total{namespace=~"techx-tf4|techx-observability",container!="",image!=""}[5m])
)
```

```promql
max_over_time(container_memory_working_set_bytes{namespace=~"techx-tf4|techx-observability",container!="",image!=""}[$__range])
```

```promql
100 * sum by (namespace,pod,container) (rate(container_cpu_cfs_throttled_periods_total{namespace=~"techx-tf4|techx-observability",container!="",image!=""}[5m]))
/ sum by (namespace,pod,container) (rate(container_cpu_cfs_periods_total{namespace=~"techx-tf4|techx-observability",container!="",image!=""}[5m]))
```

```promql
increase(kube_pod_container_status_restarts_total{namespace=~"techx-tf4|techx-observability"}[$__range])
```

```promql
kube_pod_container_status_last_terminated_reason{namespace=~"techx-tf4|techx-observability",reason="OOMKilled"}
```

CPU limit is only accepted as “không gây throttling rõ” when the throttle ratio is evaluated during peak and correlated with request throughput/latency or HPA state. Memory limit is only accepted as safe after measured peak plus an explicit headroom decision for the runtime and service criticality.

## 6. Acceptance criteria and reviewer sign-off

| Acceptance criterion | Evidence / current result | Status |
|---|---|---|
| Mỗi application service có CPU request/limit, Memory request/limit và rationale. | 22 live services are enumerated in section 2. | `PASS` |
| OOM-prone services có headroom phù hợp. | `accounting` has a fresh OOMKilled; Jaeger is CrashLoopBackOff OOMKilled; time-series evidence absent. | `BLOCKED` |
| CPU limit không tạo throttling rõ ràng. | No peak-window throttling evidence is attached. | `PENDING` |
| Memory limit không thấp hơn safe peak. | No baseline/peak/load-test time series is attached. | `PENDING` |
| Requests không vượt node allocatable/quota. | HPA-min/live fits; HPA-max violates `limits.cpu` quota by 450m. Aggregate node fit only. | `BLOCKED` |
| Có rollback values. | Every service row includes current rollback value; GitOps rollback procedure is stated. | `PASS` |
| Có reviewer sign-off. | Awaiting owner evidence below. | `PENDING` |

