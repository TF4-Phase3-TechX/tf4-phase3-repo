# Directive 18 Workstream 2: Bằng chứng thực thi Storage và lifecycle

> Thời gian thực thi: `2026-07-24T20:21:32Z`–`2026-07-24T21:44Z`  
> Phạm vi: storage observability trên production EKS, recovery snapshot, finite snapshot/S3 lifecycle, và telemetry retention tại `us-east-1`.  
> Hợp đồng bằng chứng: báo cáo này chỉ chứa các tóm tắt đã được sanitize. Output Kubernetes/AWS thô nằm ngoài repository tại `/tmp/d18-ws2-20260724T202132Z`.

## 1. Kết quả

Workstream 2 đã thực thi xong cho OpenSearch chain đang hoạt động mà không cần thay thế Pod, PVC, PV, hay EBS volume của nó:

| Mục | Trước | Sau | Kết quả |
|---|---|---|---|
| OpenSearch EBS | `vol-0024e483121338f0e`, `40 GiB gp2`, `120 IOPS`, `us-east-1b` | Cùng volume ID/AZ, `160 GiB gp3`, `3,000 IOPS`, `125 MiB/s` | Hoàn thành |
| OpenSearch PVC | `opensearch-opensearch-0`, UID `233c6ad3-c964-4032-816c-4a38d720f0f1`, request/capacity `40Gi/40Gi`, historical class `gp2` | Cùng PVC UID/PV, request/capacity `160Gi/160Gi`; immutable class vẫn là `gp2` | Hoàn thành |
| Filesystem | `40G`, `18G` đã dùng, `22G` khả dụng, `46%` | `158G`, `16G` đã dùng, khoảng `142G` khả dụng, `10%` | Mở rộng online; không cần restart Pod |
| StatefulSet | UID `27bcc0df-9cd9-46a2-bbbf-1f1c7faae489`; future claim template `gp2/20Gi` | UID `7d3a0dac-5426-4806-b96d-aa0727a10e8e`; future claim template `gp3/160Gi`; `1/1` Ready | Đã tạo lại và đồng bộ |
| OpenSearch Pod | UID `630ba280-cf27-4804-b3bd-00d41e25ec83`, Ready, restart count `2` | Cùng Pod UID, được nhận bởi StatefulSet mới, Ready, restart count vẫn `2` | Được giữ nguyên |
| OpenSearch health | `yellow`, một data node, `29` active primary shards, `18` unassigned replica shards | Cùng giá trị; không có timeout | Không có regression; yellow là trạng thái replica single-node hiện tại |
| Recovery snapshot | Không có cho migration này | `snap-0a6903e05af18a326`, nguồn `vol-0024e483121338f0e`, `40 GiB`, `completed/100%` | Được giữ lại cho đến khi hết hạn `2026-08-01` |

EBS modification bắt đầu tại `2026-07-24T21:01:00Z` và đạt `completed/100%`. Đúng một Elastic Volumes operation đã thay đổi size, type, IOPS, và throughput cùng lúc.

## 2. Nguồn và trạng thái GitOps

| Repository/state | Revision | Kết quả applied |
|---|---|---|
| Application source | `628b66e196c4f575c2b0be091ba3adf1047522e5` | OpenSearch future template `gp3/160Gi`; Jaeger `1Gi/2Gi`; OTel `100Mi/200Mi`; `kafkametrics` đã xóa; gp3 classes và lifecycle IaC đã thêm |
| External GitOps values/storage classes | `1305ee989a1d42f91661d36e6cd0b8747aead8b5` | Đã bật observability ownership của `gp2-retain`, `gp3`, và `gp3-retain` |
| External GitOps PVC reconciliation | `235c52ea45fd197b12a24c1cb6c2c4d42bab7419` | Đã thay đổi desired request của OpenSearch PVC được quản lý riêng từ `40Gi` thành `160Gi` |

Argo sync thông thường không thể thay đổi các field immutable của StatefulSet claim-template. Do đó, quá trình thực thi chỉ orphan-delete controller của StatefulSet sau khi xác nhận PVC retention là `Retain/Retain` và PV reclaim policy là `Retain`. Một Argo sync rõ ràng sau đó đã tạo StatefulSet mới và nhận diện Pod/PVC hiện có.

Sau GitOps revision `235c52e`, Argo báo cáo:

- `StatefulSet/opensearch`: `Synced/Healthy`.
- `PersistentVolumeClaim/opensearch-opensearch-0`: `Synced/Healthy`.
- Live StatefulSet: `1/1` Ready, claim template `gp3/160Gi`.

Application-level status vẫn là `OutOfSync/Healthy` chỉ vì các resource `prometheus`, Grafana `Role`, và Grafana `RoleBinding` đã tồn tại trước đó đang bị out of sync. Đây không phải là lỗi migration của OpenSearch.

## 3. Tính liên tục của Data, ingestion, và investigation

