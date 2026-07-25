# CDO08-REL-23 - Object Inventory Evidence (Subtask 1)

**Task:** CDO08-REL-23
**Ngày lấy evidence:** 2026-07-24
**Phương pháp:** Query trực tiếp trên RDS `techx-tf4-postgresql` (database `otel`), qua pod tạm `pg-inspect` (đã xoá sau khi dùng), credential production.

## Object Inventory

| Object | Kết quả |
|---|---|
| Tables | `order` (PK `order_id` text), `orderitem` (PK ghép `order_id`+`product_id`), `shipping` (PK `shipping_tracking_id` text) |
| Sequences | 0 |
| Indexes | 3 unique index tự sinh từ PK, không index phụ |
| Constraints | 3 PRIMARY KEY + 2 FOREIGN KEY, cả 2 FK đều `ON DELETE CASCADE` → `"order"` |
| Functions | 0 |
| Extensions (toàn DB `otel`) | Chỉ `plpgsql` (mặc định hệ thống) |
| Schema/table owner | `postgres` |

## Cross-Schema Dependency

Quét toàn bộ FK chạm `accounting` với đầu kia ngoài schema: 0 dòng. Xác nhận `accounting` độc lập hoàn toàn với `catalog`/`reviews`.

## Roles/Privileges

`techx_app`: SELECT, INSERT, UPDATE, DELETE, TRUNCATE trên cả 3 bảng.

## Baseline Row Counts (2026-07-24)

| Bảng | Row count |
|---|---|
| `order` | 205,891 |
| `orderitem` | 377,846 |
| `shipping` | 205,891 |

Orphan check 2 chiều (`orderitem`/`shipping` → `order`): 0 dòng.

## Validation Checklist (dùng cho mọi lần restore sau này)

| # | Kiểm tra | Điều kiện đạt |
|---|---|---|
| 1 | `order_count` | = baseline tại đúng mốc restore đang xét |
| 2 | `shipping_count` = `order_count` | Quan hệ 1:1 |
| 3 | `orderitem_count` ≥ `order_count` | ~1.83 item/order tại baseline hiện tại |
| 4 | Orphan `orderitem`→`order` | 0 dòng |
| 5 | Orphan `shipping`→`order` | 0 dòng |
| 6 | Privilege `techx_app` sau restore | Đủ 5 quyền trên cả 3 bảng, owner vẫn `postgres` |

## Kết Luận

Đã đạt cả 3 acceptance criteria của Subtask 1: có schema object inventory, không còn dependency chưa rõ, có validation checklist và expected row relationships.
