# Kế hoạch khoanh vùng ServiceAccount và RBAC - CDO08-SEC-22

## 1. Thông tin chung

- Task: `[CDO08-SEC-22][P0][RBAC] Enforce per-service ServiceAccount and least-privilege Kubernetes API access`
- Owner chính: Nhân
- Phạm vi ứng dụng: namespace `techx-tf4`
- Phạm vi quan sát hệ thống: namespace `techx-observability`
- Helm chart đã kiểm tra: `techx-corp` phiên bản `0.40.9`
- Commit `main` dùng để render manifest: `133e276`
- Ngày kiểm tra: 22/07/2026

Tài liệu này chỉ kiểm tra tên workload, ServiceAccount, chính sách mount token và cấu hình RBAC. Không đọc và không cần đọc giá trị của Secret.

## 2. Giải thích ngắn gọn

- **ServiceAccount** là danh tính của pod khi làm việc với Kubernetes.
- **Token của ServiceAccount** là thông tin xác thực để pod gọi Kubernetes API.
- **RBAC** quy định ServiceAccount được phép làm gì, ví dụ đọc Pod hoặc xem ConfigMap.
- **Automount token** nghĩa là Kubernetes tự đưa token vào pod. Nếu service không cần gọi Kubernetes API thì nên tắt để giảm rủi ro khi pod bị chiếm.
- **Desired state** là cấu hình mong muốn đang lưu trong Git/Helm.
- **Live state** là tài nguyên đang chạy thật trên cluster.

Mục tiêu của task là mỗi service có ServiceAccount riêng. Service không cần Kubernetes API sẽ không được mount token và không được cấp RBAC.

## 3. Cách kiểm tra

### 3.1. Render cấu hình trong Git

Đã render riêng release ứng dụng và release observability:

```powershell
helm template techx-app ./techx-corp-chart `
  --namespace techx-tf4 `
  -f ./deploy/values-app-stamp.yaml `
  --skip-schema-validation

helm template techx-observability ./techx-corp-chart `
  --namespace techx-observability `
  -f ./deploy/values-observability.yaml `
  --skip-schema-validation
```

Các loại tài nguyên được kiểm tra gồm `Deployment`, `StatefulSet`, `DaemonSet`, `ServiceAccount`, `Role`, `RoleBinding`, `ClusterRole` và `ClusterRoleBinding`.

### 3.2. Đối chiếu cluster thật

Đã kiểm tra metadata trên cluster:

`arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`

```powershell
kubectl get deploy,statefulset,daemonset -n techx-tf4 `
  -o custom-columns='KIND:.kind,NAME:.metadata.name,SA:.spec.template.spec.serviceAccountName,AUTOMOUNT:.spec.template.spec.automountServiceAccountToken'

kubectl get deploy,statefulset,daemonset -n techx-observability `
  -o custom-columns='KIND:.kind,NAME:.metadata.name,SA:.spec.template.spec.serviceAccountName,AUTOMOUNT:.spec.template.spec.automountServiceAccountToken'
```

Tài khoản audit hiện tại xem được workload và ServiceAccount nhưng không có quyền liệt kê `RoleBinding` và `ClusterRoleBinding`. Vì vậy:

- Thông tin workload, ServiceAccount và automount lấy từ cluster thật.
- Thông tin RBAC hiện tại lấy từ manifest đã render.
- Task 3 cần người có quyền phù hợp chạy `kubectl auth can-i` để xác nhận lần cuối.

## 4. So sánh cấu hình trong Git và cluster thật

| Namespace | Cluster đang chạy | Điểm khác với cấu hình trong Git |
|---|---|---|
| `techx-tf4` | Có 17 Deployment. Trong đó 16 Deployment dùng chung `techx-corp`; `product-reviews` dùng `product-reviews-bedrock`. | Manifest render có 22 Deployment và dùng tên ServiceAccount chung là `techx-app`. Năm service `cart`, `checkout`, `kafka`, `postgresql`, `valkey-cart` có trong Git nhưng hiện không chạy trên cluster. |
| `techx-observability` | Có 7 workload chính, khớp với manifest render. | OpenSearch dùng ServiceAccount `default`. Grafana, Alertmanager và OTel Collector đang bật automount token. Jaeger, metrics-server và Prometheus không ghi rõ giá trị nên Kubernetes mặc định vẫn mount token. |

Năm service chưa chạy trên cluster vẫn phải được sửa trong task 2. Nếu GitOps sync lại, các service này có thể được tạo trở lại từ cấu hình trong Git.

