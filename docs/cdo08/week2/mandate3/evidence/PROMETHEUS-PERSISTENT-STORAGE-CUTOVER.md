# Prometheus Persistent Storage Cutover

## Mục tiêu

Prometheus trước thay đổi dùng `emptyDir` cho `/data`, nên TSDB mất khi Pod bị replace. Thay đổi này chuyển `/data` sang PVC 20Gi dùng StorageClass `gp2-retain`.

## Lưu ý cutover đầu tiên

Metrics đang nằm trong `emptyDir` của Pod Prometheus hiện tại sẽ mất một lần khi rollout sang PVC mới. PVC mới bắt đầu rỗng, sau đó mới giữ metrics qua các lần Pod restart/recreate tiếp theo.

Trước rollout cần:

- Chạy trong change window đã approve.
- Export dashboard screenshot hoặc query result quan trọng cần giữ.
- Ghi nhận rõ one-time TSDB loss là expected trong lần cutover đầu.

## Lifecycle retention

PVC Prometheus được render với:

- `helm.sh/resource-policy: keep`
- `argocd.argoproj.io/sync-options: Prune=false,Delete=false`
- StorageClass `gp2-retain`
- `reclaimPolicy: Retain`

Mục tiêu là tránh xóa EBS volume tự động nếu PVC/release bị delete nhầm.

## Verification sau rollout

```bash
kubectl get storageclass gp2-retain -o yaml
kubectl -n techx-observability get pvc,pv
kubectl -n techx-observability describe pod -l app.kubernetes.io/name=prometheus
kubectl -n techx-observability exec deploy/prometheus -c prometheus-server -- wget -qO- http://127.0.0.1:9090/-/ready
```

Sau đó thực hiện controlled Pod replacement và query range đi qua thời điểm replacement để xác nhận metrics vẫn còn.

## Recovery khi PVC bị xóa nhầm

Nếu PVC bị xóa nhưng PV/EBS còn ở trạng thái `Released` nhờ reclaim policy `Retain`:

1. Không xóa PV hoặc EBS volume.
2. Ghi lại PV name, EBS volume ID và `claimRef` hiện tại.
3. Tạo lại PVC cùng namespace, storage size và StorageClass.
4. Rebind PV vào PVC mới theo quy trình admin đã review.
5. Rollout lại Prometheus và xác nhận `/data` mount lại retained volume.

Không patch/bind PV thủ công nếu chưa có approval từ admin/Tech Lead.
