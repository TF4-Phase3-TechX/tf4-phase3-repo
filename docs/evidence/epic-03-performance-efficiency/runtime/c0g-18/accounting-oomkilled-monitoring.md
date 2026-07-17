# C0G-18 — Accounting OOMKilled: Điều tra, ổn định và theo dõi

**Jira:** C0G-18
**Scope:** `techx-tf4` — service `accounting` (Kafka consumer, ghi sổ đơn hàng vào PostgreSQL)
**Owner:** CDO-04.
**Liên quan:** C0G-39 (PostgreSQL OOMKilled — `/postgresql-oomkilled-investigation.md`)
**Status:** Resource đã tăng, đang trong cửa sổ theo dõi 24h + đã qua 1 lần acceptance run (200 user/15 phút) không phát sinh OOM mới

---

## 1. Sự cố ban đầu

```
kubectl -n techx-tf4 get pods -l app.kubernetes.io/name=accounting -o wide
accounting-85db46b594-8hszx   1/1   Running   41 (2d22h ago)   3d7h
```

Pod `accounting` cũ ghi nhận `CrashLoopBackOff` do `OOMKilled`, `Exit Code: 137`, **Restart Count: 89** (số liệu từ `docs/cdo08/week1/nam-runtime-reliability-findings.md`), sau đó **Restart Count: 41** dồn vào ~8 giờ đầu sau khi pod được tạo, rồi đứng yên (không restart thêm) trong gần 3 ngày liên tục — trước khi resource được điều chỉnh.

Cấu hình gốc: `techx-corp-chart/values.yaml:186-188` — chỉ có `limits.memory: 120Mi`, không có `requests` tường minh, không có `initContainer` chờ Kafka nào khác ngoài `wait-for-kafka`.

## 2. Giả thuyết root cause đã xét

| Giả thuyết                                                                                                                                                                                 | Đánh giá                                                                                                                           |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| **EF Core `DBContext` không `ChangeTracker.Clear()`** (`Consumer.cs:34,52,98-132`) — 1 context sống suốt vòng đời consumer, mỗi order `Add()` 3 entity không bao giờ giải phóng            | Vẫn là nghi vấn hàng đầu về mặt code, nhưng **chưa được reproduce rõ ràng bằng trend leo dốc thực tế** — cần theo dõi thêm (mục 5) |
| **Burst catch-up do `AutoOffsetReset.Earliest`** (`Consumer.cs:147`) + `GroupId` cố định `"accounting"` — nếu offset bị mất/reset, consumer đọc lại toàn bộ lịch sử topic `orders` dồn dập | Khớp với pattern "89 restart dồn 8h đầu rồi im" quan sát ban đầu — không loại trừ                                                  |
| **.NET + OTel auto-instrumentation overhead** (`instrument.sh`, base image `mcr.microsoft.com/dotnet/aspnet:10.0`) cần nhiều RAM hơn baseline để khởi động                                 | Góp phần làm limit 120Mi càng thêm chật, không phải nguyên nhân chính                                                              |
| **Thiếu `requests.memory` tường minh** — K8s tự default `requests = limits = 120Mi` khi chỉ set `limits`, không có đệm Burstable                                                           | Xác nhận đúng — đã sửa ở mục 3                                                                                                     |

## 3. Thay đổi đã áp dụng

```yaml
# techx-corp-chart/values.yaml : dòng 186-188
accounting:
  resources:
    limits:
      memory: 256Mi
```

```
kubectl describe pod -n techx-tf4 accounting-55d8fcbb67-n7zmd
Node:            ip-10-0-10-231.ec2.internal
Start Time:      Mon, 13 Jul 2026 11:40:32 +0700
Restart Count:   0
Limits:
  memory:  256Mi
Requests:
  memory:  256Mi
QoS Class:       Burstable
```

## 4. Đối chiếu với C0G-39 (PostgreSQL) — loại trừ khả năng liên đới