## 5. Bảng audit ứng dụng (`techx-tf4`)

Trong manifest render, 21 trong 22 Deployment dùng chung ServiceAccount `techx-app`. Trên cluster thật, 16 trong 17 Deployment đang chạy dùng chung `techx-corp`. Hai tên khác nhau nhưng có cùng vấn đề: nhiều service đang chia sẻ một danh tính.

`Không ghi rõ, mặc định bật` nghĩa là Pod và ServiceAccount không đặt `automountServiceAccountToken: false`, vì vậy Kubernetes vẫn tự mount token.

| Workload | Trạng thái live | ServiceAccount trong Git | Mount token hiện tại | RBAC trong manifest | Nhu cầu thật | Kết quả mong muốn |
|---|---|---|---|---|---|---|
| accounting | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `accounting`, tắt token, không RBAC |
| ad | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `ad`, tắt token, không RBAC |
| cart | không chạy live | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `cart`, tắt token, không RBAC |
| checkout | không chạy live | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `checkout`, tắt token, không RBAC |
| currency | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `currency`, tắt token, không RBAC |
| email | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `email`, tắt token, không RBAC |
| flagd | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `flagd`, tắt token, không RBAC |
| fraud-detection | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `fraud-detection`, tắt token, không RBAC |
| frontend | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `frontend`, tắt token, không RBAC |
| frontend-proxy | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `frontend-proxy`, tắt token, không RBAC |
| image-provider | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `image-provider`, tắt token, không RBAC |
| kafka | không chạy live | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `kafka`, tắt token, không RBAC |
| llm | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `llm`, tắt token, không RBAC |
| load-generator | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `load-generator`, tắt token, không RBAC |
| payment | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `payment`, tắt token, không RBAC |
| postgresql | không chạy live | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `postgresql`, tắt token, không RBAC |
| product-catalog | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `product-catalog`, tắt token, không RBAC |
| product-reviews | đang chạy, dùng `product-reviews-bedrock` | `product-reviews-bedrock` | ServiceAccount đặt `true` | không có binding cho workload | cần AWS Bedrock qua EKS Pod Identity, không cần K8s API | giữ SA riêng và liên kết AWS; tắt token K8s sau khi smoke test Bedrock |
| quote | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `quote`, tắt token, không RBAC |
| recommendation | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `recommendation`, tắt token, không RBAC |
| shipping | đang chạy, dùng `techx-corp` | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `shipping`, tắt token, không RBAC |
| valkey-cart | không chạy live | `techx-app` dùng chung | không ghi rõ, mặc định bật | không có binding cho workload | không cần K8s API | SA `valkey-cart`, tắt token, không RBAC |

## 6. Bảng audit observability (`techx-observability`)

| Workload | Loại | ServiceAccount live | Mount token hiện tại | RBAC trong manifest | Vì sao cần hoặc không cần API | Kết quả mong muốn |
|---|---|---|---|---|---|---|
| Grafana | Deployment | `grafana` | Pod đặt `true`, ghi đè SA đang đặt `false` | có Role và ClusterRole cho sidecar | sidecar cần xem dashboard/alert từ ConfigMap hoặc Secret | giữ SA riêng; chỉ cho đọc trong namespace nếu đủ; không cấp quyền ghi hoặc wildcard |
| Jaeger | Deployment | `jaeger` | SA đặt `true` | không có binding | không cần K8s API | giữ SA `jaeger`, tắt token, không RBAC |
| metrics-server | Deployment | `metrics-server` | không ghi rõ, mặc định bật | có RBAC hệ thống | cần lấy metrics và thông tin kubelet | giữ SA riêng và RBAC cần thiết của component hệ thống; không cho đọc Secret hoặc ghi workload |
| Prometheus | Deployment | `prometheus` | không ghi rõ, mặc định bật | có ClusterRole và ClusterRoleBinding | cần tìm các target để scrape trên cluster | giữ SA riêng; chỉ cho read/list/watch tài nguyên discovery cần thiết; không đọc Secret, không có quyền ghi |
| OpenSearch | StatefulSet | `default` | Pod đặt `false` | không có binding | không cần K8s API | tạo SA `opensearch`, tiếp tục tắt token, không RBAC |
| Alertmanager | StatefulSet | `techx-observability-alertmanager` | Pod và SA đặt `true` | không có binding | không cần K8s API | giữ SA riêng, tắt token, không RBAC |
| OTel Collector agent | DaemonSet | `otel-collector` | Pod đặt `true` | có ClusterRole và ClusterRoleBinding | cần đọc metadata node/pod/namespace để bổ sung vào telemetry | giữ SA riêng; chỉ cho read/list/watch metadata thật sự cần; không đọc Secret và không ghi |

