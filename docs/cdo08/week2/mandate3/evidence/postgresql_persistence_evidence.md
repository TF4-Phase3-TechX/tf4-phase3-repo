# Báo cáo Bằng chứng Lưu trữ PostgreSQL Bền vững (CDO08)

Tài liệu này cung cấp bằng chứng xác thực rằng PostgreSQL trong namespace `techx-tf4` đã được chuyển từ lưu trữ tạm theo vòng đời Pod sang lưu trữ bền vững bằng `PersistentVolumeClaim` (PVC) trên AWS EBS. Cấu hình mới giúp giảm rủi ro mất dữ liệu khi Pod PostgreSQL bị recreate, reschedule hoặc node bị drain/restart.

Phạm vi của thay đổi này là baseline persistence cho PostgreSQL. Tài liệu này không xác nhận HA, replication, backup automation hoặc migration sang managed database như RDS.

---

## 1. Xác thực Thành phần & Phạm vi

PostgreSQL đang chạy trong namespace ứng dụng `techx-tf4` dưới dạng Kubernetes Deployment.

- **Namespace**: `techx-tf4`
- **Component**: `postgresql`
- **Database image**: `postgres:17.6`
- **PVC**: `postgresql-pvc`
- **StorageClass**: `gp2` (AWS EBS)
- **Dung lượng PVC**: `10Gi`
- **Access mode**: `ReadWriteOnce` (RWO)
- **Mount path**: `/var/lib/postgresql/data`
- **PGDATA**: `/var/lib/postgresql/data/pgdata`

Ghi chú kỹ thuật: PVC/EBS có thư mục hệ thống `lost+found`, nên PostgreSQL không nên init trực tiếp trên mount point. Cấu hình `PGDATA=/var/lib/postgresql/data/pgdata` giúp PostgreSQL tạo data directory trong subfolder riêng và tránh lỗi `initdb: directory exists but is not empty`.

---

## 2. Xác thực Rollout PostgreSQL

PostgreSQL đã rollout thành công sau khi cấu hình PVC và `PGDATA`.

```bash
$ kubectl -n techx-tf4 rollout status deploy/postgresql
deployment "postgresql" successfully rolled out
```

Trạng thái Pod sau rollout:

```bash
$ kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=postgresql -o wide
NAME                        READY   STATUS    RESTARTS   AGE   IP           NODE                          NOMINATED NODE   READINESS GATES
postgresql-879c5bd4-jc744   1/1     Running   0          98s   10.0.10.27   ip-10-0-10-231.ec2.internal   <none>           <none>
```

Kết luận: PostgreSQL Pod chạy ổn định, `READY 1/1`, không có restart sau rollout.

---

## 3. Xác thực PVC Bền vững trên AWS EBS

PVC `postgresql-pvc` đã được tạo và bind thành công với storage class `gp2`.

```bash
$ kubectl -n techx-tf4 get pvc postgresql-pvc
NAME             STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   VOLUMEATTRIBUTESCLASS   AGE
postgresql-pvc   Bound    pvc-e0600223-7b8a-4bc6-ab58-bdb77e9653e0   10Gi       RWO            gp2            <unset>                 20m
```

Ý nghĩa:

- `STATUS=Bound`: Kubernetes đã provision và gắn PVC thành công với volume backend.
- `CAPACITY=10Gi`: PostgreSQL có vùng lưu trữ bền vững 10Gi.
- `ACCESS MODES=RWO`: Volume chỉ nên được mount ghi bởi một node/pod tại một thời điểm.
- `STORAGECLASS=gp2`: PVC dùng AWS EBS dynamic provisioning.

---

## 4. Xác thực PostgreSQL Init Không Còn Lỗi `lost+found`

Lần triển khai đầu tiên gặp lỗi PostgreSQL `initdb` vì PVC/EBS có sẵn thư mục `lost+found` tại mount point. Sau khi thêm `PGDATA=/var/lib/postgresql/data/pgdata`, PostgreSQL init thành công trong subdirectory `pgdata`.

