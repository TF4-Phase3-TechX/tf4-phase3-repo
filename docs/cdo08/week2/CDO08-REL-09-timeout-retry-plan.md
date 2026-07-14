# Plan: CDO08-REL-09 — Add timeout deadline retry budget for checkout dependencies

**Owner:** Quân
**Reviewer:** Nguyên
**Priority:** P0
**Backlog:** CDO08-REL-09
**Ngày:** 2026-07-13 (rev. 2026-07-14 sau review PM)

---

## 0. Điều chỉnh theo review PM (2026-07-14)

PM đánh giá scope **đạt yêu cầu**, plan được approve để implement **sau khi** chỉnh các điểm dưới. Bảng này map từng góp ý → thay đổi trong plan.

| # | Góp ý PM | Đã chỉnh ở |
|---|---|---|
| 1 | HTTP retry phải tạo body reader mới mỗi lần, không reuse `*bytes.Buffer` | §5.7 (quoteShipping), ghi chú §3 |
| 2 | Backoff phải tôn trọng `ctx.Done()`, không `time.Sleep` cứng | §5.0 helper `retryRead` — dùng cho tất cả read call |
| 3 | Timeout product-catalog + currency nhân theo số item → worst-case theo N | §4 (bảng + công thức worst-case), §7 (acceptance theo N) |
| 4 | Thêm overall checkout deadline bao toàn flow | §5.1 (wrap `PlaceOrder`), §4 |
| 5 | Fault test phải cover cả **slow** và **fast-error**; xác nhận flag | §6.4 (Case A/B + blocker: chưa có flag inject delay cho read) |
| 6 | Deploy sai overlay — app release dùng `values-app-stamp.yaml` | §6.2 |
| 7 | Ưu tiên CD (merge → CI build → deploy), manual là fallback | §6.1 |
| 8 | `grpc.WithConnectTimeout` là phụ; evidence chính là per-RPC `context.WithTimeout` | §5.2, §7 (điều kiện 8) |

**Nguyên tắc đã làm rõ:** evidence "fail bounded" **chính** là deadline áp per-RPC (mỗi lời gọi) + overall deadline bao flow — **không** dựa vào connect timeout.

---

## 1. Mục tiêu

Checkout gọi 7 service phụ thuộc mà không có giới hạn thời gian chờ. Nếu một service chậm, request checkout bị treo vô hạn, kéo theo p95 latency vọt và cascading failure. INC-1 đã từng xảy ra: giờ cao điểm checkout success tụt 95%, khách bỏ giỏ.

**Mục tiêu:** Thêm timeout cho mỗi lời gọi service phụ thuộc. Service chậm → checkout báo lỗi nhanh thay vì treo. Thêm retry cho lời gọi đọc dữ liệu. Không retry cho lời gọi có side effect (trừ tiền, tạo vận đơn).

---

## 2. Phương án đề xuất

| # | Việc | Lý do |
|---|---|---|
| 1 | Wrap mỗi lời gọi service trong context có deadline | Service chậm → fail bounded, không treo vô hạn |
| 2 | Thêm connect timeout 3s cho gRPC client | Connection tạo không có thời hạn → treo nếu service unreachable |
| 3 | Retry 1 lần cho lời gọi đọc dữ liệu (cart, product-catalog, currency, shipping get-quote) | Gọi lại không gây hại, tăng cơ hội thành công khi fail tạm thời |
| 4 | KHÔNG retry cho payment và shipping ship-order | Retry = trừ tiền 2 lần hoặc tạo 2 vận đơn |
| 5 | Fix shipping (Rust) gọi quote không timeout | Quote chậm → shipping treo → checkout treo |
| 6 | Fault test: delay 1 service 10s → verify checkout fail bounded | Chứng minh timeout hoạt động |

### Files thay đổi code

| File | Thay đổi |
|---|---|
| `techx-corp-platform/src/checkout/main.go` | Helper `retryRead` (timeout/attempt + retry + backoff tôn trọng ctx) + overall deadline `context.WithTimeout` bọc `PlaceOrder` + guard `ctx.Err()` trước charge + per-RPC `context.WithTimeout` cho 7 lời gọi + `grpc.WithConnectTimeout` (phụ) cho `mustCreateClient` + retry qua helper cho 4 lời gọi đọc |
| `techx-corp-platform/src/shipping/src/shipping_service/quote.rs` | Thay `awc::Client::new()` bằng `awc::ClientBuilder` có timeout 2s |

