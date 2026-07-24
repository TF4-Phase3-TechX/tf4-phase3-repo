# D16-PERF-05 (C0G-92) — Kiểm chứng cải thiện p95/p99 dưới sustained load

- **Owner:** Phan Minh Tuấn (CDO-04)
- **Trạng thái:** INCONCLUSIVE — đã chạy đủ với evidence đầy đủ, nhưng có 2 vấn đề khiến chưa thể kết luận PASS/FAIL dứt khoát. Cần Tech Lead/PM quyết định trước khi chạy lại lần tiếp theo. Xem mục Kết luận bên dưới.
- **Phụ thuộc:** D16-DEV-01 (C0G-91) — toàn bộ 4 PR đã merge và xác nhận đang chạy live tại thời điểm đo:
  - PR #324 `411e9a2` — gộp N request Currency (non-USD) thành 1 `BatchConvert`.
  - PR #558 `496abcd` — revert cơ chế 2-worker song song gọi Product Catalog trong Checkout (gây quá tải Product Catalog dưới load), chỉ giữ tối đa 1 request in-flight/Checkout.
  - PR #565 `14da184` — bỏ N request `GetProduct` thừa ở bước confirmation, bỏ gọi `Currency.Convert` no-op cho item giá USD.
  - PR #592 `9fcb588` — giới hạn connection pool PostgreSQL của Product Catalog (`MaxOpenConns=20`/`MaxIdleConns=5`).
- **Tài liệu hợp đồng tải (không sửa ở đây):** `D16-PERF-01-SUSTAINED-LOAD-CONTRACT.md` — dùng chung load profile, tỷ trọng task và endpoint mix.
- **Về baseline:** file baseline D16-PERF-02 gốc đã bị xóa khỏi repo trước khi phiên đo này bắt đầu, không còn baseline chính thức nào để so sánh delta trước/sau. Lần đo này gate theo **latency budget tuyệt đối** ở D16-PERF-01 §5 thay vì so sánh before/after. Các lần đo trước đó (nếu có) không còn giá trị tham chiếu và không được dùng lại trong tài liệu này.

## Pre-run record

```text
CHANGE_TICKET=D16-PERF-05
WINDOW_START_UTC=2026-07-24T02:20:00Z
WINDOW_END_UTC=2026-07-24T03:05:00Z
REVIEWED_GIT_SHA_CHECKOUT=14da184
REVIEWED_GIT_SHA_FRONTEND=14da184
REVIEWED_GIT_SHA_PRODUCT_CATALOG=9fcb588
TEST_OPERATOR=Phan Minh Tuấn
INCIDENT_CHANNEL=đã báo TF giữ chỗ load-generator trước khi chạy
BASELINE_WINDOW=không có — file baseline D16-PERF-02 đã bị xóa, gate theo budget tuyệt đối §5
OPTIMIZED_WINDOW=2026-07-24T02:20:56Z–03:09:21Z (thực tế)
```

**Kiểm tra cluster trước khi chạy (2026-07-24T02:17:02Z):** image tag đang chạy khớp đúng REVIEWED_GIT_SHA (`14da184-checkout`, `14da184-frontend`, `9fcb588-product-catalog`); toàn bộ pod `Running`, không restart; 4 node ổn định, còn dư CPU (15-61%). HPA `frontend` dao động mạnh ngay cả ở nền (25%→355%/70%, 2-3/3 pod) do đã có một swarm ~50 user chạy sẵn trên `load-generator` trước khi bắt đầu — không phải traffic nền thông thường.

## Diễn biến lần chạy

Chạy đủ 45 phút theo đúng kế hoạch: reset stats + warm-up 50 user (5 phút) → ramp-up lên 200 user (5 phút) → sustained 200 user (25 phút) → stability 200 user (10 phút) → export evidence → dừng swarm. Tổng thời gian thực tế: `2026-07-24T02:20:56Z` – `03:09:21Z`.

- Số node giữ nguyên **4** suốt toàn bộ cửa sổ, không có sự kiện Karpenter scale. Không pod nào restart trong cả namespace.
- `checkout`/`currency` giữ CPU thấp suốt run (checkout 4-36%/70%, currency 4-6%/70%) — code checkout không hề bị áp lực CPU.
- `frontend` bị kẹt ở ceiling cứng (`maxReplicas=3`) suốt toàn bộ run, dao động **79%–273%/70%** — đúng loại nghẽn năng lực đã cảnh báo trước khi chạy, không liên quan đến code checkout.

### ⚠️ Deploy chen ngang giữa cửa sổ đo — SHA đang test không giữ nguyên suốt run

Dù đã báo TF giữ chỗ `load-generator` trước, **`frontend` vẫn bị một PR khác, không liên quan, ghi đè hoàn toàn giữa lúc đang đo**:

