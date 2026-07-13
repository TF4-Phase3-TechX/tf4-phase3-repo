# Plan: CDO08-REL-09 — Add timeout deadline retry budget for checkout dependencies

**Owner:** Quân
**Reviewer:** Nguyên
**Priority:** P0
**Backlog:** CDO08-REL-09
**Ngày:** 2026-07-13

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
| `techx-corp-platform/src/checkout/main.go` | Thêm `context.WithTimeout` cho 7 lời gọi + `grpc.WithConnectTimeout` cho `mustCreateClient` + retry loop cho 4 lời gọi đọc |
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

---

## 4. Timeout budget

| Service | Loại | Timeout | Retry | Worst case |
|---|---|---|---|---|
| cart | Đọc | 2s | 1 lần (backoff 200ms) | 4.2s |
| product-catalog | Đọc | 1s/item | 1 lần (backoff 100ms) | 2.2s/item |
| currency | Đọc | 1s/call | 1 lần (backoff 100ms) | 2.2s/call |
| shipping /get-quote | Đọc | 3s | 1 lần (backoff 300ms) | 6.3s |
| quote (qua shipping) | Đọc | 2s (fix Rust) | Không | 2s |
| payment | Ghi | 5s | KHÔNG | 5s |
| shipping /ship-order | Ghi | 3s | KHÔNG | 3s |
| gRPC connect | — | 3s | Không | 3s (startup) |

**Happy path:** Tất cả service bình thường → checkout ~550ms, p95 < 1s, timeout không trigger.

---

## 5. Code changes chi tiết

### 5.1 `checkout/main.go` — `mustCreateClient` (dòng 442-452)

**Thêm** `grpc.WithConnectTimeout(3*time.Second)` vào `grpc.NewClient`.

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

### 5.2 `checkout/main.go` — `getUserCart` (dòng 491-497)

**Thêm** `context.WithTimeout` 2s + retry 1 lần backoff 200ms.

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
	var err error
	for i := 0; i < 2; i++ {
		callCtx, cancel := context.WithTimeout(ctx, 2*time.Second)
		cart, err = cs.cartSvcClient.GetCart(callCtx, &pb.GetCartRequest{UserId: userID})
		cancel()
		if err == nil {
			break
		}
		if i == 0 {
			time.Sleep(200 * time.Millisecond)
		}
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get user cart during checkout: %+v", err)
	}
	return cart.GetItems(), nil
}
```

---

### 5.3 `checkout/main.go` — `prepOrderItems` (dòng 506-523)

**Sửa** vòng lặp `for` — thêm `context.WithTimeout` 1s cho mỗi `GetProduct` + retry 1 lần backoff 100ms.

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
		var err error
		for j := 0; j < 2; j++ {
			callCtx, cancel := context.WithTimeout(ctx, 1*time.Second)
			product, err = cs.productCatalogSvcClient.GetProduct(callCtx, &pb.GetProductRequest{Id: item.GetProductId()})
			cancel()
			if err == nil {
				break
			}
			if j == 0 {
				time.Sleep(100 * time.Millisecond)
			}
		}
		if err != nil {
			return nil, fmt.Errorf("failed to get product #%q", item.GetProductId())
		}
```

---

### 5.4 `checkout/main.go` — `convertCurrency` (dòng 525-533)

**Thêm** `context.WithTimeout` 1s + retry 1 lần backoff 100ms.

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
	var err error
	for i := 0; i < 2; i++ {
		callCtx, cancel := context.WithTimeout(ctx, 1*time.Second)
		result, err = cs.currencySvcClient.Convert(callCtx, &pb.CurrencyConversionRequest{
			From:   from,
			ToCode: toCurrency})
		cancel()
		if err == nil {
			break
		}
		if i == 0 {
			time.Sleep(100 * time.Millisecond)
		}
	}
	if err != nil {
		return nil, fmt.Errorf("failed to convert currency: %+v", err)
	}
	return result, err
}
```

---

### 5.5 `checkout/main.go` — `chargeCard` (dòng 535-550)

**Thêm** `context.WithTimeout` 5s. **KHÔNG retry.**

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

### 5.6 `checkout/main.go` — `quoteShipping` (dòng 462-466)

**Thêm** `context.WithTimeout` 3s + retry 1 lần backoff 300ms.

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
	var err error
	for i := 0; i < 2; i++ {
		callCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
		resp, err = otelhttp.Post(callCtx, cs.shippingSvcAddr+"/get-quote", "application/json", bytes.NewBuffer(quotePayload))
		cancel()
		if err == nil {
			break
		}
		if i == 0 {
			time.Sleep(300 * time.Millisecond)
		}
	}
	if err != nil {
		return nil, fmt.Errorf("failed POST to shipping service: %+v", err)
	}
	defer resp.Body.Close()
```

