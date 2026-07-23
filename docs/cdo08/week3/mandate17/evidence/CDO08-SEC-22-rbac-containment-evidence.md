# Bằng chứng khoanh vùng RBAC - CDO08-SEC-22

## 1. Mục tiêu

Chứng minh mỗi workload chỉ có quyền Kubernetes API thật sự cần thiết. Nếu một application pod bị chiếm, kẻ tấn công không thể đọc Secret, xem toàn bộ Pod trong namespace, tạo Pod hoặc mở phiên `exec`.

## 2. Phiên bản được kiểm tra

- Chart implementation đã merge: `3f759b5` (`PR #494`).
- GitOps promotion: branch `cdo08/sec-22-deploy-serviceaccounts`, commit `5b0517e`.
- Branch task 3: `cdo08/sec-22-least-privilege-rbac-evidence`.

Không được dùng kết quả runtime trước khi GitOps promotion được merge và Argo CD báo `Synced/Healthy`.

## 3. RBAC được triển khai

### Application workloads

Application ServiceAccount không được gắn Role hoặc ClusterRole. Vì vậy toàn bộ quyền sau phải trả về `no`:

- `list secrets`
- `list pods`
- `create pods`
- `create pods/exec`

### Observability workloads không cần Kubernetes API

`jaeger`, `opensearch` và `techx-observability-alertmanager` không cần gọi Kubernetes API. Token được tắt và không có quyền đọc Secret, xem Pod, tạo Pod hoặc exec.

OpenSearch subchart tạo một Role namespace chỉ có quyền `use` một PodSecurityPolicy được gọi tên cụ thể. Đây là giới hạn của subchart hiện tại, không có wildcard và không cấp quyền đọc/ghi workload. Quyền cũ này cần được loại bỏ khi nâng chart không còn phụ thuộc PodSecurityPolicy.

### Observability workloads cần Kubernetes API

| ServiceAccount | Quyền được giữ | Lý do |
|---|---|---|
| `grafana` | `get/list/watch configmaps` trong `techx-observability` | sidecar nạp dashboard, alert và datasource từ ConfigMap |
| `prometheus` | cluster read cho target discovery | tìm Pod, Service, Endpoint và Node cần scrape |
| `otel-collector` | cluster read metadata và quản lý Lease | bổ sung Kubernetes metadata, kubelet metrics và leader election |
| `metrics-server` | cluster read Pod/Node/Namespace/ConfigMap cần thiết | cung cấp Kubernetes Metrics API |

Grafana dùng Role namespace do chart cha quản lý. RBAC mặc định của subchart đã tắt vì nó cho phép đọc cả Secret và dùng ClusterRole.

Do Argo CD đang đặt `prune: false`, hai resource cũ `grafana-clusterrole` và `grafana-clusterrolebinding` không tự bị xóa khi chúng biến mất khỏi manifest của subchart. Chart vì vậy render tombstone cùng tên với `rules: []` và `subjects: []` để vô hiệu hóa quyền cũ mà không cần xóa trực tiếp trên production. Tombstone không cấp bất kỳ quyền nào; có thể xóa trong một đợt cleanup được duyệt sau khi bật prune có kiểm soát.

Không Role nào của SEC-22 dùng wildcard verb/resource. Không ServiceAccount nào được cấp `cluster-admin`.

## 4. Kiểm tra manifest trước deploy

```powershell
helm lint .\techx-corp-chart `
  -f ..\tf4-phase3-gitops-manifests\environments\production\observability-values.yaml `
  -f ..\tf4-phase3-gitops-manifests\environments\production\alertmanager-routing-values.yaml

helm template techx-observability .\techx-corp-chart `
  --namespace techx-observability `
  -f ..\tf4-phase3-gitops-manifests\environments\production\observability-values.yaml `
  -f ..\tf4-phase3-gitops-manifests\environments\production\alertmanager-routing-values.yaml
```

Kết quả tại thời điểm viết tài liệu: Helm lint và render thành công. Quyền có hiệu lực của Grafana nằm ở Role `grafana-sidecar-configmaps`, với resource `configmaps` và verb `get/list/watch`. Hai object cluster-scope cũ được render dưới dạng tombstone rỗng để xử lý an toàn môi trường `prune: false`.

## 5. Điều kiện trước khi lấy bằng chứng runtime

```powershell
kubectl get applications -n argocd

