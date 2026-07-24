# D16-PERF-05 (C0G-92) — Kiểm chứng cải thiện p95/p99 dưới sustained load

- **Owner:** Phan Minh Tuấn (CDO-04)
- **Trạng thái:** INCONCLUSIVE — chạy sạch (không bị deploy chen ngang, không lỗi hạ tầng), độ trễ cải thiện rõ rệt so với lần đo trước nhưng vẫn chưa đạt budget tuyệt đối, do cùng một nguyên nhân gốc (`frontend` HPA ceiling) vẫn chưa được xử lý. Cần Tech Lead/PM quyết định về việc nâng `maxReplicas` trước khi có thể đóng task này với kết quả PASS.
- **Phụ thuộc:** D16-DEV-01 (C0G-91) — 4 PR đã merge, xác nhận đang chạy live tại thời điểm đo:
  - PR #324 `411e9a2` — gộp N request Currency (non-USD) thành 1 `BatchConvert`.
  - PR #558 `496abcd` — revert cơ chế 2-worker song song gọi Product Catalog trong Checkout, chỉ giữ tối đa 1 request in-flight/Checkout.
  - PR #565 `14da184` — bỏ N request `GetProduct` thừa ở bước confirmation, bỏ gọi `Currency.Convert` no-op cho item giá USD.
  - PR #592 `9fcb588` — giới hạn connection pool PostgreSQL của Product Catalog (`MaxOpenConns=20`/`MaxIdleConns=5`).
  - PR #600 `b536a75` — tối ưu cân bằng request tới Product Catalog từ `frontend` (đã ổn định là bản đang chạy, không còn ở giữa quá trình rollout như lần đo trước).
- **Tài liệu hợp đồng tải (không sửa ở đây):** `D16-PERF-01-SUSTAINED-LOAD-CONTRACT.md` — dùng chung load profile, tỷ trọng task và endpoint mix.
- **Về baseline:** không còn baseline D16-PERF-02 chính thức trong repo. Gate theo **latency budget tuyệt đối** ở D16-PERF-01 §5 thay vì so sánh before/after.

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
- `frontend` vẫn bị kẹt ở ceiling cứng (`maxReplicas=3`) suốt phần lớn run, dao động **66%–237%/70%** — cùng loại nghẽn năng lực đã xác nhận ở lần đo trước, chưa được xử lý (chưa có thay đổi cấu hình `maxReplicas`).

## Evidence

### Latency so với budget tuyệt đối D16-PERF-01 §5 (`requests.csv`, toàn bộ cửa sổ 04:11:08Z–04:58:54Z)

| Flow | Requests | Failures | Success rate | p50 | p95 | p99 | Budget p95 | Budget p99 | Kết quả |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| Browse `GET /` | 8,306 | 18 | 99.78% | 190ms | 1,100ms | 1,800ms | <500ms | <800ms | **FAIL cả 2**, nhưng cải thiện rõ so với lần trước (2,300/3,000ms) |
| Cart `GET /api/cart` | 9,920 | 15 | 99.85% | 140ms | 1,100ms | 1,800ms | <700ms | <1,000ms | **FAIL cả 2**, cải thiện (từ 2,300/3,000ms) |
| Cart `POST /api/cart` | 34,396 | 44 | 99.87% | 120ms | 1,000ms | 1,600ms | <700ms | <1,000ms | **FAIL cả 2**, cải thiện (từ 2,400/3,100ms), p95 chỉ còn vượt budget đúng 300ms |
| Checkout `POST /api/checkout` | 12,404 | 45 | 99.64% | 380ms | 1,600ms | 2,400ms | <1,000ms | <1,500ms | **FAIL cả 2**, cải thiện mạnh (từ 3,000/3,900ms) |
| Tổng hợp (toàn bộ route) | 140,261 | 212 (0.15%) | 99.85% | 180ms | 1,300ms | 2,400ms | — | — | chỉ để tham khảo |