---

## 3. Hai loại call

### Đọc dữ liệu (idempotent — an toàn retry)

Lời gọi chỉ đọc dữ liệu, không thay đổi trạng thái. Gọi 1 lần hay 10 lần kết quả giống nhau. Nếu fail, retry không gây hại.

| Service | Call | Đọc gì |
|---|---|---|
| cart | `GetCart` | Giỏ hàng khách |
| product-catalog | `GetProduct` | Thông tin sản phẩm |
| currency | `Convert` | Đổi tiền tệ |
| shipping | `/get-quote` | Tính phí ship |

**Chiến lược:** Timeout ngắn + retry 1 lần.

### Ghi/thanh toán (có side effect — KHÔNG retry)

Lời gọi thay đổi trạng thái hệ thống. Gọi 2 lần = 2 lần thay đổi (trừ tiền 2 lần, tạo 2 vận đơn).

| Service | Call | Làm gì |
|---|---|---|
| payment | `Charge` | Trừ thẻ |
| shipping | `/ship-order` | Tạo vận đơn |

**Chiến lược:** Timeout dài hơn + KHÔNG retry. Retry chỉ khi có idempotency key (out of scope).

### Lưu ý HTTP body khi retry (góp ý PM #1)

Với lời gọi HTTP (`/get-quote`), body là một reader **dùng một lần** — `otelhttp.Post` đọc hết reader ở attempt đầu. **KHÔNG** được reuse cùng một `*bytes.Buffer`/reader giữa các attempt. Mỗi attempt phải tạo reader mới **từ cùng byte slice** đã marshal sẵn:

```go
body := bytes.NewReader(quotePayload) // quotePayload là []byte, tạo mới mỗi vòng
```

`quotePayload` (`[]byte`) marshal **một lần** ngoài vòng lặp; mỗi attempt bọc lại bằng `bytes.NewReader(quotePayload)` — slice không bị mutate nên an toàn. Xem §5.7.

---

## 4. Timeout budget

### 4.1 Per-call (mỗi lời gọi)

| Service | Loại | Timeout | Retry | Worst case / call |
|---|---|---|---|---|
| cart `GetCart` | Đọc | 2s | 1 lần (backoff 200ms) | 4.2s |
| product-catalog `GetProduct` | Đọc | 1s **/item** | 1 lần (backoff 100ms) | 2.1s **/item** |
| currency `Convert` | Đọc | 1s **/call** | 1 lần (backoff 100ms) | 2.1s **/call** |
| shipping `/get-quote` | Đọc | 3s | 1 lần (backoff 300ms) | 6.3s |
| quote (qua shipping) | Đọc | 2s (fix Rust) | Không | 2s |
| payment `Charge` | Ghi | 5s | KHÔNG | 5s |
| shipping `/ship-order` | Ghi | 3s | KHÔNG | 3s |
| gRPC connect | — | 3s (phụ) | Không | không phải evidence chính |

### 4.2 Worst-case theo số item N (góp ý PM #3)

`prepOrderItems` lặp qua **từng item**, mỗi item gọi `GetProduct` **và** `convertCurrency` tuần tự. Vì vậy worst-case của read path **nhân theo N item**, không phải hằng số:

```
prep phase (đọc) ≈ getUserCart(4.2s)
                 + N × [ GetProduct(2.1s) + Convert(2.1s) ]   ← nhân theo N
                 + get-quote(6.3s)
                 + Convert cho shipping(2.1s)
write phase (ghi) ≈ Charge(5s) + ship-order(3s)
```

Trong đó mỗi item ≈ `GetProduct`(2.1s) + `Convert`(2.1s) = **4.2s/item**; phần hằng số = cart(4.2s) + get-quote(6.3s) + Convert cho shipping(2.1s) = **12.6s**.

| N item | Worst-case prep (đọc) = 12.6 + N×4.2 | + write (ghi) | Tổng worst-case |
|---|---|---|---|
| 1 | ~16.8s | +8s | ~24.8s |
| 3 | ~25.2s | +8s | ~33.2s |
| 5 | ~33.6s | +8s | ~41.6s |

> **Không** claim "checkout fail <5s" cho mọi trường hợp. Con số đó chỉ đúng cho **một dependency đơn** chậm/lỗi. Acceptance criteria (§7) diễn đạt lại theo N.

### 4.3 Overall checkout deadline (góp ý PM #4)

