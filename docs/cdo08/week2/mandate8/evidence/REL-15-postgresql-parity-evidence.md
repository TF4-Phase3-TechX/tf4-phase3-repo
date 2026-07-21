# REL-15 PostgreSQL Data Parity Evidence

**Người thực hiện:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-15
**Subtask:** Verify PostgreSQL data parity after restore / Kiểm tra parity dữ liệu PostgreSQL sau restore
**Ngày ghi nhận:** 2026-07-21

Tài liệu này ghi lại evidence kiểm tra parity dữ liệu PostgreSQL sau restore/backfill từ PostgreSQL self-hosted trong EKS sang Amazon RDS PostgreSQL bằng AWS DMS.

Phạm vi tài liệu:

- Xác nhận DMS full-load đã hoàn tất cho toàn bộ bảng trong scope.
- Xác nhận DMS CDC đang chạy và tiếp tục apply record mới sang RDS.
- So sánh row count live giữa source và target.
- Ghi rõ các bảng đã pass, các bảng còn chênh lệch khi source vẫn nhận write, và điều kiện cần trước khi final cutover parity.

Tài liệu này không chứa plaintext credential, không in connection string có secret, và không xác nhận app cutover sang RDS.

---

## 1. Trạng thái Tổng quan

| Hạng mục             | Trạng thái  | Ghi chú                                                           |
| -------------------- | ----------- | ----------------------------------------------------------------- |
| DMS task             | PASS        | Task `techx-tf4-postgresql-forward` đang `running`.               |
| DMS full-load        | PASS        | `Progress = 100`, `Loaded = 5`, `Errored = 0`.                    |
| DMS CDC              | RUNNING     | Log ghi nhận WAL events và target apply đang tiếp diễn.           |
| Static table parity  | PASS        | `catalog.products` và `reviews.productreviews` khớp live count.   |
| Dynamic table parity | DIFF        | Các bảng `accounting` còn lệch vì source vẫn đang nhận write mới. |
| Sequence check       | PASS        | `reviews.productreviews_id_seq` trên RDS đã align với `MAX(id)`.  |
| Final frozen parity  | PENDING     | Cần chạy sau writer freeze và CDC catch-up trước cutover.         |
| App cutover          | NOT STARTED | App vẫn chưa cutover sang RDS.                                    |

---

## 2. Runtime Scope

| Trường              | Giá trị                                                                  |
| ------------------- | ------------------------------------------------------------------------ |
| Account ID          | `511825856493`                                                           |
| Region              | `us-east-1`                                                              |
| Namespace           | `techx-tf4`                                                              |
| Database            | `otel`                                                                   |
| Source PostgreSQL   | EKS deployment `postgresql`                                              |
| Target PostgreSQL   | Amazon RDS `techx-tf4-postgresql`                                        |
| RDS endpoint        | `techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com`          |
| DMS task ID         | `techx-tf4-postgresql-forward`                                           |
| DMS task ARN        | `arn:aws:dms:us-east-1:511825856493:task:7SDVOIB6RVGXJP3M5WK72BNYKY`     |
| Source endpoint ARN | `arn:aws:dms:us-east-1:511825856493:endpoint:UZXAJZANSFBARPVQFIKK5MBF4M` |
| Target endpoint ARN | `arn:aws:dms:us-east-1:511825856493:endpoint:52US7I3JLRBG7NPFNJMFSDB2KY` |

Các bảng trong phạm vi parity:

| Schema       | Table            | Ghi chú                           |
| ------------ | ---------------- | --------------------------------- |
| `accounting` | `order`          | Bảng dynamic, vẫn nhận write mới. |
| `accounting` | `orderitem`      | Bảng dynamic, vẫn nhận write mới. |
| `accounting` | `shipping`       | Bảng dynamic, vẫn nhận write mới. |
| `catalog`    | `products`       | Bảng static/low-write.            |
| `reviews`    | `productreviews` | Bảng static/low-write.            |

---

## 3. DMS Task Health Evidence

Lệnh kiểm tra:

```powershell
bash docs/cdo08/week2/mandate8/scripts/postgres/05-monitor-dms-forward.sh
```

Output DMS task status:

```json
{
    "Id": "techx-tf4-postgresql-forward",
    "Status": "running",
    "StopReason": null,
    "LastFailureMessage": null,
    "Progress": 100,
    "Loaded": 5,
    "Loading": 0,
    "Queued": 0,
    "Errored": 0,
    "Elapsed": 19536
}
```

Kết luận:

- DMS task đang chạy.
- Full-load đã hoàn tất.
- Không có table đang loading/queued.
- Không có table errored.
- Không có `LastFailureMessage` tại thời điểm kiểm tra.

---

## 4. DMS Table Statistics

Output table statistics:

| Table                    | State             | Full-load rows | Validation       | Failed records |
| ------------------------ | ----------------- | -------------: | ---------------- | -------------: |
| `catalog.products`       | `Table completed` |             10 | `No primary Key` |              0 |
| `accounting.shipping`    | `Table completed` |         178026 | `No primary Key` |              0 |
| `reviews.productreviews` | `Table completed` |             50 | `Validated`      |              0 |
| `accounting.order`       | `Table completed` |         178026 | `No primary Key` |              0 |
| `accounting.orderitem`   | `Table completed` |         326678 | `No primary Key` |              0 |

Kết luận:

- 5/5 tables trong scope đã hoàn tất full-load.
- Không có failed records từ DMS table statistics.
- DMS validation chỉ `Validated` cho `reviews.productreviews`; các bảng còn lại báo `No primary Key` từ DMS nên không dùng DMS validation làm final parity evidence cho toàn bộ bảng.
- Exact row-count parity được ghi nhận riêng ở phần live parity và cần chạy lại ở final frozen parity.

