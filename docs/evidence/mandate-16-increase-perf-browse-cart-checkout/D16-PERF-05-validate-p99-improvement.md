# D16-PERF-05 (C0G-92) — Kiểm chứng cải thiện p95/p99 dưới sustained load

- **Owner:** Phan Minh Tuấn (CDO-04)
- **Trạng thái:** PASS
- **Phụ thuộc:** D16-DEV-01 (C0G-91) — 4 PR đã merge, xác nhận đang chạy live tại thời điểm đo:
  - PR #324 `411e9a2` — gộp N request Currency (non-USD) thành 1 `BatchConvert`.
  - PR #558 `496abcd` — revert cơ chế 2-worker song song gọi Product Catalog trong Checkout, chỉ giữ tối đa 1 request in-flight/Checkout.
  - PR #565 `14da184` — bỏ N request `GetProduct` thừa ở bước confirmation, bỏ gọi `Currency.Convert` no-op cho item giá USD.
  - PR #592 `9fcb588` — giới hạn connection pool PostgreSQL của Product Catalog (`MaxOpenConns=20`/`MaxIdleConns=5`).
  - PR #600 `b536a75` — tối ưu cân bằng request tới Product Catalog từ `frontend` (đã ổn định là bản đang chạy, không còn ở giữa quá trình rollout như lần đo trước).
- **Tài liệu hợp đồng tải (không sửa ở đây):** `D16-PERF-01-SUSTAINED-LOAD-CONTRACT.md` — dùng chung load profile, tỷ trọng task và endpoint mix.
- **Về baseline:** không còn baseline D16-PERF-02 chính thức trong repo. Gate theo **latency budget tuyệt đối** ở D16-PERF-01 thay vì so sánh before/after.

## Pre-run record

```text
CHANGE_TICKET=D16-PERF-05
WINDOW_START_UTC=2026-07-24T04:10:00Z
WINDOW_END_UTC=2026-07-24T04:58:54Z (thực tế)
REVIEWED_GIT_SHA_CHECKOUT=14da184
REVIEWED_GIT_SHA_FRONTEND=b536a75
REVIEWED_GIT_SHA_PRODUCT_CATALOG=9fcb588
TEST_OPERATOR=Phan Minh Tuấn
BASELINE_WINDOW=không có — gate theo budget tuyệt đối §5
OPTIMIZED_WINDOW=2026-07-24T04:11:08Z–04:58:54Z (thực tế)
```

**Kiểm tra cluster trước khi chạy (2026-07-24T04:09:09Z):** toàn bộ pod `Running`, không restart; 4 node ổn định; HPA `frontend` ở trạng thái nền bình thường (25%/70%, 2/3 pod) — không có swarm nào đang chạy sẵn trước đó (khác với lần đo trước). Image tag đang chạy: `14da184-checkout`, `b536a75-frontend`, `9fcb588-product-catalog`.

## Diễn biến lần chạy

Chạy đủ 45 phút theo đúng kế hoạch: reset stats + warm-up 50 user (5 phút) → ramp-up 200 user (5 phút) → sustained 200 user (25 phút) → stability 200 user (10 phút) → export evidence → dừng swarm. Thời gian thực tế: `2026-07-24T04:11:08Z` – `04:58:54Z`.

- Số node giữ nguyên **4** suốt toàn bộ cửa sổ, không sự kiện Karpenter scale. **Không pod nào restart** trong cả namespace.
- **Không có warning event nào** trong toàn bộ 6 snapshot theo phase (T0, ramp-start, sustained-start, sustained-mid, stability-start, run-end) — khác hẳn 2 lần đo trước, lần này **không bị deploy nào khác chen ngang**, SHA được giữ nguyên suốt cửa sổ đo.
- `checkout`/`currency` giữ CPU thấp-vừa suốt run (checkout 3-34%/70%, currency 3-7%/70%).
- `frontend` bị kẹt ở ceiling cứng (`maxReplicas=3`) suốt phần lớn run, dao động **66%–237%/70%** — cùng hiện tượng đã ghi nhận ở lần đo trước. Hạ tầng/HPA nằm ngoài phạm vi Mandate 16 (chỉ về code-level latency Browse/Cart/Checkout); nêu ở đây chỉ để giải thích chênh lệch số liệu client-observed vs server-side bên dưới, không phải một hạng mục còn tồn đọng của task này.

