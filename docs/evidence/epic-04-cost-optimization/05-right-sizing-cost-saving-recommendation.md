# COST-05: Khuyến nghị right-sizing và cost saving

Ngày rà soát: 2026-07-10

## 1. Mục tiêu

Tài liệu này đối chiếu recommendation với implementation hiện có trong repository. Mỗi action được phân loại rõ là đã implement, chưa implement hoặc chỉ được phép thực hiện khi có thêm runtime evidence.

Nguồn chính:

- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`
- `docs/evidence/epic-04-cost-optimization/06-cost-quick-wins.md`
- `docs/evidence/epic-03-performance-efficiency/04-runtime-performance-evidence.md`
- `docs/evidence/epic-03-performance-efficiency/runtime/`
- `techx-corp-chart/values.yaml`
- `deploy/values-app-stamp.yaml`
- `deploy/values-observability.yaml`
- `infra/terraform/eks.tf`
- `infra/terraform/ecr.tf`
- `.github/workflows/deploy.yaml`

Nguyên tắc: không giảm CPU, memory hoặc node capacity khi workload còn `OOMKilled`, restart bất thường hoặc chưa có dữ liệu đủ dài. Cost estimate cũng không được mô tả như actual billing khi chưa đối chiếu Cost Explorer.

## 2. Kết quả kiểm tra implementation

### 2.1. Kiến trúc deploy và node group

Workflow deploy tách hai Helm release:

- Application release `techx-corp` trong namespace `techx-tf4`.
- Observability release `techx-observability` trong namespace `techx-observability`.

`infra/terraform/eks.tf:32-40` cấu hình managed node group:

- `min_size=2`
- `desired_size=2`
- `max_size=4`
- instance type `t3.large`
- capacity type `ON_DEMAND`

Repository không cài Cluster Autoscaler hoặc Karpenter. Vì vậy `max_size=4` chỉ là giới hạn của Auto Scaling Group. Cấu hình này không chứng minh cluster sẽ tự tăng từ 2 lên 4 node khi pod bị `Pending`. Việc tăng node hiện chỉ xảy ra khi có thao tác bên ngoài repository hoặc thay đổi desired capacity.

Runtime evidence ghi nhận 2 node ở `us-east-1a` và `us-east-1b`. Đây là node placement đa AZ ở thời điểm chụp, không phải full HA. Application vẫn chủ yếu chạy một replica và chart chưa có topology spread hoặc pod anti-affinity mặc định.

### 2.2. Load generator

Implementation hiện tại:

- `load-generator` được bật tại `techx-corp-chart/values.yaml:498-500`.
- `LOCUST_AUTOSTART=true` tại `values.yaml:519-520`.
- Memory limit là `1500Mi` tại `values.yaml:533-535`.
- Local Compose path cũng có `LOCUST_AUTOSTART=true` tại `techx-corp-platform/.env:104`.
- `deploy/values-app-stamp.yaml` không override các giá trị này.

Vì vậy action tắt autostart chưa được implement trong source of truth của EKS hoặc local Compose.

Load generator gọi `http://frontend-proxy:8080` trong cluster. Traffic này không đi qua public ALB theo flow mặc định, nên không nên claim nó trực tiếp làm tăng ALB LCU. Nó cũng không mặc định đi qua NAT Gateway. Tác động đã có cơ sở là:

- Tăng CPU và memory của application pods.
- Tăng request, log và trace volume.
- Tăng áp lực cho Jaeger, Prometheus, OpenSearch, Grafana và OTel Collector.
- Làm sai lệch baseline của user traffic.
- Có thể tạo thêm node pressure, nhưng repository chưa có node autoscaler để tự scale theo áp lực đó.

### 2.3. Observability

Cấu hình hiện tại trong `values.yaml`:

| Component | Cấu hình chính | Kết luận |
|---|---|---|
| Jaeger | memory limit `600Mi`, in-memory storage, `MEMORY_MAX_TRACES=25000` | Screenshot xác nhận `OOMKilled=True`, restart count `1`; không giảm memory khi chưa xác định nguyên nhân và peak usage |
| Prometheus | memory limit `400Mi`, retention `7d`, persistent volume tắt | Retention đã được cấu hình, nhưng dữ liệu mất khi pod/storage tạm thời bị thay thế |
| Grafana | memory limit `300Mi`; runtime evidence ghi request/limit `300Mi` | Đã có bằng chứng `OOMKilled`, exit `137`, restart count `7`; không giảm |
| OpenSearch | heap `400m`, memory limit `1100Mi`, persistence tắt | Không giảm khi chưa đo heap, index size và peak memory |
| OTel Collector | DaemonSet, memory limit `200Mi` | Chi phí tăng theo số node; cần tính theo DaemonSet replica count |