---

### 5.7 `checkout/main.go` — `shipOrder` (dòng 583-586)

**Thêm** `context.WithTimeout` 3s. **KHÔNG retry.**

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

### 5.8 `checkout/main.go` — `sendOrderConfirmation` (dòng 561)

**Thêm** `context.WithTimeout` 5s. Non-fatal.

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

### 5.9 `shipping/quote.rs` — `request_quote` (dòng 40)

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

### 6.1 Build & push image

```bash
# Vào thư mục techx-corp-platform
cd techx-corp-platform

# Nạp biến môi trường
set -a
. .env
. .env.override
set +a

# Build & push chỉ 2 service thay đổi
docker buildx bake -f docker-compose.yml --load --set "*.platform=linux/amd64" checkout
docker push "$IMAGE_NAME:$DEMO_VERSION-checkout"

docker buildx bake -f docker-compose.yml --load --set "*.platform=linux/amd64" shipping
docker push "$IMAGE_NAME:$DEMO_VERSION-shipping"
```

### 6.2 Deploy lên EKS

```bash
# Verify context EKS
kubectl config current-context

# Helm upgrade
helm upgrade --install techx-corp ./techx-corp-chart -n techx-tf4 \
  -f deploy/values-observability.yaml \
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

### 6.4 Fault test

```bash
# Test 1: Cart chậm — flagd cartFailure
# Bật flag cartFailure, đặt hàng, verify checkout fail <5s
kubectl -n techx-tf4 logs deploy/checkout --since=5m

# Test 2: Happy path — không delay
curl -s -o /dev/null -w "%{http_code} %{time_total}s" http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/

# Evidence: Jaeger trace — span duration < timeout
```

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

# Hoặc helm upgrade với image tag cũ
helm upgrade --install techx-corp ./techx-corp-chart -n techx-tf4 \
  -f deploy/values-observability.yaml \
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
| 1 | Checkout không treo vô hạn khi service chậm | Fault test: delay 1 service 10s | Checkout fail <5s, không chờ 10s |
| 2 | Happy path không ảnh hưởng | curl ALB không delay | HTTP 200, time < 1s |
| 3 | Payment KHÔNG retry | Jaeger trace khi payment fail | Chỉ 1 span `Charge`, không có span retry |
| 4 | Shipping ship-order KHÔNG retry | Jaeger trace khi ship-order fail | Chỉ 1 span `/ship-order` |
| 5 | Pod checkout Running sau deploy | `kubectl get pods` | READY 1/1, RESTARTS 0 |
| 6 | Pod shipping Running sau deploy | `kubectl get pods` | READY 1/1, RESTARTS 0 |
| 7 | Checkout log không crash | `kubectl logs deploy/checkout` | Không có panic/fatal |
| 8 | gRPC connect timeout hoạt động | Kill 1 service, deploy checkout | Checkout log "connection error" trong 3s, không treo |

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

- [ ] Code thay đổi 2 file: `checkout/main.go` + `shipping/quote.rs`
- [ ] Build & push image thành công
- [ ] Deploy lên EKS thành công, pod Running
- [ ] Fault test pass: dependency chậm → fail bounded
- [ ] Happy path pass: p95 < 1s
- [ ] Payment KHÔNG retry (trace verify)
- [ ] Evidence attach Jira (trace + log)
- [ ] Rollback plan verified
- [ ] PM cập nhật backlog status
