# D19-PERF-05 — Tuning Design: Nâng Trần Throughput Mà Không Tăng Node

**Task:** C0G-111  
**Baseline reference:** D19-PERF-04  
**Ngày:** 2026-07-23  

---

## Bối cảnh

Baseline ramp test (C0G-109) xác định điểm gãy hệ thống ở mức 75–125 users.  
Mục tiêu: nâng trần thông lượng lên 150–200+ users trên cùng 5 Nodes EKS mà không bổ sung tài nguyên phần cứng.

---

## Đánh Giá Candidate Tuning

### Nhóm 1: Application Concurrency

| Candidate | Áp dụng? | Lý do quyết định |
|---|---|---|
| worker count | ✅ Chọn | gRPC ThreadPoolExecutor của `product-reviews` cứng ở 10 → thread starvation khi tải > 50 users |
| thread pool | ✅ Chọn | Pool size phải khớp với connection pool để tránh thread block chờ conn |
| async concurrency | ❌ Không áp dụng | Cả Go và Python đều là synchronous blocking I/O; refactor sang async nằm ngoài phạm vi sprint |
| in-flight request cap | ❌ Không áp dụng | Nghẽn nằm ở DB latency, không phải backlog queue |
| queue size | ❌ Không áp dụng | Ưu tiên xử lý bottleneck tầng DB trước khi điều chỉnh queue |
| backpressure | ❌ Không áp dụng | Áp dụng sau khi DB bottleneck được giải quyết |

### Nhóm 2: Connection Efficiency

| Candidate | Áp dụng? | Lý do quyết định |
|---|---|---|
| DB connection pool | ✅ Chọn | Python mở/đóng conn mỗi query; Go pool không giới hạn — 2 điểm nghẽn trực tiếp |
| connection reuse | ✅ Chọn | ThreadedConnectionPool Python là cơ chế reuse; Go `database/sql` reuse nếu có giới hạn |
| downstream pool sizing | ✅ Chọn | Go MaxOpenConns=20, Python maxconn=50 → tổng conn tối đa 90 (2x20 Go + 50 Python), thực tế sử dụng an toàn dưới giới hạn 79 connections của RDS |
| idle timeout | ✅ Chọn | Go SetConnMaxIdleTime(2m) + SetConnMaxLifetime(5m) → tránh stale connections |
| HTTP keep-alive | ❌ Không áp dụng | Giao tiếp nội bộ qua gRPC (HTTP/2, có multiplexing sẵn) |
| TLS connection reuse | ❌ Không áp dụng | TLS session resumption do RDS driver xử lý tự động |

### Nhóm 3: Kubernetes / HPA

| Candidate | Áp dụng? | Lý do quyết định |
|---|---|---|
| HPA target | ❌ Không áp dụng | Bottleneck là DB conn pool và thread starvation, không phải CPU Pod thiếu |
| scale-up behavior | ❌ Không áp dụng | Scale-out trước khi fix pool sẽ nhân bội vấn đề |
| scale-down stabilization | ❌ Không áp dụng | Không liên quan khi bottleneck là application-level |
| min/max replicas | ❌ Không áp dụng | Ràng buộc cứng: không tăng node |
| CPU/memory requests sát measured usage | ❌ Không áp dụng | Thuộc phạm vi rightsizing (C0G-119) |
| pod distribution | ❌ Không áp dụng | Ràng buộc cứng: không tăng node |

### Nhóm 4: Runtime

| Candidate | Áp dụng? | Lý do quyết định |
|---|---|---|
| server worker settings | ✅ Chọn | gRPC max_workers là server worker setting trực tiếp cần nâng |
| GC mode | ❌ Không áp dụng | Go GC default (GOGC=100) đủ; không có heap pressure trong baseline |
| heap sizing | ❌ Không áp dụng | Không có OOMKill trong baseline |
| process count | ❌ Không áp dụng | Mỗi Pod 1 process — không phải mô hình multi-process |
| event-loop tuning | ❌ Không áp dụng | Không dùng asyncio/uvloop; Python dùng thread-based gRPC |

---

## Tuning Changes Đã Chọn

### TC-01 — Giới hạn Connection Pool cho Go `product-catalog`

| Trường | Nội dung |
|---|---|
| **Bottleneck** | Go `database/sql` mặc định MaxOpenConns=0 (vô hạn). Tải > 100 users → Go mở ồ ạt TCP conn mới tới RDS, vượt giới hạn 79 connections của RDS → lỗi `too many clients already` |
| **Expected throughput impact** | Ngăn cascade failure; cart/checkout/payment giữ được kết nối ổn định → hệ thống trụ đến 150–200 users mà không sập DB |
| **Resource impact** | TCP connections tới RDS giảm; CPU RDS giảm overhead; Pod memory không đổi |
| **Correctness risk** | **Thấp** — nếu MaxOpenConns=20 quá nhỏ, request chờ trong pool (latency tăng nhẹ), không gây data corruption |
| **Rollback** | `git revert` commit; hoặc xóa 4 dòng SetMax* trong initDatabase() và redeploy |
| **Test gate** | Tỷ lệ lỗi ≤ 2% tại 150 users; không có lỗi `too many clients` trong RDS log |
| **Source-of-truth file** | `techx-corp-platform/src/product-catalog/main.go` — hàm `initDatabase()` |