- PR #600 `b536a75` "perf(frontend): balance product catalog requests safely" merge vào `main` lúc **02:46:08Z** — 14 phút sau khi sustained window bắt đầu.
- GitOps rollout bắt đầu **02:54:07Z**, hoàn tất **02:57:24Z** (pod `14da184-frontend` cuối cùng bị xóa) — toàn bộ nằm trong sustained window (02:32:28–02:57:28Z), ngay trước stability window (02:58:43–03:08:43Z).
- Hệ quả: khoảng 22/25 phút đầu của sustained window chạy trên `14da184-frontend` (đúng SHA đã review); ~3 phút cuối sustained **và toàn bộ 10 phút stability** chạy trên `b536a75-frontend` — build chưa từng được đưa vào pre-run record.
- Một deploy khác (`frontend-proxy` ReplicaSet mới) bị chặn hoàn toàn bởi policy Kyverno `require-signed-techx-images` (`MANIFEST_UNKNOWN`) lúc 02:54Z và 03:05Z — không tạo được pod nên không ảnh hưởng dữ liệu, nhưng xác nhận có thêm hoạt động deploy khác nhắm đúng các service đang được test trong cùng cửa sổ.
- Theo đúng rule của `D16-PERF-01` ("Any change invalidates comparability and requires both runs to be repeated"), đây là vi phạm hợp đồng đo cần công khai, không lặng lẽ bỏ qua. Kiểm tra `failures.csv` không thấy tăng đột biến lỗi tập trung quanh 02:54–02:58Z (lỗi rải đều suốt 02:21Z–03:09Z) — nhưng riêng dữ liệu của stability window không thể quy cho SHA đã review.

### Jaeger trace — không lấy được trong phiên này

Nhiều lần thử port-forward tới `techx-observability/jaeger` (base path `/jaeger/ui/api/traces`) đều bị rớt kết nối hoặc trả về 0 trace dù kết nối đã xác nhận sống (`/api/services` trả 200). Tra trực tiếp bằng trace ID cũ cũng 404 (khả năng đã rớt khỏi retention OpenSearch). Đây là **thiếu evidence thật sự**, không phải "không có trace đáng chú ý" — cần ghi nhận và thử lại bằng công cụ/quyền truy cập ổn định hơn.

## Evidence

### Latency so với budget tuyệt đối D16-PERF-01 §5 (`requests.csv`, toàn bộ cửa sổ 02:20:56Z–03:09:21Z)

| Flow | Requests | Failures | Success rate | p50 | p95 | p99 | Budget p95 | Budget p99 | Kết quả |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| Browse `GET /` | 7,051 | 16 | 99.77% | 660ms | 2,300ms | 3,000ms | <500ms | <800ms | **FAIL cả 2** |
| Cart `GET /api/cart` | 8,614 | 22 | 99.74% | 560ms | 2,300ms | 3,000ms | <700ms | <1,000ms | **FAIL cả 2** |
| Cart `POST /api/cart` | 30,028 | 26 | 99.91% | 430ms | 2,400ms | 3,100ms | <700ms | <1,000ms | **FAIL cả 2** |
| Checkout `POST /api/checkout` | 10,805 | 88 | 99.19% | 990ms | 3,000ms | 3,900ms | <1,000ms | <1,500ms | **FAIL cả 2** |
| Tổng hợp (toàn bộ route) | 121,658 | 274 (0.23%) | 99.77% | 710ms | 2,800ms | 4,300ms | — | — | chỉ để tham khảo |

Mọi flow đều FAIL budget tuyệt đối (vượt 3-5 lần). Ngược lại, **các gate về correctness/success-rate đều PASS**: Browse/Cart đạt ngưỡng ≥99.5%, Checkout đạt SLO ≥99.0% (99.19%). `POST /api/checkout` có 86 lỗi `500 Internal Server Error` rải đều suốt run (02:31Z–03:09Z, không tập trung quanh lúc deploy chen ngang) — một lỗi Checkout gián đoạn với tần suất thấp, cần theo dõi riêng nhưng không ảnh hưởng tới việc đạt SLO success-rate.

### Resource

- Số node: **4, không đổi suốt 49 phút** (từ lúc pre-run check 02:17Z đến khi kết thúc 03:09Z) — không có Karpenter scale event.
- `checkout`: 0 restart, CPU thấp suốt (4-36%/70%) — code checkout không bị áp lực.
- `frontend`: kẹt ceiling (3/3, `maxReplicas=3`) gần suốt run, 79-273%/70%.
- Không có OOM/Pending/CrashLoopBackOff ở bất kỳ đâu trong namespace.

### Trace

Không có — xem mục "Jaeger trace" ở trên.

## Kết luận

**INCONCLUSIVE — không đủ căn cứ để đóng task là PASS hay FAIL.**

