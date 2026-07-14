# Yêu cầu CDO04 review Cost/Performance - REL-03 PVC Persistence

**Backlog:** CDO08-REL-03  
**Commit:** `614c6ef feat(cdo08): add incremental persistence for valkey and kafka`  
**Bên yêu cầu:** CDO08  
**Bên review:** CDO04 Cost/Performance  
**Trạng thái:** Đang chờ CDO04 review

---

## Mục tiêu

CDO08 cần CDO04 review tác động cost/performance trước khi merge/deploy thay đổi incremental persistence cho Valkey và Kafka.

Commit này không triển khai managed service và không bật HA multi-replica. Thay đổi chỉ bổ sung EBS-backed PVC cho stateful components hiện tại để giảm rủi ro mất dữ liệu khi pod recreate/reschedule.

---

## Tóm tắt thay đổi

| Component | Thay đổi | StorageClass | Dung lượng | Mục đích |
|-----------|--------|--------------|------|---------|
| `valkey-cart` | Thêm `valkey-cart-pvc`, mount `/data`, bật append-only persistence | `gp2` | `5Gi` | Giảm rủi ro mất cart state khi pod recreate |
| `kafka` | Thêm `kafka-pvc`, set `KAFKA_LOG_DIRS=/tmp/kraft-combined-logs` | `gp2` | `10Gi` | Giữ Kafka broker log/event data qua pod recreate |

**Tổng EBS storage mới:** khoảng `15Gi gp2`.

---

## Ước tính chi phí

**Cơ sở tính:** AWS EBS `gp2` tại US East/N. Virginia có giá tham chiếu khoảng `$0.10/GB-month`. EBS tính phí theo dung lượng đã provision theo GB-month cho đến khi volume được xóa.

| PVC | Dung lượng | Giả định đơn giá | Ước tính/tháng | Ước tính/tuần |
|-----|------|-----------------------|------------------------|-----------------------|
| `valkey-cart-pvc` | `5Gi` | `$0.10/GB-month` | `$0.50/tháng` | `~$0.12/tuần` |
| `kafka-pvc` | `10Gi` | `$0.10/GB-month` | `$1.00/tháng` | `~$0.23/tuần` |
| **Tổng** | **15Gi** | `$0.10/GB-month` | **`$1.50/tháng`** | **`~$0.35/tuần`** |

### Ghi chú

- Ước tính này chưa tính snapshot/backup vì PR này chỉ tạo PVC.
- Ước tính này chưa tính cross-AZ/network transfer; PVC là EBS volume attach trong cluster.
- Nếu account còn AWS Free Tier credit/free EBS allowance thì số tiền bill thực tế có thể thấp hơn, nhưng CDO08 không nên dựa vào Free Tier để xin duyệt.
- Chi phí nhỏ so với weekly budget hiện tại, nhưng CDO04 vẫn cần xác nhận tác động node/storage/IO và thời điểm deploy.

Công thức:

```text
15Gi * $0.10 per GB-month = $1.50/month
$1.50 / 30 * 7 = ~$0.35/week
```

---

## File thay đổi

- `techx-corp-chart/templates/component-pvcs.yaml`
- `techx-corp-chart/values.yaml`
- `docs/cdo08/week2/CDO08-REL-03-postgresql-valkey-kafka-persistence-ha-plan.md`

---

## Câu hỏi cần CDO04 review

| Câu hỏi | Phản hồi CDO04 |
|----------|----------------|
| Chi phí thêm khoảng `15Gi gp2` có nằm trong budget hiện tại không? | Pending |
| `gp2` có phù hợp không, hay nên dùng storage class khác nếu cluster hỗ trợ? | Pending |
| EBS IOPS/throughput của PVC nhỏ có đủ cho Valkey AOF và Kafka broker log workload hiện tại không? | Pending |
| Thay đổi này có gây áp lực node storage/IO hoặc scheduling không? | Pending |
| `strategy: Recreate` cho `valkey-cart` và `kafka` gây downtime ngắn khi deploy. CDO04 có chấp nhận timing deploy này trong window hiện tại không? | Pending |

---

## Kết quả mong đợi từ CDO04

CDO04 vui lòng trả lời theo format:

| Hạng mục | Quyết định | Ghi chú |
|------|----------|-------|
| PVC cost | Approve / Reject / Needs change | ... |
| StorageClass | Keep `gp2` / Change | ... |
| IO/performance risk | Low / Medium / High | ... |
| Deploy timing with `Recreate` | Approve / Need window | ... |

---

## Ghi chú của CDO08

- Đây là persistence incremental, chưa phải HA.
- `strategy: Recreate` được dùng để tránh `ReadWriteOnce` PVC bị mount đồng thời trong rolling update.
- Nếu CDO04 reject cost hoặc storage choice, CDO08 sẽ revert hoặc chỉnh PVC size/storageClass trước khi deploy.
- Sau deploy, CDO08 sẽ verify:
  - `kubectl -n techx-tf4 get pvc valkey-cart-pvc kafka-pvc`
  - `kubectl -n techx-tf4 rollout status deploy/valkey-cart`
  - `kubectl -n techx-tf4 rollout status deploy/kafka`