```go
db.SetMaxOpenConns(20)
db.SetMaxIdleConns(5)
db.SetConnMaxLifetime(5 * time.Minute)
db.SetConnMaxIdleTime(2 * time.Minute)
```

---

### TC-02 — DB Connection Pool cho Python `product-reviews`

| Trường | Nội dung |
|---|---|
| **Bottleneck** | psycopg2.connect() gọi mới trên mỗi query → TCP + TLS Handshake mỗi request → CPU RDS ~100% ở 75 users, latency query từ 20ms lên > 1.5 giây |
| **Expected throughput impact** | Loại bỏ overhead bắt tay; latency giảm từ > 1.5 giây xuống < 20ms; CPU RDS giải phóng → phục vụ được 3–4× concurrent users |
| **Resource impact** | Pool duy trì 5–50 idle conn tới RDS; Pod CPU giảm; Pod memory tăng không đáng kể |
| **Correctness risk** | **Trung bình** — nếu không rollback() trước khi trả conn về pool → idle-in-transaction. Đã mitigated bằng context manager tự động rollback() trong __exit__ |
| **Rollback** | `git revert` commit; hoặc khôi phục database.py dùng psycopg2.connect() trực tiếp và redeploy |
| **Test gate** | p99 Browse ≤ 500ms tại 125 users; log không có `PoolError: exhausted` |
| **Source-of-truth file** | `techx-corp-platform/src/product-reviews/database.py` |

```python
from psycopg2 import pool as pg_pool
_pool = pg_pool.ThreadedConnectionPool(minconn=5, maxconn=50, dsn=DB_DSN)

class DBConnection:
    def __enter__(self):
        self.conn = _pool.getconn()
        return self.conn
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.rollback()  # đảm bảo transaction sạch
        _pool.putconn(self.conn)
        return False
```

---

### TC-03 — Nâng gRPC Worker Threads Python `product-reviews` (10 → 50)

| Trường | Nội dung |
|---|---|
| **Bottleneck** | ThreadPoolExecutor(max_workers=10) cứng. Khi 10 threads chờ DB/Bedrock (I/O blocking), request mới xếp hàng ở tầng gRPC → p99 tăng dù server chưa tốn CPU |
| **Expected throughput impact** | 50 workers xử lý đồng thời I/O blocking → throughput gRPC tăng ~5×; p99 dự kiến giảm 60–80% ở 100+ users |
| **Resource impact** | 40 thread bổ sung ≈ 320MB stack/Pod — trong giới hạn memory request; CPU không tăng (GIL nhường nhau với I/O) |
| **Correctness risk** | **Thấp** — Python GIL đảm bảo thread-safe; psycopg2 ThreadedConnectionPool thread-safe; Bedrock SDK thread-safe theo AWS docs |
| **Rollback** | `git revert` commit; hoặc sửa lại max_workers=10 trong product_reviews_server.py và redeploy |
| **Test gate** | Không có gRPC timeout ở 125 users; p99 AI Assistant ≤ SLO; active_threads không vượt 50 |
| **Source-of-truth file** | `techx-corp-platform/src/product-reviews/product_reviews_server.py` |

```python
server = grpc.server(futures.ThreadPoolExecutor(max_workers=50))
```

---

## Change Sequence (thứ tự triển khai bắt buộc)

```
[1] TC-01 → main.go (Go product-catalog)
      Lý do: Bảo vệ RDS trước. Nếu RDS sập thì TC-02 và TC-03 không có ý nghĩa.

[2] TC-02 → database.py (Python product-reviews)
      Lý do: Phải có pool trước khi nâng worker count.
      Nếu max_workers=50 nhưng maxconn=1 thì 49 threads block chờ conn ngay lập tức.

[3] TC-03 → product_reviews_server.py (Python product-reviews)
      Lý do: Nâng worker count sau khi pool đã đủ chỗ (maxconn=50 = max_workers=50).
```

Tất cả 3 TC commit vào 1 PR duy nhất → deploy 1 lần → tránh trạng thái half-applied.

---

## Acceptance Criteria

- [x] Có ít nhất một tuning nhắm đúng bottleneck — TC-01 (RDS conn), TC-02 (Python pool), TC-03 (thread starvation)
- [x] Không tăng node — toàn bộ thay đổi ở tầng application config
- [x] Có expected result — mỗi TC có con số kỳ vọng cụ thể
- [x] Có risk analysis — mỗi TC có correctness risk và mức độ (Thấp/Trung bình)
- [x] Có rollback — mỗi TC có bước rollback cụ thể
- [x] Có reviewer sign-off — Tech Lead approved
- [x] Có change sequence — xem mục Change Sequence ở trên
- [x] Có đường dẫn thư mục logs kiểm thử: [log/](./log/)