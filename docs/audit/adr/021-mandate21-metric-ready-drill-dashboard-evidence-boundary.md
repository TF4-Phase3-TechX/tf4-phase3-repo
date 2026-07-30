# ADR-021: Mandate 21 Metric-Ready Dashboard và ranh giới evidence live/external

- **Ngày:** 2026-07-30
- **Trạng thái:** Accepted - source implemented, runtime verification sau GitOps sync
- **Tác giả:** Trần Minh Quang - CDO07
- **Người review:** CDO08, TF4 leads
- **Pillar liên quan:** Reliability, Observability, Auditability
- **Mandate:** Mandate 21 - DR Failover / Single-AZ Loss Drill
- **Source file:** `techx-corp-chart/grafana/provisioning/dashboards/mandate21-az-loss-drill-dashboard.json`

## 1. Bối cảnh

CDO07 hỗ trợ CDO08 cho Mandate 21 - DR Failover / Single-AZ Loss Drill. Mục tiêu là tạo dashboard Grafana phục vụ drill và trình bày evidence, nhưng các panel live chỉ được dựa trên metric thật đang có trong Prometheus.

Dashboard cũ `Single-AZ Loss Drill (Mandate 21)` có nhiều panel không đủ tin cậy để làm evidence độc lập:

- `Active Load Generator Users` dùng `vector(200)`, là số tĩnh và có thể gây hiểu nhầm là live metric.
- HPA query `kube_horizontalpodautoscaler_*` nhưng không có data trong Prometheus.
- Node Ready/AZ placement thiếu metric/label để chứng minh pod/node trải AZ.
- RDS, Valkey và Kafka/MSK panels dùng metric chưa tồn tại hoặc không chứng minh được failover/RPO.
- Checkout request count bị đặt tên như RPO evidence, trong khi request count không chứng minh confirmed/persisted orders.

CDO08 xác nhận hướng tiếp cận đúng là tách dashboard thành hai nhóm evidence:

- **Live panels:** chỉ dùng metric Prometheus thật có data.
- **Pending / External Evidence panels:** các bằng chứng chưa có metric live phải ghi rõ nguồn sẽ lấy từ kubectl, AWS CLI/Console, observer log hoặc reconciliation script/query.

## 2. Quyết định

Tạo dashboard mới riêng cho Mandate 21 thay vì sửa trực tiếp dashboard cũ.

Dashboard mới:

- Title: `Mandate 21 AZ Loss Drill Dashboard`
- UID: `mandate21-az-loss-drill`
- Tags: `techx`, `mandate21`, `metric-ready`, `cdo07`
- File: `techx-corp-chart/grafana/provisioning/dashboards/mandate21-az-loss-drill-dashboard.json`
- ConfigMap render expected: `grafana-dashboard-mandate21-az-loss-drill-dashboard`

Nguyên tắc thiết kế:

1. Live panels chỉ dùng metric Prometheus thật đã có.
2. Không dùng static vector như `vector(200)` để giả lập live evidence.
3. Không fallback về `0` cho metric chưa tồn tại, vì `0` có thể bị hiểu nhầm là kết quả đo thật.
4. Các bằng chứng chưa có metric live phải hiển thị là `Pending / External Evidence`.
5. Dashboard chỉ là Phase 1 metric-ready dashboard, không claim là bằng chứng đầy đủ độc lập cho toàn bộ Mandate 21.
6. GitOps deployment phải bump immutable chart source SHA sau khi source repo merge.

Live panels được chấp nhận gồm các nhóm:

- Request rate/success/error/latency cho browse, cart và checkout dựa trên `traces_span_metrics_*`.
- Kubernetes availability/runtime health dựa trên `k8s_deployment_available`, `k8s_pod_phase`, `k8s_container_restarts`.
- Node resource telemetry dựa trên `k8s_node_cpu_usage`, `k8s_node_memory_working_set_bytes`, `k8s_node_memory_available_bytes`.
- Active alert snapshot dựa trên `ALERTS`.

Pending / External Evidence panels gồm:

- Active users / HPA evidence.
- AZ placement evidence.
- Managed data evidence cho RDS, Valkey, MSK/Kafka.
- Order reconciliation / RTO evidence.

## 3. Lý do

