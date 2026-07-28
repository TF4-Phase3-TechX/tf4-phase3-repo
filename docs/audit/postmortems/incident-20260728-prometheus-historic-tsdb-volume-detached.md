# Báo cáo sự cố: Prometheus mất metrics lịch sử sau storage lifecycle migration

**Issue:** [#723](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/issues/723)

**Ngày ghi nhận:** 2026-07-28

**Namespace:** `techx-observability`

**Thành phần:** Grafana, Prometheus, Kubernetes PVC/PV, AWS EBS

**Mức độ:** Medium — không làm gián đoạn customer-facing traffic nhưng làm mất khả năng quan sát lịch sử

**Trạng thái:** Đã xác định volume chứa dữ liệu cũ; chưa thực hiện recovery live

---

## 1. Executive summary

Grafana không hiển thị metrics trong phần lớn cửa sổ **Last 7 days**; các time series chỉ bắt đầu xuất hiện lại gần ngày 2026-07-28. Kiểm tra live cho thấy Prometheus đang dùng một PVC/EBS volume mới được tạo ngày 2026-07-27, trong khi EBS volume cũ tạo ngày 2026-07-16 đã bị detach nhưng vẫn còn ở trạng thái `available`.

Sự cố không phải do Grafana time range hoặc Prometheus retention. Prometheus vẫn cấu hình retention `7d`. Nguyên nhân trực tiếp là PVC `prometheus` đã được recreate và bind sang một EBS volume rỗng mới; TSDB lịch sử vẫn có khả năng còn trên volume cũ nhờ `reclaimPolicy: Retain`.

Không xóa volume cũ `vol-051c0352bdfaceb5d`. Recovery phải được thực hiện trong change window, sau khi snapshot và có phê duyệt của platform owner.

## 2. User-visible impact

- Dashboard **Business Flow Health Overview** trống dữ liệu từ khoảng 2026-07-22 đến trước thời điểm volume mới bắt đầu nhận samples.
- Các phép tính SLO, latency, request rate và điều tra incident dựa trên historical range bị thiếu dữ liệu.
- Stat panels vẫn có thể hiển thị giá trị gần nhất, nên không phản ánh rõ khoảng trống lịch sử nếu chỉ nhìn trạng thái hiện tại.
- Không có bằng chứng cho thấy application traffic hoặc dữ liệu giao dịch bị mất.

### Grafana evidence

![Grafana Last 7 days chỉ có dữ liệu sát ngày 28/07](images/incident-20260728-grafana-last-7-days-gap.png)

_Hình 1 — Dashboard chọn `Last 7 days`, nhưng request-rate và p95-latency series chỉ xuất hiện sát ngày 28/07. Đây là biểu hiện đồng thời trên nhiều series, phù hợp với một lần reset TSDB hơn là lỗi query riêng lẻ._

## 3. Timeline

| Thời gian (UTC) | Sự kiện |
|---|---|
| 2026-07-16 16:33:38 | EBS volume cũ `vol-051c0352bdfaceb5d` được tạo cho PVC `techx-observability/prometheus`. |
| 2026-07-25 | Commit `628b66e1` bổ sung vòng đời gp3, `gp3-retain` và cấu hình Prometheus dùng `existingClaim: prometheus`. |
| 2026-07-27 19:11:19 | PVC `prometheus` hiện tại được tạo với UID `ea652ab7-02d5-40eb-be05-8f922df2f6c9`. |
| 2026-07-27 19:11:21 | EBS volume mới `vol-03364cc7d0cb2fd35` được provision cho PVC mới. |
| 2026-07-27 19:33 | Prometheus khởi động, replay WAL trên volume mới và bắt đầu tạo TSDB blocks mới. |
| 2026-07-28 | Grafana được ghi nhận chỉ còn metrics từ thời điểm volume mới hoạt động. |

## 4. Runtime evidence

### 4.1 PVC và mount hiện tại

```text
NAME         STATUS   VOLUME                                     CAPACITY   STORAGECLASS   AGE
prometheus   Bound    pvc-ea652ab7-02d5-40eb-be05-8f922df2f6c9   20Gi       gp3-retain    7h33m
```

PVC live có:

```yaml
creationTimestamp: "2026-07-27T19:11:19Z"
spec:
  storageClassName: gp3-retain
  volumeName: pvc-ea652ab7-02d5-40eb-be05-8f922df2f6c9
```

Deployment hiện mount đúng PVC mới vào `/data`:

```text
storage-volume pvc=prometheus
container=prometheus-server mount=storage-volume:/data
```

### 4.2 EBS volume inventory

| Vai trò | Volume ID | Trạng thái | Created (UTC) | Kubernetes PV identity |
|---|---|---|---|---|
| Historic TSDB | `vol-051c0352bdfaceb5d` | `available` | 2026-07-16 16:33:38 | `pvc-efca0cc7-6cb1-4793-8864-d4c6e46a2fe7` |
| Current TSDB | `vol-03364cc7d0cb2fd35` | `in-use` | 2026-07-27 19:11:21 | `pvc-ea652ab7-02d5-40eb-be05-8f922df2f6c9` |

Cả hai volume đều có tag:

```text
kubernetes.io/created-for/pvc/name=prometheus
kubernetes.io/created-for/pvc/namespace=techx-observability
```

Volume cũ ở trạng thái `available`, thay vì bị xóa, chứng minh `Retain` đã bảo vệ EBS asset sau khi PVC/PV cũ bị loại khỏi binding hiện tại.

### 4.3 Prometheus startup evidence

Prometheus bắt đầu TSDB trên volume hiện tại vào khoảng `2026-07-27T19:33Z`:

```text
time=2026-07-27T19:33:32.250Z level=INFO msg="WAL replay completed"
time=2026-07-27T19:33:32.338Z level=INFO msg="TSDB started"
time=2026-07-27T19:33:32.340Z level=INFO msg="TSDB retention updated" duration=1w
```

`duration=1w` xác nhận retention vẫn là bảy ngày. Vì vậy retention không thể giải thích việc toàn bộ dữ liệu trước ngày 27/07 biến mất cùng lúc.

## 5. Root cause analysis

### Direct cause

PVC `techx-observability/prometheus` đã bị recreate. PVC mới được dynamic provision sang EBS volume mới rỗng, nên Prometheus chỉ đọc được WAL/blocks phát sinh sau thời điểm cutover.

### Contributing change

Commit `628b66e196c4f575c2b0be091ba3adf1047522e5` (`feat(observability): add gp3 storage lifecycle`) giới thiệu `gp3-retain` và đặt cấu hình tương lai của Prometheus thành:

```yaml
persistentVolume:
  enabled: true
  existingClaim: prometheus
  storageClass: gp3-retain
```

Mục tiêu của commit là reuse claim hiện hữu. Tuy nhiên `storageClassName` của PVC là immutable; việc chuyển binding từ lifecycle cũ sang `gp3-retain` không thể là một in-place update an toàn. Runtime evidence chứng minh PVC thực tế đã được thay thế vào ngày 27/07.

### Root-cause boundary

Evidence hiện có xác nhận chắc chắn **PVC recreation và volume replacement** là nguyên nhân mất historical metrics. Role audit không có quyền đọc ArgoCD Application hoặc cluster-scoped PV/audit events, vì vậy báo cáo chưa quy kết thao tác delete/recreate cho một user, controller hay lệnh cụ thể. Cần EKS audit log/CloudTrail correlation để hoàn tất attribution.

## 6. Recovery plan

> Không thực hiện trực tiếp từ tài liệu này. Mọi bước write/delete/rebind cần change approval, backup và platform owner.

1. Đặt protection tag và tuyệt đối không xóa `vol-051c0352bdfaceb5d`.
2. Tạo EBS snapshot của cả volume cũ và volume hiện tại.
3. Scale Prometheus về `0` trong change window để tránh ghi đồng thời.
4. Mount snapshot/clone của volume cũ vào helper pod chỉ đọc và xác minh thư mục TSDB (`wal`, `chunks_head`, ULID block directories).
5. Chọn một trong hai chiến lược:
   - **Rebind:** tạo static PV trỏ đến volume cũ và bind lại PVC `prometheus`.
   - **Block recovery:** copy các immutable TSDB block hợp lệ sang volume đích; không copy WAL đang active và phải kiểm tra overlapping blocks trước khi start.
6. Scale Prometheus lên `1`, kiểm tra `/-/ready`, logs và query range qua ngày 16–28/07.
7. Xác minh dashboard Grafana, alert evaluation và ingestion hiện tại.
8. Giữ snapshot rollback cho đến khi owner ký xác nhận recovery.

## 7. Verification checklist

- [ ] Snapshot của volume cũ và volume hiện tại hoàn tất.
- [ ] Historic volume được mount read-only và xác nhận có TSDB blocks trước 27/07.
- [ ] Prometheus `Running 2/2`, không có mount, corruption hoặc repair error.
- [ ] Query `up` và business-flow metrics trả về samples xuyên qua thời điểm 27/07.
- [ ] Grafana hiển thị lại dữ liệu 16/07–27/07.
- [ ] Ingestion mới tiếp tục sau recovery, không tạo khoảng trống mới.
- [ ] Alert rules và recording rules evaluate bình thường.

## 8. Preventive actions

| Priority | Action | Acceptance criteria |
|---|---|---|
| P0 | Cấm tự động delete/recreate PVC Prometheus trong storage migration. | Pipeline fail nếu rendered PVC đổi immutable `storageClassName` hoặc claim identity. |
| P0 | Snapshot trước mọi PVC/PV migration. | Change ticket chứa snapshot ID và restore test/check. |
| P1 | Alert khi PVC UID hoặc Prometheus storage identity thay đổi. | Alert chứa namespace, claim, old/new UID. |
| P1 | Thêm post-sync historical query canary. | Query range trước rollout vẫn có samples sau rollout. |
| P1 | Thu thập EKS audit events cho PVC delete/create và PV release. | Xác định được actor/controller cùng timestamp. |
| P2 | Ghi rõ runbook static rebind và TSDB block recovery. | Runbook được platform/reliability owner review. |

## 9. Reproduction commands (read-only)

```bash
export AWS_PROFILE=TF4-AuditReadOnlyAndAnalyze

kubectl -n techx-observability get pods,pvc -o wide
kubectl -n techx-observability get pvc prometheus -o yaml
kubectl -n techx-observability get deploy prometheus -o yaml

aws ec2 describe-volumes \
  --region us-east-1 \
  --volume-ids vol-051c0352bdfaceb5d vol-03364cc7d0cb2fd35

kubectl -n techx-observability logs deploy/prometheus \
  -c prometheus-server --since=24h \
  | grep -Ei 'WAL replay|TSDB started|retention|corrupt|repair'
```

## 10. Current limitations

Role `TF4-AuditReadOnlyAndAnalyze` cho phép đọc namespaced pod/PVC và AWS EBS inventory nhưng không cho phép:

- list cluster-scoped PersistentVolumes;
- đọc ArgoCD `Application` trong namespace `argocd`;
- `pods/exec`, `pods/portforward` hoặc `services/proxy` để truy cập Grafana nội bộ.

Do đó recovery chưa được thực hiện và ảnh Grafana trong báo cáo được thu tại thời điểm phát hiện sự cố. Các thao tác live tiếp theo phải dùng role được phê duyệt trong change window.