kubectl get deploy,statefulset,daemonset -n techx-tf4 `
  -o custom-columns='KIND:.kind,NAME:.metadata.name,READY:.status.readyReplicas,SA:.spec.template.spec.serviceAccountName,AUTOMOUNT:.spec.template.spec.automountServiceAccountToken'

kubectl get deploy,statefulset,daemonset -n techx-observability `
  -o custom-columns='KIND:.kind,NAME:.metadata.name,READY:.status.readyReplicas,SA:.spec.template.spec.serviceAccountName,AUTOMOUNT:.spec.template.spec.automountServiceAccountToken'
```

Chỉ tiếp tục khi:

- Argo CD báo application app và observability đã `Synced/Healthy` đúng revision.
- Không application workload nào dùng `techx-corp`, `techx-app` hoặc `default`.
- Mỗi application workload có ServiceAccount riêng và automount là `false`.
- OpenSearch dùng `opensearch`; Jaeger và Alertmanager đã tắt token.

## 6. Chạy negative test

Người chạy cần quyền impersonate ServiceAccount. Chạy script:

```powershell
.\scripts\cdo08\verify-sec22-rbac.ps1
```

Có thể kiểm tra thủ công một ServiceAccount:

```powershell
kubectl auth can-i list secrets -n techx-tf4 `
  --as=system:serviceaccount:techx-tf4:accounting

kubectl auth can-i list pods -n techx-tf4 `
  --as=system:serviceaccount:techx-tf4:accounting

kubectl auth can-i create pods -n techx-tf4 `
  --as=system:serviceaccount:techx-tf4:accounting

kubectl auth can-i create pods/exec -n techx-tf4 `
  --as=system:serviceaccount:techx-tf4:accounting
```

Cả bốn lệnh trên phải trả về `no`. Script trả exit code khác 0 nếu có kết quả khác kỳ vọng hoặc người chạy thiếu quyền impersonate.

## 7. Smoke test Product Reviews/Bedrock

Sau rollout:

1. Xác nhận Deployment `product-reviews` Ready và dùng `product-reviews-bedrock` với automount `false`.
2. Gửi một request review qua luồng storefront hoặc công cụ smoke test đã được duyệt.
3. Xác nhận request thành công và log không có lỗi lấy AWS credentials hoặc `AccessDenied` từ Bedrock.
4. Không in token, AWS credential hoặc nội dung Secret vào evidence.

```powershell
kubectl get deploy product-reviews -n techx-tf4 `
  -o custom-columns='READY:.status.readyReplicas,SA:.spec.template.spec.serviceAccountName,AUTOMOUNT:.spec.template.spec.automountServiceAccountToken'

kubectl logs -n techx-tf4 deploy/product-reviews --since=10m | `
  Select-String -Pattern 'AccessDenied|credential|Bedrock|ERROR'