OTel Collector là DaemonSet, không phải Deployment hoặc StatefulSet. Workload này vẫn được đưa vào audit vì thuộc hệ thống observability và có quyền gọi Kubernetes API.

CronJob `jaeger-es-index-cleaner` là component phụ của subchart Jaeger. Nó đã dùng ServiceAccount riêng và đặt automount token là `false`.

## 7. Workload có thể tắt token ngay

- Toàn bộ 22 application Deployment trong cấu hình Git.
- Jaeger.
- Alertmanager.
- OpenSearch đã tắt token nhưng cần đổi từ ServiceAccount `default` sang `opensearch`.

Riêng `product-reviews` cần chạy smoke test gọi AWS Bedrock sau khi tắt token Kubernetes. EKS Pod Identity là danh tính AWS, không phải lý do để cấp quyền Kubernetes API.

## 8. Workload cần giữ token và phải kiểm tra thêm

| Component | Lý do cần token | Điều phải chứng minh ở task 3 |
|---|---|---|
| metrics-server | cung cấp Kubernetes Metrics API | chỉ có quyền hệ thống cần thiết; không đọc Secret, tạo Pod hoặc exec |
| Prometheus | tìm target để scrape | chỉ read/list/watch đúng tài nguyên discovery; không đọc Secret và không có quyền ghi |
| OTel Collector | đọc metadata để gắn vào telemetry | chỉ read/list/watch node/pod/namespace cần thiết; không đọc Secret và không có quyền ghi |
| Grafana sidecar | tìm dashboard và alert trong namespace | ưu tiên Role trong `techx-observability`; bỏ ClusterRole nếu kiểm thử cho thấy không cần |

Đây mới là danh sách exception dự kiến. Exception chỉ được chấp nhận sau khi task 3 có kết quả `kubectl auth can-i` và negative test.

## 9. Kết luận audit

1. Ứng dụng chưa có danh tính riêng cho từng service. Phần lớn workload đang dùng một ServiceAccount chung.
2. Các application service không có nhu cầu gọi Kubernetes API, vì vậy có thể tắt token và không cần tạo RBAC.
3. `product-reviews` cần giữ liên kết AWS nhưng không cần quyền Kubernetes API.
4. OpenSearch đã tắt token nhưng vẫn dùng ServiceAccount `default`, nên chưa đạt yêu cầu.
5. Jaeger và Alertmanager có ServiceAccount riêng nhưng đang mount token không cần thiết.
6. Grafana, Prometheus, metrics-server và OTel Collector có nhu cầu gọi Kubernetes API. Quyền của chúng phải được thu hẹp và kiểm chứng ở task 3.
7. Role dành cho người dùng, nhóm team hoặc bastion port-forward không phải RBAC của workload, nên không thuộc thay đổi per-service ServiceAccount.

## 10. Yêu cầu đầu vào cho task 2

Task 2 phải thực hiện các thay đổi sau:

- Tạo ServiceAccount riêng, có tên ổn định cho từng application component đang bật.
- Đặt `automountServiceAccountToken: false` ở cả ServiceAccount và Pod của application service không cần API.
- Giữ đúng annotation hoặc cấu hình EKS Pod Identity của `product-reviews-bedrock`, sau đó kiểm tra Bedrock vẫn hoạt động khi tắt token Kubernetes.
- Tạo ServiceAccount riêng cho OpenSearch và tắt token.
- Tắt token của Jaeger và Alertmanager.
- Không tạo Role, RoleBinding, ClusterRole hoặc ClusterRoleBinding cho application service thông thường.
- Render cả hai release và xác nhận không có workload chính nào dùng ServiceAccount `default` hoặc ServiceAccount dùng chung.
- Kiểm tra rollout và chuẩn bị lệnh rollback trước khi áp dụng production.

## 11. Cách rollback

Nếu workload lỗi sau khi triển khai task 2, rollback toàn bộ revision Helm/GitOps về phiên bản ổn định trước đó. Không xử lý nhanh bằng cách cấp RBAC rộng hoặc bật lại token cho tất cả service.

Với workload bị lỗi:

1. Thu thập Pod event và log.
2. Xác định workload cần Kubernetes API, AWS Identity hay chỉ bị lỗi cấu hình.
3. Nếu thật sự cần API, tạo exception với quyền nhỏ nhất và đưa qua review.
4. Render, kiểm thử và rollout lại sau khi exception được duyệt.