Mọi flow vẫn FAIL budget tuyệt đối, nhưng **độ trễ đã giảm gần một nửa** so với lần đo trước ở mọi flow — đúng hướng cải thiện, chỉ còn bị chặn bởi nghẽn năng lực `frontend`. **Correctness/success-rate PASS rõ và tốt hơn lần trước**: Browse/Cart đều ≥99.5%, Checkout 99.64% (≥ SLO 99.0%), aggregate error rate 0.15% (tốt hơn 0.23% của lần trước).

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

**INCONCLUSIVE — nhưng là lần đo sạch nhất và có tín hiệu cải thiện rõ ràng nhất từ trước tới nay.**

1. Mọi gate p95/p99 tuyệt đối vẫn FAIL, nhưng khoảng cách với budget đã thu hẹp đáng kể (độ trễ giảm gần một nửa so với lần đo trước ở mọi flow); Cart `POST` p95 chỉ còn vượt budget 300ms.
2. Nguyên nhân xác nhận vẫn là `frontend` HPA ceiling (`maxReplicas=3`, 66-237%/70%), không phải do code checkout (`checkout` CPU thấp suốt run). Đây là lần thứ 2 xác nhận cùng một nút thắt trên 2 lần đo độc lập, ở 2 trạng thái code khác nhau.
3. **Lần đo này không có vấn đề phương pháp**: không bị deploy nào chen ngang (0 warning event), SHA giữ nguyên suốt cửa sổ đo — khác với lần trước.
4. Correctness/success-rate tiếp tục đạt và tốt hơn lần trước (Checkout 99.64%, aggregate error 0.15%).

**Kết luận thực tế: bộ fix D16-DEV-01 (kể cả PR #600) đang hoạt động đúng hướng và cải thiện rõ rệt, nhưng chưa đủ để đạt budget tuyệt đối vì bị chặn bởi năng lực `frontend`.** Việc đóng ticket với kết quả PASS phụ thuộc vào xử lý ceiling này, không phải vào code checkout nữa:

- **Cần nâng `maxReplicas` của `frontend`** (node còn dư CPU theo các lần kiểm tra trước, không cần thêm node) — đây là điều kiện tiên quyết duy nhất còn lại để có cơ hội đạt budget tuyệt đối ở lần đo tiếp theo. Cần người phụ trách Cost/Capacity duyệt.
- Không cần escalate thêm về vấn đề coordination/deploy-chen-ngang nữa — lần này đã sạch.

## Acceptance criteria (theo `task-tuan.md`)

- [x] Dùng cùng load contract — đúng tỷ trọng task/endpoint mix, đủ 4 phase (warm-up 5', ramp 5', sustained 25', stability 10').
- [x] Số lượng request đủ ngưỡng tối thiểu — Checkout 12,404 request, Browse/Cart đều vượt xa ngưỡng tối thiểu 1,000 mẫu/sustained window.
- [ ] p99 giảm theo improvement target (≥20% Checkout) — không đánh giá được, không có baseline hợp lệ để tính delta.
- [ ] p95 đạt budget tuyệt đối (§5) — **FAIL**, cả 3 flow vượt budget, nhưng khoảng cách đã thu hẹp mạnh so với lần trước.
- [ ] p99 đạt budget tuyệt đối (§5) — **FAIL**, tương tự.
- [x] Correctness giữ nguyên — **PASS**.
- [x] Error rate không tăng đáng kể — **PASS so với SLO**: Browse 99.78%, Cart 99.85%/99.87%, Checkout 99.64%, aggregate 0.15%.
- [x] Node count không tăng — 4 node, ổn định suốt run.
- [x] Node-hours không tăng — nhất quán với node count ổn định.
- [x] Không có OOM/Pending regression mới — không quan sát thấy; 0 restart, 0 warning event toàn namespace.
- [x] SHA đang review được giữ nguyên suốt cửa sổ đo — **PASS**, không có deploy chen ngang lần này.

Kết quả chung: resource, correctness, error-rate và tính toàn vẹn phương pháp đo đều đạt; chỉ còn gate latency tuyệt đối chưa đạt, do một nguyên nhân đã xác định rõ và nằm ngoài phạm vi code checkout (`frontend` HPA ceiling).