Thêm **một deadline bao toàn `PlaceOrder`** để chặn trường hợp nhiều dependency timeout nối tiếp làm request kéo dài. SLO hiện **không** có ngưỡng latency cho checkout (chỉ success ≥ 99.0%, xem `onboarding/SLO.md`), nên overall deadline là **trần chống-treo (ceiling)**, không phải mục tiêu SLO.

- **Giá trị:** `CHECKOUT_OVERALL_TIMEOUT`, mặc định **20s** (env-configurable để tune mà không rebuild). 20s >> happy path (~0.55s) và > write-path budget (payment 5s + ship 3s = 8s) nên không cắt nhầm payment/flow khoẻ; đồng thời **cố ý thấp hơn** worst-case cascade bệnh lý (mọi dependency cùng chậm: ~24.8s cho 1 item, tăng theo N) để chặn request kéo dài vô ích. Tune theo dữ liệu latency thật sau khi deploy.
- **Guard side-effect:** sau prep, kiểm tra `ctx.Err()` **trước** khi gọi `chargeCard` → không bao giờ bắt đầu payment trên context đã hết hạn/cancel (tránh "đã trừ tiền nhưng báo lỗi").
- Overall deadline được set > tổng write-path budget (payment 5s + ship 3s = 8s) để không cắt ngang payment đang chạy.

**Happy path:** Tất cả service bình thường → checkout ~550ms, p95 < 1s, không timeout nào trigger.

---

## 5. Code changes chi tiết

### 5.0 `checkout/main.go` — helper `retryRead` (mới)