- Index count vẫn là `13` xuyên suốt quá trình kiểm tra thực thi.
- Document count tăng từ `455,581,831` trước migration lên `464,625,145` sau đó; điều này xác nhận rằng việc ghi dữ liệu vẫn tiếp tục chứ không chứng minh tính toàn vẹn từng bản ghi.
- `otel-logs-2026-07-24` tăng từ `4,065,075` lên `4,146,047` documents trong khoảng quan sát ngắn sau thay đổi.
- OpenSearch không báo cáo index write blocks nào (`{}`).
- Phân bổ sau thay đổi báo cáo khoảng `14.4 GB` index data và `141.7 GB` trống, `9%` disk utilization.
- Jaeger query trả về `17` services mà không có API errors từ `/jaeger/ui/api/services`.
- Jaeger Deployment vẫn `1/1` Ready với zero container restarts.
- OTel Collector vẫn `4/4` Ready. Across tất cả bốn agents, quét log 15 phút cuối tìm thấy zero lần xuất hiện chuỗi `error`, `refused`, hoặc `dropped`.
- Prometheus vẫn `1/1` Ready và readiness endpoint trả về `Prometheus Server is Ready.`
- Grafana vẫn `1/1` Ready và `/api/health` trả về database `ok`.
- Tính liên tục storage của Prometheus được bảo toàn: PVC `prometheus` hiện tại vẫn Bound tại `20Gi`, historical class `gp2-retain`, với cùng PV/backing volume chain được giữ lại.

Các kiểm tra này xác nhận tính liên tục service và query/ingestion paths. Chúng không thay thế cho một full application SLO observation window hay một record-level restore comparison.

## 4. Các quyết định về Resource và retention

### Workload resources

- Jaeger memory là request `1Gi`, limit `2Gi`.
- OTel Collector memory vẫn là request `100Mi`, limit `200Mi`; không áp dụng tăng memory.

### Telemetry retention

- Jaeger index cleaner được bật trên schedule `35 23 * * *`; lần thực thi quan sát gần nhất đã hoàn thành thành công. Retention được cấu hình vẫn là một ngày.
- `opensearch-otel-logs-retention` được bật trên schedule `45 23 * * *`; lần thực thi quan sát gần nhất đã hoàn thành thành công.
- `otel-logs-2026-07-24` được gắn vào policy `otel-logs-retention` trong `hot/transition`; log retention được cấu hình vẫn là ba ngày.

### Snapshot lifecycle

DLM policy `policy-08ed1dffc099481b5` là `ENABLED`:

- target tag: `D18Snapshot=true`;
- schedule: hàng ngày tại `23:15 UTC`;
- retention count: `7` snapshots.

Snapshot migration thủ công có các tag workload, purpose, workstream, source volume, change, creation, và expiry. Snapshot này không bị xóa bởi quá trình thực thi này.

### S3 lifecycle và Object Lock

Cả CloudTrail và EKS audit buckets đều giữ Object Lock `COMPLIANCE` trong `90` ngày. Cả hai đều đã bật lifecycle rule `archive-and-expire-after-compliance-floor`:

- current và noncurrent chuyển sang `GLACIER_IR` tại ngày `91`;
- current và noncurrent expiration tại ngày `365`;
- abort incomplete multipart upload sau `7` ngày.

Không có lifecycle nào rút ngắn hoặc bypass compliance floor 90 ngày.

## 5. Inventory gp2 còn lại và protected boundaries

EC2 inventory sau migration tại `us-east-1` chứa bốn gp2 volumes tổng cộng `35 GiB`, tất cả đều `available`:

| Volume | Size | State | Boundary |
|---|---:|---|---|
| `vol-0cb8c31ac039d6597` | `10 GiB` | available | PostgreSQL ownership/cutover chưa giải quyết; không thay đổi hay xóa |
| `vol-01a7d9f5b6270c06d` | `10 GiB` | available | Kafka ownership/cutover chưa giải quyết; không thay đổi hay xóa |
| `vol-0878313d6b2957e96` | `5 GiB` | available | Valkey ownership/cutover chưa giải quyết; không thay đổi hay xóa |
| `vol-0ce59bf32f9aea7d5` | `10 GiB` | available | Recovery-chain candidate đã phát hành; vẫn cần quyết định từ recovery owner |

Volume OpenSearch đang hoạt động không còn là gp2. Không thực hiện bulk cleanup đối với PostgreSQL, Kafka, Valkey, hay các artifacts recovery đã phát hành chưa được giải quyết.

## 6. Exceptions và follow-up

| Mục | Trạng thái | Follow-up cần thiết |
|---|---|---|
| Isolated restore rehearsal từ `snap-0a6903e05af18a326` | Bỏ qua | Migration này sử dụng in-place Elastic Volumes và bảo toàn production chain. Thực hiện isolated restore được owner phê duyệt trước khi tuyên bố tested restore capability. |
| Dọn dẹp migration snapshot | Mở theo design | Giữ qua rollback expiry `2026-08-01`; chỉ xóa qua approved lifecycle/owner path sau khi recovery-owner xác nhận. |
| Full application SLO observation window | Không tuyên bố | Tiếp tục monitoring bình thường; điều tra riêng bất kỳ latency/error regression nào xảy ra sau đó. |
| Application-level Argo `Synced` | Mở một phần | OpenSearch StatefulSet và PVC đã đồng bộ. Giải quyết riêng drift không liên quan của Prometheus/Grafana; không đánh đồng nó với migration này. |
| gp2 volumes available còn lại | Bị chặn bởi ownership | Giữ được ghi nhận và không thay đổi cho đến khi mỗi workload/recovery owner chọn keep, migrate, hoặc cleanup. |

## 7. Trạng thái cuối cùng của Workstream 2

OpenSearch storage migration đang hoạt động, future gp3 desired state, các quyết định resource Jaeger/OTel, recurring EBS snapshot lifecycle, audit-bucket lifecycle, và các kiểm tra telemetry retention đã hoàn thành. Identity Pod/PVC/PV production và investigation capability đã được bảo toàn.

Migration snapshot vẫn được giữ lại có chủ ý, và các gp2 volumes chưa giải quyết không phải OpenSearch vẫn được bảo vệ thay vì force-cleanup. Các mục mở đó là các boundary rõ ràng, không phải những tuyên bố hoàn thành ẩn.
