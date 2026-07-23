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
| Product Reviews log check | Log 30 phút gần nhất không khớp `AccessDenied`, `credential`, `Bedrock` hoặc `ERROR` | PASS cho readiness/log; chưa thay thế functional request |
| Grafana ConfigMap discovery | `kubectl auth can-i list configmaps --as=system:serviceaccount:techx-observability:grafana` trả `yes` | PASS |
| Grafana Secret negative test | `kubectl auth can-i list secrets --as=system:serviceaccount:techx-observability:grafana` trả `yes` | **FAIL** |
| Argo CD | `techx-corp` và `techx-observability` đều `OutOfSync`; operation gần nhất báo `Succeeded` | BLOCKED |

### 8.1. Root cause của negative test Grafana

Live `grafana-clusterrole` vẫn có `get/list/watch` trên cả `configmaps` và
`secrets`; live `grafana-clusterrolebinding` vẫn có subject ServiceAccount
`grafana`. Argo CD đánh dấu hai object này là orphaned, `requiresPruning: true`.
Vì môi trường chạy `prune: false`, việc bỏ resource khỏi subchart không thu hồi
quyền đã tồn tại.

Commit tombstone `693354f` đặt `rules: []` và `subjects: []` nhưng tại thời điểm
kiểm tra chỉ có trên branch `cdo08/sec-22-runtime-evidence`, chưa có trong
`origin/main`. Hai Argo application đang pin chart source tại commit
`918a8eb2ad39959c3a8071cc27a4519798977a0c`; commit này không chứa template
`grafana-legacy-rbac-tombstone.yaml`. Vì vậy không được ghi nhận tombstone là đã
deploy và không được chuyển Task 3 sang Done.

### 8.2. Sửa verification script

`kubectl auth can-i` dùng exit code `1` cho câu trả lời hợp lệ `no`. Script cũ
đổi các kết quả này thành `ERROR: no`, tạo fail giả. Script đã được sửa để chấp
nhận hai kết quả chuẩn `yes`/`no`, và chỉ ghi `ERROR` cho lỗi CLI, authentication,
transport hoặc impersonation thực sự.

Sau khi tombstone thực sự được merge vào `main`, pipeline cập nhật GitOps
`targetRevision` và Argo sync, chạy lại mục 5-7. Không xóa trực tiếp hai resource
production để né quy trình GitOps.

## 9. Tiêu chí hoàn thành

- [ ] GitOps promotion đã merge, Argo CD `Synced/Healthy`.
- [x] Live workload dùng đúng per-service ServiceAccount và token policy.
- [ ] Script `verify-sec22-rbac.ps1` trả về PASS.
- [ ] Application SAs không list Secret/Pod, không create Pod và không exec.
- [ ] Observability exceptions chỉ có quyền đã duyệt.
- [ ] Product Reviews gọi Bedrock thành công khi Kubernetes token bị tắt.
- [ ] Output runtime đã được reviewer/operator đính kèm mà không lộ Secret.