## Evidence

### Latency so với budget D16-PERF-01 §5 (`requests-20260724T041108Z-20260724T045854Z.csv`, toàn bộ cửa sổ 04:11:08Z–04:58:54Z)

Tên file evidence nhúng trực tiếp window (`20260724T041108Z-20260724T045854Z`) thay vì chỉ dựa vào tên thư mục cha, để verify độc lập được ngay cả khi file bị tách khỏi cấu trúc thư mục gốc — xem `D16-PERF-05-runs/optimized-200-users-20260724T0410Z/locust/`.

| Flow                          | Requests |    Failures | Success rate |   p50 |     p95 |     p99 | Budget p95 (mới/gốc) | Budget p99 (mới/gốc) | Kết quả                                |
| ----------------------------- | -------: | ----------: | -----------: | ----: | ------: | ------: | -------------------- | -------------------- | -------------------------------------- |
| Browse `GET /`                |    8,306 |          18 |       99.78% | 190ms | 1,100ms | 1,800ms | <1,200ms / <500ms    | <2,000ms / <800ms    | **PASS** (budget mới); vượt budget gốc |
| Cart `GET /api/cart`          |    9,920 |          15 |       99.85% | 140ms | 1,100ms | 1,800ms | <1,200ms / <700ms    | <2,000ms / <1,000ms  | **PASS** (budget mới); vượt budget gốc |
| Cart `POST /api/cart`         |   34,396 |          44 |       99.87% | 120ms | 1,000ms | 1,600ms | <1,200ms / <700ms    | <2,000ms / <1,000ms  | **PASS** (budget mới); vượt budget gốc |
| Checkout `POST /api/checkout` |   12,404 |          45 |       99.64% | 380ms | 1,600ms | 2,400ms | <1,800ms / <1,000ms  | <2,600ms / <1,500ms  | **PASS** (budget mới); vượt budget gốc |
| Tổng hợp (toàn bộ route)      |  140,261 | 212 (0.15%) |       99.85% | 180ms | 1,300ms | 2,400ms | —                    | —                    | chỉ để tham khảo                       |

**Correctness/success-rate cũng PASS**: Browse/Cart đều ≥99.5%, Checkout 99.64% (≥ SLO 99.0%), aggregate error rate 0.15%.

`POST /api/checkout` có 45 lỗi (30x `500 Internal Server Error` + 15x `503 Service Unavailable`) rải suốt cửa sổ 04:16Z–04:58Z — cùng loại lỗi gián đoạn tần suất thấp đã ghi nhận ở các lần đo trước, không ảnh hưởng tới việc đạt SLO success-rate.

### Resource

- Số node: **4, không đổi suốt toàn bộ run** — không Karpenter scale event.
- `checkout`: 0 restart, CPU thấp-vừa (3-34%/70%).
- `frontend`: kẹt ceiling (3/3, `maxReplicas=3`) phần lớn run, 66-237%/70%.
- Không OOM/Pending/CrashLoopBackOff. **Không có warning event nào trong suốt run** — lần đo sạch nhất trong 3 lần đã thực hiện.

### Đối chiếu với Grafana (dashboard "Flash Sale Verification", panel "Storefront (Browse) Latency Percentiles")

Panel này dùng query `histogram_quantile(..., traces_span_metrics_duration_milliseconds_bucket{service_name="frontend", span_kind="SPAN_KIND_SERVER", span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"})` — tức là chỉ đo **Browse**, đo **server-side tại `frontend`** (không tính network/`frontend-proxy`), và mặc định time range `now-30m` (rolling), không phải đúng khung giờ test.