Gom logic timeout-per-attempt + retry + backoff-tôn-trọng-ctx vào **một** helper, dùng chung cho mọi read call. Backoff dùng `select` theo `ctx.Done()` thay cho `time.Sleep` cứng (góp ý PM #2) — nếu request cha đã bị cancel/hết hạn thì trả về ngay, không sleep thừa.

```go
// retryRead chạy một lời gọi IDEMPOTENT với timeout cho mỗi attempt và tối đa 1
// retry. Backoff tôn trọng ctx cha (không sleep khi ctx đã done).
// CHỈ dùng cho read (cart, product-catalog, currency, get-quote).
// TUYỆT ĐỐI không dùng cho call có side effect (payment, ship-order).
func retryRead(ctx context.Context, perAttempt, backoff time.Duration, fn func(ctx context.Context) error) error {
	var err error
	for attempt := 0; attempt < 2; attempt++ {
		callCtx, cancel := context.WithTimeout(ctx, perAttempt)
		err = fn(callCtx)
		cancel()
		if err == nil {
			return nil
		}
		if attempt == 0 {
			select {
			case <-time.After(backoff):
			case <-ctx.Done():
				return ctx.Err() // ctx cha cancel/hết hạn → dừng, không sleep tiếp
			}
		}
	}
	return err
}
```

---

### 5.1 `checkout/main.go` — overall checkout deadline trong `PlaceOrder` (mới)

Bọc toàn bộ flow bằng một deadline tổng (góp ý PM #4) + guard side-effect trước khi charge.

Trước (đầu `PlaceOrder`):
```go
func (cs *checkout) PlaceOrder(ctx context.Context, req *pb.PlaceOrderRequest) (*pb.PlaceOrderResponse, error) {
	span := trace.SpanFromContext(ctx)
	...
```

Sau:
```go
func (cs *checkout) PlaceOrder(ctx context.Context, req *pb.PlaceOrderRequest) (*pb.PlaceOrderResponse, error) {
	// Overall deadline: trần chống-treo cho toàn request (không phải mục tiêu SLO).
	// Configurable qua env để tune không cần rebuild; mặc định 20s.
	overall := 20 * time.Second
	if v := os.Getenv("CHECKOUT_OVERALL_TIMEOUT"); v != "" {
		if d, perr := time.ParseDuration(v); perr == nil {
			overall = d
		}
	}
	ctx, cancel := context.WithTimeout(ctx, overall)
	defer cancel()

	span := trace.SpanFromContext(ctx)
	...
```

Guard trước khi charge (giữa `span.AddEvent("prepared")` và `chargeCard`):
```go
	// Không bắt đầu payment nếu ctx đã hết hạn/cancel trong lúc prep
	// (tránh "đã trừ tiền nhưng báo lỗi" khi overall deadline cháy giữa chừng).
	if err = ctx.Err(); err != nil {
		return nil, status.Errorf(codes.DeadlineExceeded, "checkout deadline exceeded before payment: %v", err)
	}

	txID, err := cs.chargeCard(ctx, total, req.CreditCard)
```

---

### 5.2 `checkout/main.go` — `mustCreateClient` (connect timeout — evidence phụ)

**Thêm** `grpc.WithConnectTimeout(3*time.Second)` vào `grpc.NewClient`.

> **Lưu ý (góp ý PM #8):** `grpc.NewClient` thiết lập connection **lazy**, nên connect timeout **không** phải là cơ chế chính đảm bảo request fail bounded. Giữ nó như một lớp phòng thủ phụ (dial hang lúc startup / service unreachable), nhưng **evidence chính** cho "fail bounded" là per-RPC `context.WithTimeout` (§5.3–5.6) + overall deadline (§5.1). Trace verify phải chỉ vào deadline **per-call**, không phải connect timeout.

Trước:
```go
func mustCreateClient(svcAddr string) *grpc.ClientConn {
	c, err := grpc.NewClient(svcAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
	)
```

Sau:
```go
func mustCreateClient(svcAddr string) *grpc.ClientConn {
	c, err := grpc.NewClient(svcAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
		grpc.WithConnectTimeout(3*time.Second),
	)
```

---

### 5.3 `checkout/main.go` — `getUserCart` (timeout 2s + retry qua helper)

Dùng `retryRead` (§5.0): timeout 2s/attempt, backoff 200ms tôn trọng ctx.

Trước:
```go
func (cs *checkout) getUserCart(ctx context.Context, userID string) ([]*pb.CartItem, error) {
	cart, err := cs.cartSvcClient.GetCart(ctx, &pb.GetCartRequest{UserId: userID})
	if err != nil {
		return nil, fmt.Errorf("failed to get user cart during checkout: %+v", err)
	}
	return cart.GetItems(), nil
}
```

Sau:
```go
func (cs *checkout) getUserCart(ctx context.Context, userID string) ([]*pb.CartItem, error) {
	var cart *pb.Cart
	err := retryRead(ctx, 2*time.Second, 200*time.Millisecond, func(callCtx context.Context) error {
		var e error
		cart, e = cs.cartSvcClient.GetCart(callCtx, &pb.GetCartRequest{UserId: userID})
		return e
	})
	if err != nil {
		return nil, fmt.Errorf("failed to get user cart during checkout: %+v", err)
	}
	return cart.GetItems(), nil
}
```

---

### 5.4 `checkout/main.go` — `prepOrderItems` (timeout 1s/item + retry qua helper)

**Sửa** vòng lặp `for` — mỗi `GetProduct` dùng `retryRead` (§5.0): timeout 1s/attempt, backoff 100ms tôn trọng ctx.

> ⚠️ **Timeout này áp cho MỖI item** — worst-case của cả `prepOrderItems` nhân theo số item N (xem §4.2). Overall deadline (§5.1) là lớp bao chống trường hợp N lớn + degrade.

Trước:
```go
	for i, item := range items {
		product, err := cs.productCatalogSvcClient.GetProduct(ctx, &pb.GetProductRequest{Id: item.GetProductId()})
		if err != nil {
			return nil, fmt.Errorf("failed to get product #%q", item.GetProductId())
		}
```

Sau:
```go
	for i, item := range items {
		var product *pb.Product
		err := retryRead(ctx, 1*time.Second, 100*time.Millisecond, func(callCtx context.Context) error {
			var e error
			product, e = cs.productCatalogSvcClient.GetProduct(callCtx, &pb.GetProductRequest{Id: item.GetProductId()})
			return e
		})
		if err != nil {
			return nil, fmt.Errorf("failed to get product #%q", item.GetProductId())
		}
```

---

### 5.5 `checkout/main.go` — `convertCurrency` (timeout 1s + retry qua helper)

Dùng `retryRead` (§5.0): timeout 1s/attempt, backoff 100ms tôn trọng ctx.

> ⚠️ `convertCurrency` được gọi **trong** vòng lặp `prepOrderItems` (1 lần/item) **và** 1 lần cho shipping cost → cũng nhân theo N (xem §4.2).

Trước:
```go
func (cs *checkout) convertCurrency(ctx context.Context, from *pb.Money, toCurrency string) (*pb.Money, error) {
	result, err := cs.currencySvcClient.Convert(ctx, &pb.CurrencyConversionRequest{
		From:   from,
		ToCode: toCurrency})
	if err != nil {
		return nil, fmt.Errorf("failed to convert currency: %+v", err)
	}
	return result, err
}
```

Sau:
```go
func (cs *checkout) convertCurrency(ctx context.Context, from *pb.Money, toCurrency string) (*pb.Money, error) {
	var result *pb.Money
	err := retryRead(ctx, 1*time.Second, 100*time.Millisecond, func(callCtx context.Context) error {
		var e error
		result, e = cs.currencySvcClient.Convert(callCtx, &pb.CurrencyConversionRequest{
			From:   from,
			ToCode: toCurrency})
		return e
	})
	if err != nil {
		return nil, fmt.Errorf("failed to convert currency: %+v", err)
	}
	return result, nil
}
```

---

### 5.6 `checkout/main.go` — `chargeCard` (timeout 5s, KHÔNG retry)

**Thêm** `context.WithTimeout` 5s. **KHÔNG retry** (side effect — trừ tiền). Guard "không charge khi ctx đã hết hạn" đã đặt ở `PlaceOrder` (§5.1).

Trước:
```go
func (cs *checkout) chargeCard(ctx context.Context, amount *pb.Money, paymentInfo *pb.CreditCardInfo) (string, error) {
	paymentService := cs.paymentSvcClient
	if cs.isFeatureFlagEnabled(ctx, "paymentUnreachable") {
		badAddress := "badAddress:50051"
		c := mustCreateClient(badAddress)
		paymentService = pb.NewPaymentServiceClient(c)
	}

	paymentResp, err := paymentService.Charge(ctx, &pb.ChargeRequest{
		Amount:     amount,
		CreditCard: paymentInfo})
```

Sau:
```go
func (cs *checkout) chargeCard(ctx context.Context, amount *pb.Money, paymentInfo *pb.CreditCardInfo) (string, error) {
	paymentService := cs.paymentSvcClient
	if cs.isFeatureFlagEnabled(ctx, "paymentUnreachable") {
		badAddress := "badAddress:50051"
		c := mustCreateClient(badAddress)
		paymentService = pb.NewPaymentServiceClient(c)
	}

	callCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	paymentResp, err := paymentService.Charge(callCtx, &pb.ChargeRequest{
		Amount:     amount,
		CreditCard: paymentInfo})
```

---

### 5.7 `checkout/main.go` — `quoteShipping` (timeout 3s + retry qua helper, body reader mới mỗi attempt)

Dùng `retryRead` (§5.0): timeout 3s/attempt, backoff 300ms tôn trọng ctx. **Mỗi attempt tạo `bytes.NewReader(quotePayload)` mới** — không reuse reader/buffer giữa các lần (góp ý PM #1). `quotePayload` (`[]byte`) đã marshal sẵn ngoài loop nên tạo reader mới là an toàn, không mutate slice.

Trước:
```go
	resp, err := otelhttp.Post(ctx, cs.shippingSvcAddr+"/get-quote", "application/json", bytes.NewBuffer(quotePayload))
	if err != nil {
		return nil, fmt.Errorf("failed POST to shipping service: %+v", err)
	}
	defer resp.Body.Close()
```

Sau:
```go
	var resp *http.Response
	err = retryRead(ctx, 3*time.Second, 300*time.Millisecond, func(callCtx context.Context) error {
		// body reader MỚI mỗi attempt — attempt trước đã consume reader cũ.
		r, e := otelhttp.Post(callCtx, cs.shippingSvcAddr+"/get-quote", "application/json", bytes.NewReader(quotePayload))
		if e != nil {
			return e
		}
		resp = r
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("failed POST to shipping service: %+v", err)
	}
	defer resp.Body.Close()
```

> Lưu ý: helper coi "không có transport error" là thành công của attempt. Nếu shipping trả HTTP 5xx nhưng vẫn có response (không phải transport error), retry sẽ **không** tự kích hoạt — status code được kiểm tra sau vòng `retryRead` như hiện tại (`resp.StatusCode != 200`). Đây là chủ đích: get-quote 5xx thường là lỗi logic phía shipping, retry ngay không giúp; timeout/transport error mới là thứ đáng retry.

---

### 5.8 `checkout/main.go` — `shipOrder` (timeout 3s, KHÔNG retry)

**Thêm** `context.WithTimeout` 3s. **KHÔNG retry** (side effect — tạo vận đơn).

Trước:
```go
	resp, err := otelhttp.Post(ctx, cs.shippingSvcAddr+"/ship-order", "application/json", bytes.NewBuffer(shipPayload))
	if err != nil {
		return "", fmt.Errorf("failed POST to shipping service: %+v", err)
	}
	defer resp.Body.Close()
```

Sau:
```go
	callCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()

	resp, err := otelhttp.Post(callCtx, cs.shippingSvcAddr+"/ship-order", "application/json", bytes.NewBuffer(shipPayload))
	if err != nil {
		return "", fmt.Errorf("failed POST to shipping service: %+v", err)
	}
	defer resp.Body.Close()
```

---

### 5.9 `checkout/main.go` — `sendOrderConfirmation` (timeout 5s, non-fatal, KHÔNG retry)

**Thêm** `context.WithTimeout` 5s. Non-fatal (lỗi email chỉ log warning, không fail order).

Trước:
```go
	resp, err := otelhttp.Post(ctx, cs.emailSvcAddr+"/send_order_confirmation", "application/json", bytes.NewBuffer(emailPayload))
```

Sau:
```go
	callCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	resp, err := otelhttp.Post(callCtx, cs.emailSvcAddr+"/send_order_confirmation", "application/json", bytes.NewBuffer(emailPayload))
```

---

### 5.10 `shipping/quote.rs` — `request_quote` (dòng 40)

**Thay** `awc::Client::new()` bằng `awc::ClientBuilder` có timeout 2s.

Trước:
```rust
    let client = awc::Client::new();
```

Sau:
```rust
    let client = awc::ClientBuilder::new()
        .timeout(std::time::Duration::from_secs(2))
        .finish();
```

---

## 6. Sau khi thay đổi code — đưa lên hệ thống

### 6.1 Build & push image — CD là đường chính (góp ý PM #7)

**Preferred path (chuẩn):** PR merge → CI build image → deploy workflow. Tránh image tag lệch giữa manual build và chart/CD.

1. Mở PR từ branch `cdo08/week2/rel-09-checkout-timeout-retry` → `main`, để CI (`.github/workflows/ci.yaml`) chạy build + test.
2. Merge PR → `.github/workflows/build-and-push.yaml` build & push image, rồi trigger `.github/workflows/deploy.yaml` (chạy on push to `main`) với image tag do CI sinh.
3. Deploy workflow tự chạy `helm upgrade` với đúng app overlay (xem §6.2). Không cần thao tác thủ công.

**Fallback (chỉ khi CD hỏng / cần hotfix khẩn):** build & push tay 2 service thay đổi. Ghi rõ đây là ngoại lệ và verify image tag khớp với chart trước khi deploy.

```bash
# FALLBACK — chỉ dùng khi CD không khả dụng
cd techx-corp-platform
set -a; . .env; . .env.override; set +a
docker buildx bake -f docker-compose.yml --load --set "*.platform=linux/amd64" checkout
docker push "$IMAGE_NAME:$DEMO_VERSION-checkout"
docker buildx bake -f docker-compose.yml --load --set "*.platform=linux/amd64" shipping
docker push "$IMAGE_NAME:$DEMO_VERSION-shipping"
```

### 6.2 Deploy lên EKS — dùng app overlay (góp ý PM #6)

App release **phải** dùng `values-app-stamp.yaml`, **KHÔNG** dùng `values-observability.yaml` (overlay đó set `checkout: { enabled: false }` — sẽ tắt luôn service cần deploy). Đây cũng đúng với `deploy.yaml` của CD.

Nếu để CD lo thì bỏ qua bước tay này. Chỉ chạy khi cần deploy thủ công (fallback):

```bash
# Verify context EKS
kubectl config current-context

# Helm upgrade — APP overlay (không phải observability)
helm upgrade --install techx-corp ./techx-corp-chart -n techx-tf4 \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml \
  --wait --timeout 5m

# Chờ rollout
kubectl -n techx-tf4 rollout status deploy/checkout --timeout=120s
kubectl -n techx-tf4 rollout status deploy/shipping --timeout=120s
```

### 6.3 Verify sau deploy

```bash
# Pod healthy
kubectl -n techx-tf4 get pods -l app.kubernetes.io/name=checkout
kubectl -n techx-tf4 get pods -l app.kubernetes.io/name=shipping

# Checkout log không có error
kubectl -n techx-tf4 logs deploy/checkout --tail=50

# Smoke test
curl -s -o /dev/null -w "%{http_code} %{time_total}s" http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/
```

### 6.4 Fault test (góp ý PM #5)

Task yêu cầu chứng minh **cả hai** trường hợp: dependency **trả lỗi nhanh** và dependency **chậm hơn timeout**. Phải phân biệt rõ vì hai đường code khác nhau (fail nhanh vs deadline trigger).

#### Kiểm tra flag hiện có (đã verify trong repo)

| Flag | Ảnh hưởng thực tế | Loại | Dùng test được gì |
|---|---|---|---|
| `cartFailure` | Chỉ đổi `EmptyCart` sang bad store → **lỗi nhanh**; **KHÔNG** làm `GetCart` chậm, và `EmptyCart` chạy **sau** payment (non-fatal) | fast-error | ❌ **Không** demo được timeout của `getUserCart` |
| `productCatalogFailure` | `GetProduct` trả lỗi nhanh, **chỉ** với product id `OLJCESPC7Z` | fast-error | ✅ Case A (fast-error) cho product-catalog |
| `paymentFailure` | `Charge` trả lỗi nhanh theo xác suất | fast-error | ✅ Case A cho payment (verify KHÔNG retry) |
| `paymentUnreachable` | Checkout trỏ `Charge` sang `badAddress:50051` (unreachable) → RPC **treo** đến khi hết deadline | slow/hang | ✅ Case B (slow) cho write path |

> **Blocker cần ghi nhận:** **không** có flagd flag nào inject *latency* vào một dependency đọc đang khoẻ (cart/product-catalog/currency Get*). `paymentUnreachable` chỉ cover write path. Để test "read dependency chậm hơn timeout" cần một trong các cách sau — **phải review trước khi dùng trên cluster chung**:
> 1. **Tạm scale/patch** một dependency để thêm delay (vd sidecar sleep, hoặc network delay qua toxiproxy) — cần Nguyên review.
> 2. **Thêm một fault flag delay tạm thời** (vd `checkoutDependencyDelayMs`) chỉ bật trong cửa sổ test, tắt ngay sau — cần review + không merge vào flag production.
> 3. Nếu không kịp, ghi rõ blocker này trên Jira và giới hạn evidence Case B ở `paymentUnreachable`.

#### Case A — dependency trả lỗi nhanh

```bash
# Bật productCatalogFailure, đặt hàng với product OLJCESPC7Z
# Kỳ vọng: checkout fail nhanh (không treo), Jaeger có span GetProduct lỗi
kubectl -n techx-tf4 logs deploy/checkout --since=5m | grep -i "failed to get product"

# Payment fast-error: bật paymentFailure, verify Jaeger CHỈ 1 span Charge (không retry)
```

#### Case B — dependency chậm hơn timeout

```bash
# paymentUnreachable → Charge treo → verify fail bounded bởi timeout 5s (§5.6), KHÔNG treo vô hạn
# Kỳ vọng: request fail trong ~5s (per-RPC deadline), KHÔNG có span Charge thứ 2 (không retry)
kubectl -n techx-tf4 logs deploy/checkout --since=5m | grep -i "could not charge"

# (Nếu có cơ chế delay read đã review) bật delay > timeout cho cart/product-catalog/currency:
#   verify per-RPC deadline trigger + đúng 1 retry cho read
```

#### Happy path

```bash
curl -s -o /dev/null -w "%{http_code} %{time_total}s" http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/
# Kỳ vọng: HTTP 200, time_total < 1s, không timeout nào trigger
```

**Evidence (góp ý PM #8):** screenshot Jaeger trace cho từng case, chỉ rõ **span duration của per-RPC call** ≤ timeout tương ứng (đây là evidence chính, không phải connect timeout). Đính kèm log checkout + trace vào Jira.

### 6.5 Rollback nếu cần

```bash
# Revert code commit
git revert <commit-hash>

# Rebuild & push image cũ
cd techx-corp-platform
set -a; . .env; . .env.override; set +a
docker buildx bake -f docker-compose.yml --load --set "*.platform=linux/amd64" checkout
docker push "$IMAGE_NAME:$DEMO_VERSION-checkout"
docker buildx bake -f docker-compose.yml --load --set "*.platform=linux/amd64" shipping
docker push "$IMAGE_NAME:$DEMO_VERSION-shipping"

# Helm rollback
helm rollback techx-corp -n techx-tf4

# Hoặc helm upgrade với image tag cũ — APP overlay (không phải observability)
helm upgrade --install techx-corp ./techx-corp-chart -n techx-tf4 \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml \
  --wait --timeout 5m

# Verify rollback
kubectl -n techx-tf4 rollout status deploy/checkout --timeout=120s
kubectl -n techx-tf4 rollout status deploy/shipping --timeout=120s
curl -s -o /dev/null -w "%{http_code} %{time_total}s" http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/
```

---

## 7. Điều kiện pass

| # | Điều kiện | Cách check | Pass khi |
|---|---|---|---|
| 1 | Một dependency chậm/hang → fail bounded theo per-RPC deadline | Case B (§6.4): `paymentUnreachable` hoặc delay đã review | Request fail trong ~timeout của call đó (vd payment ~5s), **không** treo vô hạn |
| 1b | Fail bounded **theo số item N** cho read path | Case B với cart N item | Tổng thời gian ≤ worst-case theo §4.2 cho N đó (KHÔNG claim `<5s` cho mọi N) |
| 1c | Toàn request bị bao bởi overall deadline | Nhiều dependency degrade | Request kết thúc ≤ `CHECKOUT_OVERALL_TIMEOUT` (mặc định 20s), không kéo dài hơn |
| 2 | Happy path không ảnh hưởng | curl ALB không delay | HTTP 200, time < 1s |
| 3 | Payment KHÔNG retry | Jaeger trace khi payment fail (Case A) | Chỉ 1 span `Charge`, không có span retry |
| 4 | Shipping ship-order KHÔNG retry | Jaeger trace khi ship-order fail | Chỉ 1 span `/ship-order` |
| 5 | Read call CÓ retry đúng 1 lần | Jaeger trace khi read fail tạm | Tối đa 2 span cho cùng call (1 gốc + 1 retry) |
| 6 | Pod checkout Running sau deploy | `kubectl get pods` | READY 1/1, RESTARTS 0 |
| 7 | Pod shipping Running sau deploy | `kubectl get pods` | READY 1/1, RESTARTS 0 |
| 8 | Checkout log không crash | `kubectl logs deploy/checkout` | Không có panic/fatal |
| 9 | **Evidence chính = per-RPC deadline** (không phải connect timeout) | Jaeger trace | Span duration của từng RPC ≤ timeout tương ứng; connect timeout chỉ là lớp phụ |

---

## 8. Rollback

| Tình huống | Rollback gì | Lý do |
|---|---|---|
| Timeout quá ngắn → false failure | Tăng timeout service đó, không xóa guard | Service cần nhiều thời gian hơn |
| Checkout crash sau deploy | Revert commit `checkout/main.go` → rebuild → helm rollback | Code bug |
| Shipping crash sau Rust change | Revert commit `quote.rs` → rebuild → helm rollback | Rust build issue |
| p95 latency tăng vì retry | Bỏ retry, giữ timeout | Retry tạo tải thêm |

**Nguyên tắc:** Rollback từng service. Không bỏ guard hoàn toàn — nếu timeout sai, tăng timeout, không xóa.

---

## 9. Coordination

| Role | Người | Trách nhiệm |
|---|---|---|
| Owner | Quân | Code, test, evidence |
| Reviewer | Nguyên | Review design + code |
| SLO | Quyết | Verify p95, success rate |


---

## 10. Definition of Done

- [ ] Code thay đổi 2 file: `checkout/main.go` (helper `retryRead` + overall deadline + guard trước charge + per-RPC timeout) + `shipping/quote.rs`
- [ ] Backoff dùng `select`/`ctx.Done()`, KHÔNG `time.Sleep` cứng
- [ ] HTTP retry tạo body reader mới mỗi attempt (không reuse buffer)
- [ ] Deploy qua CD (merge → CI build → deploy workflow); dùng `values-app-stamp.yaml` (không `values-observability.yaml`); pod Running
- [ ] Fault test pass **cả 2 case**: fast-error (Case A) + slow/hang (Case B); blocker delay-injection đã ghi nhận nếu còn
- [ ] Happy path pass: p95 < 1s
- [ ] Payment + ship-order KHÔNG retry (trace verify); read CÓ retry đúng 1 lần
- [ ] Worst-case theo N item được document; overall deadline bao request
- [ ] Evidence chính = per-RPC span duration ≤ timeout (attach Jira: trace + log)
- [ ] Rollback plan verified
- [ ] PM cập nhật backlog status