```

## 8. Trạng thái runtime hiện tại

Lần kiểm tra ngày 23/07/2026 dùng context
`arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster` cho kết quả:

| Hạng mục | Kết quả live | Verdict |
|---|---|---|
| Application identity | 17 Deployment đang chạy dùng ServiceAccount riêng; không workload nào dùng `techx-corp`, `techx-app` hoặc `default` | PASS |
| Application token | Cả 17 Deployment có `automountServiceAccountToken: false` | PASS |
| Product Reviews identity | Deployment Ready `1/1`, dùng `product-reviews-bedrock`, automount `false` | PASS |
| Product Reviews/Bedrock smoke | POST `/api/product-ask-ai-assistant/0PUK6V6EV0` trả response dài 117 ký tự; log có `ai_assistant_request` và `ai_assistant_completed`, không có `AccessDenied` hoặc lỗi credential | PASS |
| Grafana ConfigMap discovery | `kubectl auth can-i list configmaps --as=system:serviceaccount:techx-observability:grafana` trả `yes` | PASS |
| Grafana Secret negative test | `kubectl auth can-i list secrets --as=system:serviceaccount:techx-observability:grafana` trả `no` | PASS |
| Full RBAC suite | `scripts/cdo08/verify-sec22-rbac.ps1` kiểm tra 117 permission assertions và kết thúc `SEC-22 RBAC verification passed.` | PASS |
| GitOps promotion | Source PR #522 và GitOps PR #131 đã merge; Argo pin `b6cc154f01fbcbc52fb5466d6c518bb4357645b4` | PASS |
| Tombstone live | `grafana-clusterrole.rules` rỗng; `grafana-clusterrolebinding.subjects` rỗng; cả hai có label `security.techx.io/migration-tombstone: "true"` | PASS |

### 8.1. Root cause của negative test Grafana

Trước follow-up, live `grafana-clusterrole` có `get/list/watch` trên cả
`configmaps` và `secrets`, còn `grafana-clusterrolebinding` vẫn gắn ServiceAccount
`grafana`. Do môi trường chạy `prune: false`, việc bỏ resource khỏi subchart
không thu hồi quyền đã tồn tại.

Source PR #522 đưa tombstone vào `main` bằng squash commit `b6cc154`. GitOps PR
#131 sau đó cập nhật chart source SHA cho cả `techx-corp` và
`techx-observability`. Argo đã apply hai object cùng tên với `rules: []` và
`subjects: []`, vì vậy binding cũ được vô hiệu hóa mà không xóa trực tiếp
resource production. Role namespace `grafana-sidecar-configmaps` tiếp tục cấp
`get/list/watch` riêng cho ConfigMap.

### 8.2. Sửa verification script

`kubectl auth can-i` dùng exit code `1` cho câu trả lời hợp lệ `no`. Script cũ
đổi các kết quả này thành `ERROR: no`, tạo fail giả. Script đã được sửa để chấp
nhận hai kết quả chuẩn `yes`/`no`, và chỉ ghi `ERROR` cho lỗi CLI, authentication,
transport hoặc impersonation thực sự.

Lần chạy cuối xác nhận mọi kết quả `no` được xử lý đúng và toàn bộ suite PASS.
Không có Secret, token hoặc AWS credential nào được ghi vào evidence.

Trong smoke test, ứng dụng có một số log OTLP exporter `UNAVAILABLE` tới OTel
Collector. Đây là finding observability riêng; request Bedrock vẫn hoàn tất và
không có lỗi identity/credential, nên không làm thay đổi SEC-22 verdict.

### 8.3. Runtime output

Grafana tombstone live:

```yaml
kind: ClusterRole
metadata:
  name: grafana-clusterrole
  labels:
    security.techx.io/migration-tombstone: "true"
rules: null
---
kind: ClusterRoleBinding
metadata:
  name: grafana-clusterrolebinding
  labels:
    security.techx.io/migration-tombstone: "true"
roleRef:
  name: grafana-clusterrole
```

`rules: null` và việc không có trường `subjects` là biểu diễn live của hai danh
sách rỗng `rules: []` và `subjects: []` trong manifest đã apply.

Trích output từ `scripts/cdo08/verify-sec22-rbac.ps1`:

```text
Namespace           ServiceAccount Permission       Expected Actual Status
techx-observability grafana        list configmaps  yes      yes    PASS
techx-observability grafana        list secrets     no       no     PASS
techx-observability grafana        list pods        no       no     PASS
techx-observability grafana        create pods      no       no     PASS
techx-observability grafana        create pods/exec no       no     PASS

SEC-22 RBAC verification passed.
```

Script đã chạy đủ 117 assertions. Bảng trên giữ phần Grafana quan trọng nhất;
mọi assertion application, Jaeger, OpenSearch, Alertmanager, Prometheus, OTel
Collector và metrics-server còn lại cũng trả `PASS`.

Product Reviews/Bedrock functional smoke output:

```text
ProductId         : 0PUK6V6EV0
ProductName       : Solar System Color Imager
HasResponse       : True
ResponseLength    : 117
HasActionProposal : False

ai_assistant_request
ai_assistant_completed
```

## 9. Tiêu chí hoàn thành

- [x] GitOps promotion đã merge và Argo đã apply target revision `b6cc154`.
- [x] Live workload dùng đúng per-service ServiceAccount và token policy.
- [x] Script `verify-sec22-rbac.ps1` trả về PASS.
- [x] Application SAs không list Secret/Pod, không create Pod và không exec.
- [x] Observability exceptions chỉ có quyền đã duyệt.
- [x] Product Reviews gọi Bedrock thành công khi Kubernetes token bị tắt.
- [x] Output runtime đã được reviewer/operator đính kèm mà không lộ Secret.

**Trạng thái Task 3: Done.**