---

## 5. CDC Runtime Evidence

DMS logs gần đây ghi nhận source WAL capture và target apply vẫn đang hoạt động:

```text
Event fetched from wal log
Applied record 237753 to target
Applied record 242281 to target
Applied record 247697 to target
Applied record 252489 to target
Applied record 257733 to target
Applied record 262625 to target
Applied record 267637 to target
Applied record 273033 to target
Applied record 278185 to target
Applied record 283593 to target
Task is running
```

Kết luận:

- DMS đã qua full-load và đang chạy ongoing CDC.
- Source PostgreSQL vẫn là active write path.
- Target RDS tiếp tục nhận CDC changes từ source.

---

## 6. Live Row Count Parity

Lệnh kiểm tra:

```powershell
bash docs/cdo08/week2/mandate8/scripts/postgres/06-parity-counts.sh
```

Script cảnh báo rõ đây là live sanity check vì source chưa freeze:

```text
[WARN] SOURCE_FROZEN is not true. This is a live sanity check, not final cutover parity.
[WARN] Dynamic tables can differ while source writes and DMS CDC are still active.
```

Output row count:

```text
table                                source       target   status
accounting."order"                   190648       190668     DIFF
accounting.orderitem                 349880       349908     DIFF
accounting.shipping                  190729       190750     DIFF
catalog.products                         10           10     PASS
reviews.productreviews                   50           50     PASS
```

Diễn giải:

- `catalog.products` và `reviews.productreviews` khớp exact row count tại thời điểm live check.
- Các bảng `accounting` đang lệch trong live count vì source vẫn đang nhận write và DMS CDC vẫn đang apply.
- Đây là expected behavior trước writer freeze, không phải final parity fail.

---

## 7. Sequence Parity

Output sequence check trên RDS:

```text
 max_productreview_id | last_value | is_called
----------------------+------------+-----------
                   50 |         50 | t
(1 row)
```

Kết luận:

- `reviews.productreviews_id_seq` trên RDS đã khớp với `MAX(id)`.
- Sequence này đã sẵn sàng cho write mới sau cutover đối với bảng `reviews.productreviews`.
- Sequence check cần được chạy lại trong final frozen parity để bảo đảm trạng thái mới nhất trước cutover.

---

## 8. Bảng Chưa Thể Kết luận Final Parity

| Table                  | Trạng thái hiện tại | Lý do chưa thể kết luận final parity          | Owner bước tiếp theo |
| ---------------------- | ------------------- | --------------------------------------------- | -------------------- |
| `accounting.order`     | `DIFF` live count   | Source vẫn nhận write, CDC vẫn đang catch-up. | REL-15 cutover gate  |
| `accounting.orderitem` | `DIFF` live count   | Source vẫn nhận write, CDC vẫn đang catch-up. | REL-15 cutover gate  |
| `accounting.shipping`  | `DIFF` live count   | Source vẫn nhận write, CDC vẫn đang catch-up. | REL-15 cutover gate  |

Không bỏ qua bảng nào trong scope. Các bảng trên đã được kiểm tra, nhưng kết quả hiện tại được phân loại là live drift trước freeze.

---

## 9. Điều kiện Final Parity Trước Cutover

Final parity strict phải được chạy ở cutover gate sau khi:

1. Dừng hoặc freeze toàn bộ writer vào PostgreSQL self-hosted.
2. Đợi DMS CDC catch-up và không còn apply backlog đáng kể.
3. Chạy lại exact row count với strict mode.
4. Re-check sequence trên RDS.
5. Nếu cần, bổ sung checksum/sample record cho bảng quan trọng.

Lệnh strict parity:

```powershell
SOURCE_FROZEN=true bash docs/cdo08/week2/mandate8/scripts/postgres/06-parity-counts.sh
```

Tiêu chí pass trước cutover:

- 5/5 tables exact row count pass.
- Không còn `DIFF` ở các bảng `accounting`.
- Sequence `reviews.productreviews_id_seq` vẫn khớp với `MAX(id)`.
- DMS task vẫn `running`, `Errored = 0`, `LastFailureMessage = null`.

---

## 10. Cleanup

Temp secret `rds-admin-temp` chỉ dùng để tạo pod parity query target RDS, không commit secret value vào Git/Jira/Slack.

Sau khi chạy parity, cần cleanup temp secret nếu không còn dùng:

```powershell
kubectl -n techx-tf4 delete secret rds-admin-temp --ignore-not-found
```

Temp parity pod được script cleanup tự động sau khi chạy.

---

## 11. Kết luận

Subtask parity hiện có các evidence chính:

- DMS task đang `running`.
- DMS full-load đã hoàn tất cho 5/5 tables.
- DMS CDC đang hoạt động và apply WAL changes sang RDS.
- `catalog.products` exact row count PASS.
- `reviews.productreviews` exact row count PASS.
- `reviews.productreviews_id_seq` trên RDS đã align với dữ liệu target.
- Các bảng `accounting` có live count `DIFF` vì source vẫn đang nhận writes; đây là risk đã biết và phải xử lý bằng writer freeze + CDC catch-up trước cutover.

Kết luận vận hành:

- Chưa thực hiện app cutover.
- Chưa có final frozen parity pass.
- PM/Tech Lead có đủ thông tin để quyết định bước cutover gate: cần freeze writer, đợi CDC catch-up, chạy strict parity, sau đó mới chuyển app traffic sang RDS.