1. Mọi gate p95/p99 tuyệt đối đều FAIL, vượt budget 3-5 lần.
2. Nguyên nhân xác nhận không phải do code checkout: `checkout`/`currency` không hề bị áp lực CPU suốt run; `frontend` bị kẹt cứng ở ceiling (`maxReplicas=3`), dao động 79-273%/70%. Node vẫn còn dư CPU (15-61%) — nút thắt là do cấu hình HPA, không phải do thiếu năng lực cluster.
3. Vấn đề phương pháp mới phát sinh: code đang test không được giữ nguyên suốt cửa sổ đo — PR #600 (`b536a75`) ghi đè toàn bộ `frontend` giữa chừng, khiến toàn bộ stability window chạy trên build chưa được review. Theo đúng rule đóng băng so sánh của D16-PERF-01, đây là căn cứ để phải chạy lại.
4. Điểm tích cực: correctness/success-rate đạt yêu cầu (Checkout 99.19% ≥ SLO 99%, aggregate error rate chỉ 0.23%) — xác nhận bộ fix D16-DEV-01 (#324/#558/#565/#592) không làm giảm correctness dưới tải, nhưng không đủ để chứng minh mục tiêu cải thiện p95/p99 vì bị chặn bởi nghẽn năng lực `frontend`.

**Đề xuất escalate lên Tech Lead/PM trước khi chạy lần tiếp theo:**

- **(a) Ceiling HPA của `frontend` (`maxReplicas=3`)** là nút thắt xác nhận lặp lại, chặn mọi lần đo validation. Node còn dư CPU (15-61%) nên tăng `maxReplicas` cho riêng `frontend` — không thêm node, không tăng `minReplicas` — có vẻ phù hợp với nguyên tắc "không đổi latency lấy compute" đã áp dụng cho checkout. Cần người phụ trách Cost/Capacity duyệt trước khi đo lại (Tuấn đang co-own pillar Cost + Perf).
- **(b) Cơ chế "báo TF giữ chỗ" qua chat không đủ để ngăn GitOps auto-sync deploy chen vào cửa sổ đang đo.** Cần cơ chế mạnh hơn: tạm dừng auto-sync cho các service đang test (`frontend`, `checkout`, `product-catalog`) trong đúng cửa sổ đã đặt lịch, hoặc quy ước merge-freeze chính thức thay vì chỉ báo qua chat.
- Cần thử lại việc lấy Jaeger trace bằng công cụ/quyền truy cập ổn định hơn — đây là evidence bắt buộc theo `task-tuan.md` nhưng chưa lấy được trong phiên này.

## Acceptance criteria (theo `task-tuan.md`)

- [x] Dùng cùng load contract — đúng tỷ trọng task/endpoint mix, đủ 4 phase (warm-up 5', ramp 5', sustained 25', stability 10').
- [x] Số lượng request đủ ngưỡng tối thiểu — Checkout 10,805 request, Browse/Cart đều vượt xa ngưỡng tối thiểu 1,000 mẫu/sustained window; không có baseline để tính tolerance ≤5%.
- [ ] p99 giảm theo improvement target (≥20% Checkout) — **không đánh giá được**, không có baseline hợp lệ để tính delta.
- [ ] p95 đạt budget tuyệt đối (§5) — **FAIL**, cả 3 flow vượt budget ~3-5 lần.
- [ ] p99 đạt budget tuyệt đối (§5) — **FAIL**, cả 3 flow vượt budget ~3.5-5 lần.
- [x] Correctness giữ nguyên — **PASS**, không phát sinh lỗi correctness ngoài lỗi Checkout 500 tần suất thấp đã biết.
- [x] Error rate không tăng đáng kể — **PASS** so với SLO: Browse 99.77%, Cart 99.74%/99.91%, Checkout 99.19%, aggregate 0.23%.
- [x] Node count không tăng — 4 node, ổn định suốt 49 phút.
- [x] Node-hours không tăng — nhất quán với node count ổn định.
- [x] Không có OOM/Pending regression mới — không quan sát thấy; 0 restart toàn namespace.
- [ ] **SHA đang review được giữ nguyên suốt cửa sổ đo** — **FAIL**: `frontend` bị PR #600 (`b536a75`) ghi đè giữa chừng, ảnh hưởng ~3 phút cuối sustained và toàn bộ stability window.
- [ ] Trace ID trước/sau để so sánh — **chưa lấy được**, lỗi công cụ truy vấn Jaeger trong phiên này.

Kết quả chung: gate resource và correctness/error-rate đều PASS; gate latency tuyệt đối FAIL; gate so sánh cải thiện p99 không thể đánh giá vì thiếu baseline; và 2 yêu cầu về evidence/quy trình (giữ nguyên SHA, trace ID) chưa đạt trong lần chạy này.