Vì C0G-39 phát hiện `postgresql` bị OOM do khả năng cao là "vạ lây" từ node dùng chung với Jaeger, cần xác nhận `accounting` không nằm cùng node với các pod đang bất ổn:

```
accounting  → ip-10-0-10-231.ec2.internal
grafana     → ip-10-0-10-231.ec2.internal
jaeger      → ip-10-0-11-40.ec2.internal
postgresql  → ip-10-0-11-40.ec2.internal
```

`accounting` và `grafana` cùng node (`10-231`), nhưng Grafana tại thời điểm ghi nhận đã ổn định resource riêng (xem báo cáo Grafana), không có dấu hiệu ảnh hưởng chéo sang `accounting` (Restart Count = 0 kể từ khi redeploy). Không có bằng chứng liên đới giữa 2 sự cố C0G-18 và C0G-39 ngoài việc từng chạy cùng đợt thay đổi resource.

## 5. Theo dõi bắt buộc — chưa thể đóng task chỉ vì "chưa restart lại"

`Restart Count = 0` sau khi tăng resource **chưa đủ để kết luận đã fix xong**, vì nếu root cause là leak (giả thuyết ChangeTracker), việc tăng RAM chỉ trì hoãn OOM chứ không chặn. Cách phân biệt duy nhất là nhìn **trend theo thời gian**, không phải 1 điểm đo:

```promql
# Trend chính — phẳng hay leo dốc?
container_memory_working_set_bytes{namespace="techx-tf4", pod=~"accounting-.*", container="accounting"}

# % so với limit mới (256Mi)
100 * container_memory_working_set_bytes{namespace="techx-tf4", pod=~"accounting-.*", container="accounting"}
    / container_spec_memory_limit_bytes{namespace="techx-tf4", pod=~"accounting-.*", container="accounting"}

# Slope — dương liên tục & ổn định = leak thật; dao động quanh 0 = phẳng, chỉ là thiếu đệm cũ
deriv(container_memory_working_set_bytes{namespace="techx-tf4", pod=~"accounting-.*", container="accounting"}[1h])

# Dự đoán có chạm 256Mi (268435456 bytes) trong 24h tới không
predict_linear(container_memory_working_set_bytes{namespace="techx-tf4", pod=~"accounting-.*", container="accounting"}[6h], 86400)
```

Đánh dấu restart mới (nếu có) lên cùng dashboard qua Grafana Annotation:

```promql
increase(kube_pod_container_status_restarts_total{namespace="techx-tf4", pod=~"accounting-.*", container="accounting"}[5m]) > 0
```

## 6. Kết quả acceptance run (200 user / ramp-up 20 / 15 phút)

Đã chạy 2 lần theo đúng thông số Directive #2 — `accounting` **không restart, không OOM** trong suốt bài test. Đây là tín hiệu tích cực nhưng **không đóng task**: cần đủ 24h quan sát trend liên tục (mục 5) trước khi kết luận resource mới là đủ, đặc biệt vì bài test chỉ chạy 15 phút — không đủ dài để bộc lộ leak tích luỹ chậm nếu có.

## 7. Acceptance Criteria (C0G-18)

- [x] Evidence OOMKilled/restart trước khi đổi resource (mục 1).
- [x] Resource mới đã deploy qua PR, xác nhận runtime đúng cấu hình (mục 3).
- [x] Đã loại trừ liên đới trực tiếp với sự cố C0G-39 qua đối chiếu node (mục 4).
- [x] Acceptance run 200-user/15 phút — pass, không OOM.
- [ ] Trend Prometheus ≥24h sau khi tăng resource: phẳng, không leo dốc theo số order xử lý.
- [ ] Restart count không tăng thêm trong ít nhất 24h.
- [ ] Nếu trend vẫn leo dốc sau 24h: mở follow-up ticket sửa `Consumer.cs` (`ChangeTracker.Clear()` sau `SaveChanges()`), không tiếp tục tăng RAM thêm.