Bằng chứng raw cho Grafana nằm tại:

`docs/evidence/epic-03-performance-efficiency/runtime/grafana/grafana-resource-evidence-2026-07-09.md`

Screenshot `docs/evidence/epic-04-cost-optimization/runtime/screenshots/Jaeger overkill.jpg` xác nhận container Jaeger từng có `OOMKilled=True` và restart count `1` ở memory limit `600Mi`. Đây là bằng chứng cho ít nhất một sự cố OOM lịch sử. Snapshot `runtime/jaeger/http-check-2026-07-09.md:21-25` cho thấy pod Jaeger sau đó đang `Running` với restart count `0`; nhiều khả năng đây là pod hoặc container instance mới, nên hai bằng chứng không mâu thuẫn. Screenshot chưa thể hiện đầy đủ timestamp, pod/container ID, peak memory hoặc traffic correlation. Vì vậy OOM được xem là đã xác nhận, còn nguyên nhân và mức memory phù hợp vẫn cần điều tra.

Namespace inventory không thấy PVC. Điều này khớp với Prometheus và OpenSearch persistence đang tắt, còn Jaeger dùng in-memory storage. Storage cost thấp nhưng restart có thể làm mất metrics, logs hoặc traces.

### 2.4. ECR lifecycle

Action thêm ECR lifecycle policy đã được implement tại `infra/terraform/ecr.tf:17-51`:

- Xóa untagged image sau 7 ngày.
- Giữ tối đa 30 tagged image gần nhất.

Vì vậy tài liệu không nên tiếp tục ghi "Add ECR lifecycle policy" như một action chưa làm.

Policy hiện tại vẫn cần hardening. Rule `tagStatus: any` có thể expire tagged image cũ, kể cả release tag cần rollback. Cần kiểm tra lifecycle preview và thay rule chung bằng tag prefixes hoặc retention policy phân biệt release, environment và development image.

### 2.5. CloudWatch Logs retention

Runtime inventory ghi nhận 8 log groups. Một số group có retention, một số group để `Not set`.

Repository không có `aws_cloudwatch_log_group` hoặc `retention_in_days` để quản lý các non-critical log group đó. EKS control plane log group hiện được quan sát với retention 90 ngày, nhưng các `/ec2/cloudwatch-agent/...` group có thể thuộc workload hoặc môi trường khác. Không được thay retention hàng loạt trước khi xác nhận ownership, compliance và nguồn tạo log.

Action này chưa được implement trong Terraform hiện tại.

### 2.6. ResourceQuota

`deploy/quota.yaml` là manifest mẫu/manual, không được apply trong `.github/workflows/deploy.yaml`. Workflow cũng không tạo `LimitRange`.

Nếu quota được apply vào namespace `techx-tf4`, các pod thiếu CPU request/limit có thể bị admission từ chối. Observability chạy ở namespace khác nên cần quota riêng nếu team muốn kiểm soát cả hai release.

Do đó, việc giữ hoặc giảm node capacity phải đi cùng:

- Tổng resource request/limit của từng namespace.
- Server-side dry-run với quota.
- Node allocatable và headroom trong baseline lẫn controlled load test.

## 3. Baseline cost và giới hạn của estimate

Số liệu từ COST-01:

| Kịch bản | Monthly estimate | Weekly estimate | Trạng thái |
|---|---:|---:|---|
| Fixed baseline hiện tại | `$246.95/month` | `$56.83/week` | Estimate, chưa phải actual bill |
| Fixed baseline và trung bình 1 ALB LCU | `$252.79/month` | `$58.18/week` | Scenario, ALB LCU thực tế chưa được đo |
| 4 node theo mô hình cũ | `$368.42/month` | `$84.79/week` | Đang giữ EBS ở 40 GiB nên chưa tính đủ 4 root volume |
| 4 node với 4 x 20 GiB gp3 | khoảng `$371.62/month` | khoảng `$85.53/week` | Scenario điều chỉnh nếu cả 4 node cùng chạy đủ tháng |

Estimate chưa gồm đầy đủ:

- NAT data processing.
- ALB LCU thực tế.
- ECR storage thực tế.
- CloudWatch ingestion và storage thực tế.
- Data transfer, kể cả cross-AZ.
- Tax, credit, discount hoặc Savings Plans.

Budget target cũng chưa thống nhất giữa `$300/week` trong một số tài liệu và AWS Budget `$300/month` đã được khai báo tại `infra/terraform/variables.tf:90-99` và `infra/terraform/budgets.tf:2-18`. Theo guardrail hiện tại, baseline `$246.95/month` thấp hơn budget khoảng `$53.05/month`, nhưng scenario cũ `$368.42/month` vượt khoảng `$68.42/month`, còn scenario đã điều chỉnh `$371.62/month` vượt khoảng `$71.62/month`. Không được dùng phép so sánh với `$300/week` để chứng minh tuân thủ AWS Budget đang implement.