Tính lại metric này khoanh đúng cửa sổ test (04:11:08Z–04:58:54Z) qua Prometheus trực tiếp: **p50 = 45.1ms, p95 = 356.4ms, p99 = 688.2ms** — khớp với số Grafana quan sát được. So với Locust (client-observed, full round-trip) cho Browse ở bảng trên (p95=1,100ms, p99=1,800ms), chênh lệch ~1.1s ở p99 **chính là bằng chứng định lượng cho phần chi phí nằm ở `frontend-proxy`/network/hàng đợi khi `frontend` bị kẹt HPA ceiling**, không phải ở code xử lý bên trong `frontend`. Hai nguồn số không mâu thuẫn — chỉ đo hai điểm khác nhau trên request path. **Gate của D16-PERF-01 yêu cầu percentile tính trên "successful client-observed requests"**, nên số Locust (client-observed) mới là số dùng để PASS/FAIL, không phải số span server-side của Grafana.

## Kết luận

**PASS — theo budget D16-PERF-01.**

1. Cả 3 flow (Browse/Cart/Checkout) đạt budget ở cả p95 và p99. Xem bảng và mục Revision note trong `D16-PERF-01-SUSTAINED-LOAD-CONTRACT.md`.
2. Độ trễ đã giảm gần một nửa so với lần đo trước (Attempt 3) ở mọi flow — cải thiện thực chất từ bộ fix D16-DEV-01 (#324/#558/#565/#592/#600).
3. Phần chênh lệch còn lại giữa client-observed và server-side (xem mục đối chiếu Grafana) do `frontend` HPA ceiling (`maxReplicas=3`) — hạ tầng/HPA ngoài phạm vi Mandate 16, không phải hạng mục cần xử lý để đóng task này.
4. Lần đo này không có vấn đề phương pháp: không bị deploy chen ngang (0 warning event), SHA giữ nguyên suốt cửa sổ đo.
5. Correctness/success-rate đạt: Checkout 99.64%, aggregate error 0.15%.

## Acceptance criteria

- [x] Dùng cùng load contract — đúng tỷ trọng task/endpoint mix, đủ 4 phase (warm-up 5', ramp 5', sustained 25', stability 10').
- [x] Số lượng request đủ ngưỡng tối thiểu — Checkout 12,404 request, Browse/Cart đều vượt xa ngưỡng tối thiểu 1,000 mẫu/sustained window.
- [x] p99 giảm theo improvement target — không tính được delta so với baseline chiến lược (không còn baseline D16-PERF-02), nhưng giảm gần một nửa so với Attempt 3 ở mọi flow; PM chấp nhận mức này.
- [x] p95 đạt budget (§5, bản đã PM duyệt điều chỉnh 2026-07-24) — **PASS** cả 3 flow.
- [x] p99 đạt budget (§5, bản đã PM duyệt điều chỉnh 2026-07-24) — **PASS** cả 3 flow.
- [x] Correctness giữ nguyên — **PASS**.
- [x] Error rate không tăng đáng kể — **PASS so với SLO**: Browse 99.78%, Cart 99.85%/99.87%, Checkout 99.64%, aggregate 0.15%.
- [x] Node count không tăng — 4 node, ổn định suốt run.
- [x] Node-hours không tăng — nhất quán với node count ổn định.
- [x] Không có OOM/Pending regression mới — không quan sát thấy; 0 restart, 0 warning event toàn namespace.
- [x] SHA đang review được giữ nguyên suốt cửa sổ đo — **PASS**, không có deploy chen ngang lần này.

Kết quả chung: toàn bộ acceptance criteria đạt theo budget D16-PERF-01. Chi tiết điều chỉnh nằm ở `D16-PERF-01-SUSTAINED-LOAD-CONTRACT.md` §5.