Log sau khi fix:

```bash
$ kubectl -n techx-tf4 logs deploy/postgresql --tail=80
fixing permissions on existing directory /var/lib/postgresql/data/pgdata ... ok
creating subdirectories ... ok
selecting dynamic shared memory implementation ... posix
selecting default "max_connections" ... 100
selecting default "shared_buffers" ... 128MB
creating configuration files ... ok
running bootstrap script ... ok
performing post-bootstrap initialization ... ok
syncing data to disk ... ok

Success. You can now start the database server using:

    pg_ctl -D /var/lib/postgresql/data/pgdata -l logfile start

PostgreSQL init process complete; ready for start up.

2026-07-13 14:44:00.896 UTC [1] LOG:  database system is ready to accept connections
```

Kết luận: lỗi `lost+found/initdb` đã được xử lý; PostgreSQL init và start thành công.

---

## 5. Xác thực Database Schema & Table

Sau rollout, PostgreSQL có các schema/table ứng dụng cần thiết.

```bash
$ kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "\dt *.*"
                          List of relations
       Schema       |           Name           |    Type     | Owner
--------------------+--------------------------+-------------+-------
 accounting         | order                    | table       | root
 accounting         | orderitem                | table       | root
 accounting         | shipping                 | table       | root
 catalog            | products                 | table       | root
 reviews            | productreviews           | table       | root
(118 rows)
```

Các table ứng dụng chính đã tồn tại:

- `accounting.order`
- `accounting.orderitem`
- `accounting.shipping`
- `catalog.products`
- `reviews.productreviews`

Kết luận: database không ở trạng thái empty; schema/table ứng dụng đã sẵn sàng sau khi PostgreSQL start với PVC.

---

## 6. Xác thực Persistence Sau Khi Pod Bị Recreate

Để kiểm tra dữ liệu không mất theo vòng đời Pod, PostgreSQL Pod đã được xóa thủ công để Kubernetes tạo lại Pod mới.

```bash
$ kubectl -n techx-tf4 delete pod -l app.kubernetes.io/component=postgresql
pod "postgresql-879c5bd4-jc744" deleted from techx-tf4 namespace
```

Deployment rollout lại thành công:

```bash
$ kubectl -n techx-tf4 rollout status deploy/postgresql
deployment "postgresql" successfully rolled out
```

Pod mới chạy ổn định:

```bash
$ kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=postgresql -o wide
NAME                        READY   STATUS    RESTARTS   AGE   IP            NODE                          NOMINATED NODE   READINESS GATES
postgresql-879c5bd4-5fpq4   1/1     Running   0          43s   10.0.10.249   ip-10-0-10-231.ec2.internal   <none>           <none>
```

Kiểm tra lại table sau khi Pod recreate:

```bash
$ kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "\dt accounting.*"
           List of relations
   Schema   |   Name    | Type  | Owner
------------+-----------+-------+-------
 accounting | order     | table | root
 accounting | orderitem | table | root
 accounting | shipping  | table | root
(3 rows)
```

Kết luận: sau khi Pod PostgreSQL bị xóa và tạo lại, các table trong schema `accounting` vẫn tồn tại. Đây là bằng chứng runtime chính cho thấy dữ liệu PostgreSQL hiện không còn phụ thuộc trực tiếp vào vòng đời Pod.

---

## 7. Backup Trước Rollout

Trước khi deploy cấu hình PVC, một bản backup PostgreSQL đã được tạo bằng `pg_dump` để có phương án restore nếu PVC mới khởi tạo database trống hoặc rollout gây lỗi dữ liệu.

```bash
$ kubectl -n techx-tf4 exec deploy/postgresql -- pg_dump -U root -d otel > postgres_backup.sql
```

Xác thực file backup local:

```powershell
$ Get-Item .\postgres_backup.sql
Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
-a---          13/07/2026 09:17 PM        1192555 postgres_backup.sql
```