## 4. Recommendation summary

| Ưu tiên | Recommendation | Trạng thái implementation | Quyết định |
|---|---|---|---|
| P0 | Đặt `LOCUST_AUTOSTART=false` cho EKS và local Compose | Chưa implement | Làm ngay, sau đó redeploy và verify |
| P0 | Không giảm Grafana memory | Có runtime OOM evidence | Giữ hoặc thử tăng có kiểm soát |
| P0 | Điều tra Jaeger sau OOM | Screenshot xác nhận `OOMKilled=True`, restart count `1` | Giữ memory, bổ sung timestamp, peak usage và traffic correlation trước khi đổi |
| P0 | Xử lý `accounting` OOM/restart trước khi cost cut | Chưa hoàn tất | Làm trước right-sizing |
| P1 | Giữ 2 x `t3.large` trong cửa sổ Week 1 | Đang implement | Giữ cho đến khi có 48 đến 72 giờ metrics |
| P1 | Chuẩn hóa Prometheus/Grafana metrics | Đang có dashboard, thiếu long-window dataset | Hoàn thiện trước compute right-sizing |
| P1 | Quản lý CloudWatch retention theo ownership | Chưa implement | Làm sau khi owner xác nhận |
| P1 | Harden ECR lifecycle policy | Policy đã có nhưng chưa bảo vệ release tags rõ ràng | Review lifecycle preview và sửa rule |
| P2 | Đổi instance type hoặc giảm max size | Chưa được chứng minh an toàn | Chỉ thử sau controlled load test |
| P2 | Node autoscaling | Chưa implement | Cần Cluster Autoscaler hoặc Karpenter nếu muốn tự scale |

## 5. Hành động đề xuất

### 5.1. Tắt load-generator autostart

Thay đổi cần làm:

```text
techx-corp-chart/values.yaml:
LOCUST_AUTOSTART=true -> false

techx-corp-platform/.env:
LOCUST_AUTOSTART=true -> false
```

Nếu team cần khác nhau theo environment, nên đưa giá trị này vào một environment-specific values file thay vì sửa tay trước mỗi lần test.

Validation:

- Rendered app manifest có `LOCUST_AUTOSTART=false`.
- Sau redeploy, Locust không tự tạo user load.
- Request rate và trace volume giảm về traffic thực hoặc planned test.
- Khi chạy test, bật thủ công, ghi lại start/end time rồi tắt sau test.

Rollback chỉ dùng cho planned load test, không bật lại làm baseline mặc định.

### 5.2. Giữ 2 node trong giai đoạn hiện tại

Giữ `min=2`, `desired=2` trong Week 1 vì:

- Runtime còn OOM và restart history.
- Application và observability dùng chung node group.
- Chưa có 48 đến 72 giờ CPU/memory trend đủ sạch sau khi tắt synthetic traffic.
- Hai node đã được quan sát ở hai AZ, dù application chưa đạt full HA.

Chưa thực hiện:

- Không giảm về 1 node nếu chưa chấp nhận downtime và mất redundancy ở node layer.
- Không chuyển sang `t3.medium` khi chưa cộng tổng memory request/working set của cả hai namespace.
- Không tăng `max_size` vượt 4 khi chưa có budget approval.
- Không mô tả `max_size=4` là autoscaling đã hoạt động khi chưa có Cluster Autoscaler hoặc Karpenter.

### 5.3. Giữ observability ổn định

- Grafana: không giảm. Có thể thử request `512Mi`, limit `768Mi`, sau đó kiểm tra 24 giờ.
- Jaeger: không giảm dưới `600Mi` vì screenshot đã xác nhận một lần `OOMKilled`. Cần bổ sung timestamp, peak usage và traffic correlation. Có thể giảm trace volume bằng sampling hoặc `MEMORY_MAX_TRACES` trước khi chỉ tăng memory.
- Prometheus: giữ `400Mi`; retention đã là `7d`, nhưng persistence đang tắt.
- OpenSearch: giữ `1100Mi`; cần theo dõi heap, index growth và log retention.
- OTel Collector: theo dõi memory theo từng DaemonSet pod và nhân với số node khi lập capacity model.

Acceptance criteria trước khi thay đổi memory:

- Không có `OOMKilled` mới.
- Restart count không tăng.
- Grafana và Jaeger route vẫn trả `HTTP 200`.
- Metrics, traces và logs vẫn có dữ liệu trong test window.

### 5.4. Quản lý CloudWatch retention

Trước khi tạo Terraform resource:

1. Xác nhận từng log group thuộc cluster hoặc workload nào.
2. Phân loại audit/security, application troubleshooting và temporary/test logs.
3. Chọn retention theo compliance và nhu cầu điều tra.
4. Import resource hiện có vào Terraform nếu Terraform sẽ quản lý chúng.
5. Chạy plan và kiểm tra không xóa hoặc recreate nhầm log group.

Gợi ý ban đầu:

| Loại log | Retention tham khảo |
|---|---:|
| Temporary/test | 1 đến 7 ngày |
| Application troubleshooting | 14 đến 30 ngày |
| Audit/security | Theo compliance requirement |
| EKS control plane | Giữ policy hiện tại cho đến khi owner phê duyệt |

### 5.5. Harden ECR lifecycle

Policy đã tồn tại, nên action tiếp theo là review chứ không phải tạo mới.

Validation:

- Dùng `aws ecr get-lifecycle-policy` để xác minh policy đã được apply, thay vì chỉ dựa vào Terraform declaration.
- Chạy lifecycle preview.
- Xác nhận rollback tags không bị expire.
- Xác nhận production release tags được bảo vệ.
- Chỉ expire untagged và development images theo policy đã thống nhất.

### 5.6. Compute right-sizing có điều kiện

Chỉ thử đổi instance type hoặc node count khi:

- `LOCUST_AUTOSTART=false` đã được deploy.
- Có 48 đến 72 giờ metrics cho app và observability.
- `accounting` và Grafana không còn OOM mới.
- Có tổng request/limit và working set theo từng namespace.
- Controlled load test đạt p95/p99, error rate và checkout success target.
- ResourceQuota server-side dry-run thành công.

Rollback nếu latency, error rate, restart, `OOMKilled` hoặc pending pod tăng.

## 6. Không thực hiện trong cycle này

| Thay đổi | Lý do |
|---|---|
| Giảm Grafana memory | Có bằng chứng `OOMKilled`, exit `137` |
| Giảm Jaeger theo giả định usage thấp | Screenshot đã xác nhận một lần `OOMKilled`; nguyên nhân và traffic correlation chưa rõ |
| Giảm Prometheus/OpenSearch memory | Chưa có long-window evidence; persistence đang tắt |
| Chuyển ngay từ `t3.large` sang instance nhỏ hơn | Chưa có node/pod headroom đầy đủ |
| Giảm node count mặc định từ 2 xuống 1 | Giảm node-layer redundancy và capacity |
| Xóa NAT Gateway hoặc ALB | Cần architecture change và traffic analysis riêng |
| Xem max size 4 là active autoscaling | Repository chưa có Cluster Autoscaler hoặc Karpenter |
| Tạo thêm ECR lifecycle policy | Policy đã tồn tại; cần harden policy hiện tại |
| Xem estimate là actual bill | Chưa có Cost Explorer actual data |

## 7. Kế hoạch triển khai

### Giai đoạn 1: safe changes

1. Đặt `LOCUST_AUTOSTART=false` trong chart và local `.env`.
2. Redeploy và kiểm tra request/trace volume.
3. Giữ node group ở 2 x `t3.large`.
4. Xử lý `accounting` và Grafana OOM/restart.
5. Bổ sung metadata cho Jaeger OOM evidence: timestamp, pod/container ID, peak usage và traffic correlation.
6. Review ECR lifecycle preview.

### Giai đoạn 2: evidence window

1. Thu CPU/memory trong 48 đến 72 giờ cho cả hai namespace.
2. Theo dõi restart và `OOMKilled` theo pod/container.
3. Chạy controlled load test có start/end time rõ ràng.
4. Đối chiếu Cost Explorer với estimate.
5. Xác nhận log group ownership và retention policy.

### Giai đoạn 3: conditional optimization

1. Thử instance type nhỏ hơn trong controlled window nếu headroom cho phép.
2. Kiểm tra lại chi phí EBS nếu node count thay đổi.
3. Đánh giá giảm `max_size` sau peak load test.
4. Chỉ bổ sung node autoscaler khi có nhu cầu scale theo pending pods và có capacity/budget guardrail.

## 8. Trạng thái

| Hạng mục | Trạng thái |
|---|---|
| Cost baseline | Đã có estimate; chưa đối chiếu actual bill |
| Load-generator autostart | Chưa tắt trong source config |
| Node group 2 x `t3.large` | Đã implement |
| ECR lifecycle | Đã implement; cần bảo vệ release tags rõ ràng hơn |
| CloudWatch retention cho non-critical groups | Chưa được quản lý trong Terraform |
| Observability right-sizing | Chưa đủ evidence; Grafana không được giảm |
| Compute right-sizing | Chưa được phê duyệt |
| Node autoscaling | Chưa được implement |

COST-05 chỉ hoàn tất khi recommendation được chuyển thành config change, có rendered output, rollout evidence, số liệu trước/sau và rollback result nếu validation không đạt.
