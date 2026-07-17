# Review Request: CDO04 duyệt rightsizing cho Currency Service

**Requester:** CDO08 - Reliability / Platform  
**Reviewer:** CDO04 - Cost Optimization / Performance Efficiency  
**Ngày tạo:** 2026-07-17  
**Phạm vi:** `techx-tf4/currency`  
**Lý do:** Checkout phát sinh lỗi khi gọi `CurrencyService.Convert` trong giai đoạn tải cao.

## 1. Tóm tắt đề xuất

CDO08 đề xuất CDO04 duyệt thay đổi resource cho `currency` theo hướng tăng CPU headroom trước, chưa thay đổi memory.

| Item | Current | Proposed | Ghi chú |
|---|---:|---:|---|
| `requests.cpu` | `75m` | `150m` | Tăng reservation để phản ánh vai trò critical trong checkout path. |
| `limits.cpu` | `300m` | `750m` | Cho phép burst CPU tốt hơn khi checkout/load tăng. |
| `requests.memory` | `96Mi` | `96Mi` | Chưa thấy evidence memory pressure. |
| `limits.memory` | `192Mi` | `192Mi` | Giữ nguyên để tránh tăng footprint không cần thiết. |
| HPA `minReplicas` | `2` | `2` | Giữ HA baseline hiện tại. |
| HPA `maxReplicas` | `3` | `3` | Không tăng ngay để tránh quota/cost spike; đánh giá lại sau regression test. |
| HPA target CPU | `70%` | `70%` | Giữ nguyên để thay đổi lần này chỉ tập trung vào resource size. |

**Recommendation:** approve cấu hình proposed ở trên cho một rollout có kiểm soát. Nếu sau post-enforcement test vẫn còn `CurrencyService.Convert` timeout hoặc HPA chạm max 3 thường xuyên, mở review request tiếp theo để cân nhắc tăng `maxReplicas` lên `4`.

## 2. Evidence đã xác minh

### 2.1. Currency nằm trên checkout critical path

Checkout gọi `CurrencyService.Convert` khi chuẩn bị đơn hàng. Nếu call này chậm hoặc timeout, frontend checkout có thể trả lỗi `500`.

Evidence source:

```text
techx-corp-platform/src/checkout/main.go
```

Checkout hiện có per-call timeout cho currency convert là `1s`, thông qua `retryRead`.

### 2.2. Runtime hiện tại của Currency

Runtime hiện tại:

```text
Deployment: techx-tf4/currency
Replicas: 2 desired / 2 available
Requests: cpu 75m, memory 96Mi
Limits:   cpu 300m, memory 192Mi
HPA: min 2, max 3, target CPU 70%
```

HPA event đã ghi nhận nhiều lần scale lên 3:

```text
SuccessfulRescale ... New size: 3; reason: cpu resource utilization above target
```

Điều này cho thấy `currency` đã từng bị đẩy lên sát năng lực HPA hiện tại trong giai đoạn tải cao.

### 2.3. Dấu hiệu ảnh hưởng checkout

Trong window nghi vấn ngày 2026-07-17, Prometheus có evidence:

```text
checkout -> CurrencyService.Convert có rpc_grpc_status_code="4"
```

`rpc_grpc_status_code="4"` là deadline exceeded. Tại khoảng 06:28 UTC, p95 của `checkout -> CurrencyService.Convert` khoảng `2425ms`, vượt timeout 1 giây của checkout.

Ngoài ra `app_frontend_requests_total` có status `500` cho `POST /api/checkout`.

## 3. Vì sao không đề xuất tăng thẳng lên `1000m`

Tăng `limits.cpu` lên `1000m` có thể giảm throttling mạnh hơn, nhưng tác động quota lớn hơn:

| Option | Per-pod CPU limit | Max replicas | Max CPU limit reservation theo quota |
|---|---:|---:|---:|
| Current | `300m` | 3 | `900m` |
| Proposed | `750m` | 3 | `2250m` |
| Aggressive | `1000m` | 3 | `3000m` |

Cluster hiện đã từng có ResourceQuota pressure ở `limits.cpu`, nên CDO08 không muốn tăng quá mạnh nếu chưa có CDO04 duyệt cost/performance trade-off.