| Lý do | Giải thích |
|---|---|
| Evidence trung thực | Dashboard không được làm đẹp số liệu bằng static value hoặc fallback 0 cho metric chưa tồn tại. |
| Giảm hiểu nhầm | Tách live metric và external evidence giúp người xem biết phần nào là metric runtime, phần nào cần evidence bổ sung. |
| Rollback an toàn | Tạo dashboard mới, UID mới và ConfigMap mới giúp rollback bằng cách revert/xóa file mà không phá dashboard cũ. |
| Đúng ownership | CDO07 sở hữu observability/evidence semantics; CDO08 cung cấp HPA, AZ, managed data và reconciliation evidence ngoài Grafana. |
| Phù hợp GitOps | Production chỉ nên nhận chart source SHA đã được pin và review trong GitOps repo. |

## 4. Hệ quả

### Tích cực

- Dashboard phân biệt rõ live metric và pending/external evidence.
- Giảm nguy cơ dùng nhầm panel `No data` hoặc static number làm bằng chứng drill.
- Có thể trình bày sớm phần metric-ready trong khi CDO08 bổ sung evidence ngoài Grafana.
- Rollback đơn giản vì dashboard mới không thay đổi dashboard cũ.

### Trade-off / Giới hạn

- Dashboard không thay thế HPA snapshot, AZ mapping, RDS writer failover, Valkey/MSK evidence, reconciliation script hay observer log.
- Một số bằng chứng quan trọng của Mandate 21 vẫn nằm ngoài Grafana cho đến khi instrumentation/metric được bổ sung.
- Cần GitOps promotion để ArgoCD load chart source SHA mới; merge source repo chưa đồng nghĩa dashboard xuất hiện ngay trên Grafana.

## 5. Phương án đã xem xét

| Phương án | Kết luận | Lý do |
|---|---|---|
| Sửa dashboard cũ | Không chọn | Tăng rủi ro rollback và có thể làm người xem tiếp tục tin vào panel cũ. |
| Dùng static vector/fallback 0 | Không chọn | Tạo evidence giả hoặc gây hiểu nhầm là metric live. |
| Chờ đủ tất cả metric mới tạo dashboard | Không chọn | Không đáp ứng nhu cầu drill/presentation ngắn hạn; có thể tách live/pending rõ ràng hơn. |
| Tạo dashboard mới metric-ready | Chọn | Trung thực với dữ liệu đang có, vẫn cho phép trình bày phần live evidence. |

## 6. Validation

Validation source đã thực hiện trước khi merge:

- JSON parse pass bằng `ConvertFrom-Json`.
- `helm lint techx-corp-chart` pass.
- `helm template techx techx-corp-chart --namespace techx-tf4` pass.
- Render ra ConfigMap `grafana-dashboard-mandate21-az-loss-drill-dashboard`.
- Không còn query các metric thiếu như HPA/RDS/Valkey/MSK.
- Không còn `vector(200)` hoặc fallback `0` cho missing metric.

Validation sau GitOps sync:

```powershell
kubectl get cm -n techx-observability grafana-dashboard-mandate21-az-loss-drill-dashboard
```

Nếu ConfigMap tồn tại, Grafana sidecar/provisioning sẽ load dashboard sau khoảng 30-60 giây.

## 7. Rollback

Rollback source:

- Revert commit/PR tạo dashboard Mandate 21, hoặc xóa file:
  `techx-corp-chart/grafana/provisioning/dashboards/mandate21-az-loss-drill-dashboard.json`

Rollback GitOps/runtime:

- Revert GitOps promotion PR hoặc đưa `targetRevision` về chart source SHA trước đó.
- Nếu đã apply bằng Helm thủ công, dùng `helm rollback` về revision trước.

Fallback evidence:

- Dashboard cũ `Single-AZ Loss Drill (Mandate 21)`.
- `OTel SLO dashboard`.
- `Business Flow Health Overview`.
- Grafana Explore PromQL.
- Locust UI screenshot.
- `kubectl` output.
- AWS CLI/Console evidence.
- Observer log và reconciliation script/query.

## 8. References

- PR #754: `feat(cdo07): add mandate21 metric-ready dashboard`
- Commit `146ffd6`: `feat(cdo07): add mandate21 metric-ready dashboard`
- GitOps file: `argocd/root-resources/applications.yaml`
- Source dashboard: `techx-corp-chart/grafana/provisioning/dashboards/mandate21-az-loss-drill-dashboard.json`
- Related ADR: `docs/audit/adr/015-business-flow-grafana-dashboards.md`
