# CDO7 Static Audit Scan - phase3

Phạm vi: scan tĩnh cho team CDO7 (audit) trên repository hiện tại, dựa theo format template `cdo08_scan.md`. Báo cáo này được tổ chức theo cột audit/trụ audit trước, sau đó mới đến finding và evidence. Báo cáo chỉ dùng bằng chứng trong repository; các finding runtime như trạng thái pod, PVC thực tế, quyền RBAC bị từ chối, hoặc service public exposure cần được xác nhận thêm bằng `kubectl` trên namespace deploy.

## Tổng hợp theo trụ audit

| Trụ audit | Số finding | Priority chính | Ghi chú |
| :--- | :--- | :--- | :--- |
| Reliability | 8 | P1/P2 | Chủ yếu nằm ở replica, health probe, persistence, checkout consistency và Kafka ack |
| Security | 6 | P1/P2 | Chủ yếu nằm ở secret handling, anonymous admin, OpenSearch security, NetworkPolicy và insecure gRPC |
| Operational Excellence | 1 | P2 | Supply-chain/Dockerfile hardening |
| Evidence | 1 | P2 | Thiếu bằng chứng runtime/RBAC để hoàn tất audit |

## Bảng finding theo cột audit

| ID | Trụ audit | Finding | Evidence | Priority gợi ý |
| :--- | :--- | :--- | :--- | :--- |
| REL-01 | Reliability | Default app deployment chỉ có `1` replica, nhiều dependency quan trọng cũng single replica | `techx-corp-chart/values.yaml:28` đặt default `replicas: 1`; `flagd` `replicas: 1` ở `values.yaml:715`, `kafka` ở `values.yaml:787`, `postgresql` ở `values.yaml:837`, `valkey-cart` ở `values.yaml:888`; template dùng `.replicas \| default .defaultValues.replicas` tại `techx-corp-chart/templates/_objects.tpl:13` | P1 |
| REL-02 | Reliability | App pods chưa cấu hình readiness/liveness probe mặc định | Probe chỉ là option/comment trong values tại `techx-corp-chart/values.yaml:153-154`; template chỉ render khi `.livenessProbe`/`.readinessProbe` có giá trị tại `techx-corp-chart/templates/_objects.tpl:73-79` | P1 |
| REL-03 | Reliability | Chưa có HPA/PDB/topology spread cho workload app | Component chart chỉ include deployment/service/ingress/configmap tại `techx-corp-chart/templates/component.yaml:11-14`; lệnh `rg -n "HorizontalPodAutoscaler|PodDisruptionBudget|topologySpreadConstraints|autoscaling" techx-corp-chart deploy` không tìm thấy manifest tương ứng | P1/P2 |
| REL-04 | Reliability | PostgreSQL, Valkey, Kafka chưa thấy cấu hình PVC/persistence trong component chart | PostgreSQL chỉ mount init ConfigMap tại `techx-corp-chart/values.yaml:873-876`; Valkey chỉ khai báo port/resource tại `values.yaml:888-901`; Kafka khai báo single broker/listener tại `values.yaml:787-810`; template chỉ render `emptyDir`, ConfigMap và `additionalVolumes`, không có PVC kind tại `techx-corp-chart/templates/_objects.tpl:143-157` | P1 |
| REL-05 | Reliability / Observability | Observability data và alerting chưa sẵn sàng cho incident/forensics dài hạn | Prometheus Alertmanager disabled tại `techx-corp-chart/values.yaml:1119-1120`; Prometheus PV disabled tại `values.yaml:1173-1174`; Jaeger dùng memory backend tại `values.yaml:1040`; OpenSearch `singleNode: true` và `persistence.enabled: false` tại `values.yaml:1219-1222` | P1 |
| REL-06 | Reliability | Checkout có side effect không atomic: charge/shipping/cart/email xong mới publish event | `chargeCard` tại `techx-corp-platform/src/checkout/main.go:329`, `shipOrder` tại `main.go:342`, ignore lỗi empty cart tại `main.go:349`, send confirmation tại `main.go:379`, publish postProcessor sau cùng tại `main.go:388` | P1 |
| REL-07 | Reliability | Kafka producer có nguy cơ mất event vì không đợi broker ack và async error chỉ log | `saramaConfig.Producer.RequiredAcks = sarama.NoResponse` tại `techx-corp-platform/src/checkout/kafka/producer.go:41`; errors được đọc/log trong goroutine tại `producer.go:55`; checkout gửi async qua `KafkaProducerClient.Input()` tại `techx-corp-platform/src/checkout/main.go:630` | P1/P2 |
| REL-08 | Reliability / Cost | Nhiều service chỉ có memory limit, thiếu CPU/request nên scheduler và autoscaling khó dự đoán | Lệnh `rg -n "requests:|limits:|memory:|cpu:" techx-corp-chart/values.yaml deploy` cho thấy gần như toàn bộ app component chỉ khai báo `limits.memory`; CPU chỉ xuất hiện cho Grafana sidecar tại `techx-corp-chart/values.yaml:1207-1209`; quota có requests/limits namespace tại `deploy/quota.yaml:6-9` nhưng app pod không set requests | P2 |
| SEC-01 | Security | Hardcoded credentials/API keys/secret material trong Helm values | DB connection string có password tại `techx-corp-chart/values.yaml:183`, `values.yaml:582-583`, `values.yaml:619-620`; `OPENAI_API_KEY` dummy tại `values.yaml:601`; `SECRET_KEY_BASE` tại `values.yaml:759`; `POSTGRES_PASSWORD` tại `values.yaml:869`; override tốt hơn đã dùng Secret tại `deploy/values-aio-llm.yaml:2,10-11` | P1 |
| SEC-02 | Security | Grafana anonymous Admin và admin password mặc định | `auth.anonymous.enabled: true` và `org_role: Admin` tại `techx-corp-chart/values.yaml:1189-1192`; `adminPassword: admin` tại `values.yaml:1196` | P1, P0 nếu expose public |
| SEC-03 | Security | OpenSearch security plugin bị disable | `DISABLE_SECURITY_PLUGIN` tại `techx-corp-chart/values.yaml:1228` và giá trị `true` ở dòng liền kề; OpenSearch cũng `singleNode: true`/persistence off tại `values.yaml:1219-1222` | P1/P2 |
| SEC-04 | Security | Default container security context rỗng, chỉ một số service có `runAsNonRoot` | `default.securityContext: {}` tại `techx-corp-chart/values.yaml:37`; chỉ một số service có `runAsNonRoot` tại `values.yaml:410,472,563,658,814,905`; template render securityContext nếu có cấu hình tại `techx-corp-chart/templates/_objects.tpl:50,70` | P2 |
| SEC-05 | Security | Chưa thấy NetworkPolicy; OTel receiver CORS mở wildcard | Lệnh `rg -n "NetworkPolicy" techx-corp-chart deploy` không tìm thấy manifest; OTLP HTTP CORS cho `http://*` và `https://*` tại `techx-corp-chart/values.yaml:941-943` | P2 |
| SEC-06 | Security | Inter-service gRPC dùng insecure transport credential | Checkout tạo gRPC client bằng `grpc.WithTransportCredentials(insecure.NewCredentials())` tại `techx-corp-platform/src/checkout/main.go:444` | P2 |
| OPS-01 | Operational Excellence / Security | Supply-chain hardening chưa chặt: image `latest`/remote artifact download trong Dockerfile | `frontend-proxy` dùng `envoyproxy/envoy:v1.34-latest` tại `techx-corp-platform/src/frontend-proxy/Dockerfile:4`; Java agent được `ADD` từ GitHub trong `ad`, `fraud-detection`, `kafka` Dockerfile tại `src/ad/Dockerfile:31`, `src/fraud-detection/Dockerfile:21`, `src/kafka/Dockerfile:12`; không thấy checksum verification trong các dòng scan | P2 |
| EVD-01 | Evidence | Repo chưa có bằng chứng runtime cho status namespace/CDO7 audit RBAC | Static repo có ServiceAccount template tại `techx-corp-chart/templates/serviceaccount.yaml`; lệnh `rg -n "kind: (Role|RoleBinding|ClusterRole|ClusterRoleBinding)" techx-corp-chart deploy` không thấy RBAC manifest; cần bổ sung output `kubectl auth can-i`, `kubectl get deploy/pod/pvc/events` theo namespace thực tế | P2 |