```powershell
$ Get-Content .\postgres_backup.sql -TotalCount 20
--
-- PostgreSQL database dump
--

-- Dumped from database version 17.6 (Debian 17.6-2.pgdg13+1)
-- Dumped by pg_dump version 17.6 (Debian 17.6-2.pgdg13+1)
```

Ghi chú: file `postgres_backup.sql` chỉ được giữ local để rollback/restore khẩn cấp, không commit vào repository.

---

## 8. Rủi ro & Giới hạn Hiện tại

Cấu hình hiện tại đã giải quyết baseline persistence cho PostgreSQL, nhưng chưa phải thiết kế HA đầy đủ.

Các giới hạn còn lại:

- PostgreSQL vẫn chạy `replicas: 1`, chưa có standby/replication.
- PVC `gp2` là EBS volume dạng `ReadWriteOnce`, phù hợp với một Pod ghi tại một thời điểm.
- Khi node/AZ gặp sự cố nghiêm trọng, cần thêm chiến lược backup/restore hoặc managed database để đạt RPO/RTO rõ ràng.
- Chưa có backup automation định kỳ.
- Chưa có proof restore tự động từ backup.

Khuyến nghị backlog tiếp theo:

- Xác định RPO/RTO cho dữ liệu order/accounting.
- Thiết kế backup schedule và restore drill.
- Đánh giá nâng cấp sang StatefulSet hoặc managed database nếu yêu cầu production cao hơn.

---

## 9. Rollback Plan

Nếu PostgreSQL gặp lỗi sau khi bật PVC:

1. Dùng Helm rollback về revision trước đó hoặc revert chart change.
2. Không xóa PVC nếu chưa xác nhận backup hợp lệ và chưa có approval từ Tech Lead.
3. Nếu database bị empty/missing table, restore từ backup local:

```bash
kubectl -n techx-tf4 exec -i deploy/postgresql -- psql -U root -d otel < postgres_backup.sql
```

4. Sau restore, kiểm tra lại table ứng dụng:

```bash
kubectl -n techx-tf4 exec deploy/postgresql -- psql -U root -d otel -c "\dt accounting.*"
```

---

## 10. Kết luận

PostgreSQL persistence baseline đã được xác thực thành công trên runtime EKS:

- PVC `postgresql-pvc` đã `Bound` với `10Gi`, `RWO`, `gp2`.
- PostgreSQL rollout thành công, Pod `Running`, `READY 1/1`, `RESTARTS 0`.
- Lỗi `lost+found/initdb` đã được xử lý bằng `PGDATA=/var/lib/postgresql/data/pgdata`.
- Database có các schema/table ứng dụng cần thiết.
- Sau khi xóa Pod PostgreSQL và để Deployment recreate, table `accounting.order`, `accounting.orderitem`, `accounting.shipping` vẫn tồn tại.

Kết luận: thay đổi này đáp ứng mục tiêu của task PostgreSQL PVC baseline, giúp dữ liệu PostgreSQL không còn bị mất chỉ vì Pod bị recreate/reschedule thông thường.
---
## 🛡️ CDO-07 Audit Approval Sign-Off
- **Trạng thái:** ✅ APPROVED / PASS
- **Người kiểm duyệt:** CDO-07 (Đội ngũ Auditability)
- **Ngày thực hiện:** 2026-07-16
- **Đối tượng kiểm toán:** Kiểm chứng bằng chứng Reliability, Độ bền dữ liệu (Data Durability) và EKS/Karpenter HA.
- **Chi tiết xác minh:** Đã kiểm tra trạng thái runtime của cụm EKS bằng tài khoản quyền `TF4-AuditReadOnlyAndAnalyze`. Xác nhận các PVC (gp2/gp3) đã Bound, số lượng replicas (2/2 đi kèm topology spread constraints), liveness/readiness probes hoạt động ổn định, và Karpenter tự động cấp phát node thành công. Tính toàn vẹn của Kafka event và độ bền dữ liệu của PostgreSQL sau khi xóa/khởi động lại pod đã được xác minh đầy đủ và đạt yêu cầu.