## 4. Cost / quota impact

CPU request tăng:

| State | Min replicas | Max replicas | Total CPU request |
|---|---:|---:|---:|
| Current | 2 | 3 | `150m` min / `225m` max |
| Proposed | 2 | 3 | `300m` min / `450m` max |
| Delta |  |  | `+150m` min / `+225m` max |

CPU limit tăng:

| State | Min replicas | Max replicas | Total CPU limit |
|---|---:|---:|---:|
| Current | 2 | 3 | `600m` min / `900m` max |
| Proposed | 2 | 3 | `1500m` min / `2250m` max |
| Delta |  |  | `+900m` min / `+1350m` max |

Tác động billing trực tiếp chưa chắc tăng nếu node count không đổi. Tuy nhiên scheduler/quota headroom sẽ giảm, nên CDO04 cần xác nhận:

- ResourceQuota `limits.cpu` còn đủ sau thay đổi.
- Node headroom còn đủ khi `currency` burst.
- Không làm các workload khác bị `FailedScheduling` hoặc quota rejection.

## 5. Rollout plan đề xuất

1. CDO04 approve proposed size.
2. CDO08 cập nhật Helm values qua Git PR, không patch trực tiếp production.
3. Deploy qua GitOps/Argo CD.
4. Verify rollout:

```bash
kubectl -n techx-tf4 rollout status deploy/currency --timeout=180s
kubectl -n techx-tf4 get deploy,hpa,pods -o wide | grep -E 'currency|NAME'
kubectl -n techx-tf4 describe hpa currency
```

5. Theo dõi Grafana/Prometheus trong observation window:

```promql
histogram_quantile(
  0.95,
  sum(rate(rpc_client_duration_milliseconds_bucket{
    service_name="checkout",
    rpc_service="oteldemo.CurrencyService",
    rpc_method="Convert"
  }[5m])) by (le)
)
```

```promql
sum(rate(rpc_client_duration_milliseconds_count{
  service_name="checkout",
  rpc_service="oteldemo.CurrencyService",
  rpc_method="Convert",
  rpc_grpc_status_code="4"
}[5m]))
```

```promql
sum(rate(container_cpu_cfs_throttled_periods_total{
  namespace="techx-tf4",
  container="currency"
}[5m]))
/
sum(rate(container_cpu_cfs_periods_total{
  namespace="techx-tf4",
  container="currency"
}[5m]))
```

## 6. Acceptance criteria

- `currency` rollout complete, all pods `Ready`.
- Không có `FailedScheduling`, `exceeded quota`, `OOMKilled`, `CrashLoopBackOff`.
- HPA vẫn hoạt động và không bị kẹt ở max replicas trong steady state.
- Checkout error rate không tăng sau rollout.
- `checkout -> CurrencyService.Convert` p95 giảm xuống dưới timeout budget hoặc ít nhất không còn deadline-exceeded spike trong official observation window.
- Nếu vẫn còn timeout, CDO08 mở follow-up để review:
  - tăng `currency` HPA `maxReplicas` từ `3` lên `4`; hoặc
  - điều chỉnh checkout currency timeout sau khi CDO04 xác nhận capacity.

## 7. Rollback

Rollback bằng GitOps revert về:

```yaml
resources:
  requests: { cpu: 75m, memory: 96Mi }
  limits: { cpu: 300m, memory: 192Mi }
```

Sau rollback cần verify:

```bash
kubectl -n techx-tf4 rollout status deploy/currency --timeout=180s
kubectl -n techx-tf4 describe hpa currency
```

Không rollback bằng live patch trừ khi đang trong incident và có incident commander approve.

## 8. Câu hỏi cần CDO04 duyệt

| Question | CDO04 decision |
|---|---|
| Có approve `currency` CPU request `150m` không? | Pending |
| Có approve `currency` CPU limit `750m` không? | Pending |
| Có giữ HPA max `3` cho phase này không? | Pending |
| Nếu vẫn timeout sau rollout, CDO04 có đồng ý mở phase 2 tăng HPA max `4` không? | Pending |
| ResourceQuota hiện tại có đủ cho proposed limit delta `+1350m` ở max HPA không? | Pending |