## Nguồn tham chiếu đã dùng

- Template đầu vào: `cdo08_scan.md`
- Helm chart chính: `techx-corp-chart/values.yaml`, `techx-corp-chart/templates/component.yaml`, `techx-corp-chart/templates/_objects.tpl`, `techx-corp-chart/templates/_pod.tpl`, `techx-corp-chart/templates/serviceaccount.yaml`
- Deploy overrides/manifests: `deploy/values-observability.yaml`, `deploy/values-aio-llm.yaml`, `deploy/quota.yaml`
- Checkout flow: `techx-corp-platform/src/checkout/main.go`, `techx-corp-platform/src/checkout/kafka/producer.go`
- Supply-chain/Dockerfile evidence: `techx-corp-platform/src/frontend-proxy/Dockerfile`, `techx-corp-platform/src/ad/Dockerfile`, `techx-corp-platform/src/fraud-detection/Dockerfile`, `techx-corp-platform/src/kafka/Dockerfile`
- Repo inventory: output từ `rg --files`
- Negative evidence: các lệnh `rg` không tìm thấy `HorizontalPodAutoscaler`, `PodDisruptionBudget`, `topologySpreadConstraints`, `autoscaling`, `NetworkPolicy`, `Role`, `RoleBinding`, `ClusterRole`, `ClusterRoleBinding` trong `techx-corp-chart` và `deploy`

## Runtime checks cần chạy thêm

```powershell
kubectl -n <namespace> get deploy,pod,svc,pvc,events
kubectl -n <namespace> get hpa,pdb,networkpolicy
kubectl -n <namespace> get sa,role,rolebinding
kubectl auth can-i --list -n <namespace>
kubectl -n <namespace> get deploy -o jsonpath="{range .items[*]}{.metadata.name}{': replicas='}{.spec.replicas}{' ready='}{.status.readyReplicas}{' probes='}{.spec.template.spec.containers[*].readinessProbe}{' / '}{.spec.template.spec.containers[*].livenessProbe}{'\n'}{end}"
```
