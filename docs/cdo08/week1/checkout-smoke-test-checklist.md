# Checkout Smoke Test Checklist

**Task:** CDO08-12 — Tạo checkout smoke test checklist
**Owner:** Quân
**Pillar:** Reliability
**Priority:** P1
**Ngày:** 2026-07-08

---

## 1. Mục đích

Checklist này dùng để kiểm tra nhanh luồng checkout sau:
- Deploy hoặc Helm upgrade
- Rollback
- Incident recovery
- Thay đổi cấu hình flagd
- Build/push image mới

Smoke test chỉ kiểm tra các bước quan trọng nhất của revenue path, không phải full regression.

---

## 2. Prerequisites

| Mục | Yêu cầu |
|---|---|
| ALB URL | Lấy từ `kubectl get ingress -n techx-tf4 -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'` |
| Browser | Chrome/Firefox/Edge mới nhất |
| Kubectl access | Namespace `techx-tf4` — quyền `get pods`, `get logs`, `get events` |
| Jaeger access | `http://<ALB_URL>/jaeger` |
| Grafana access | `http://<ALB_URL>/grafana` |
| Test data | Cart có sẵn sản phẩm hoặc thêm sản phẩm từ storefront |

---

## 3. Smoke test steps

### 3.1 Pre-check — hệ thống sẵn sàng

| # | Step | Command / Action | Expected result | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| P1 | Kiểm tra pod checkout | `kubectl get pods -n techx-tf4 -l app=checkout -o wide` | Pod `Running`, READY `1/1`, RESTARTS `0` | Screenshot terminal | □ Pass □ Fail |
| P2 | Kiểm tra tất cả pod trong revenue path | `kubectl get pods -n techx-tf4 -l 'app in (checkout, cart, product-catalog, currency, shipping, quote, payment, email, frontend, frontend-proxy)'` | Tất cả `Running`, READY `1/1` | Screenshot terminal | □ Pass □ Fail |
| P3 | Kiểm tra infra pod | `kubectl get pods -n techx-tf4 -l 'app in (kafka, valkey-cart, postgresql, flagd)'` | Tất cả `Running` | Screenshot terminal | □ Pass □ Fail |
| P4 | Kiểm tra ALB health | `curl -s -o /dev/null -w "%{http_code}" http://<ALB_URL>` | HTTP `200` | Terminal output | □ Pass □ Fail |
| P5 | Kiểm tra Jaeger reachable | Mở `http://<ALB_URL>/jaeger` trong browser | Jaeger UI hiển thị, search được service `checkout` | Screenshot Jaeger UI | □ Pass □ Fail |

### 3.2 User flow — browse sản phẩm

| # | Step | Action | Expected result | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| U1 | Mở storefront | Mở `http://<ALB_URL>` | Trang chủ hiển thị danh sách sản phẩm, không có lỗi | Screenshot storefront | □ Pass □ Fail |
| U2 | Xem danh sách sản phẩm | Scroll danh sách sản phẩm trên trang chủ | Ít nhất 4-6 sản phẩm hiển thị, có ảnh + giá + tên | Screenshot product list | □ Pass □ Fail |
| U3 | Mở chi tiết sản phẩm | Click vào một sản phẩm bất kỳ | Trang chi tiết hiển thị: tên, ảnh, giá, mô tả, nút "Add to Cart" | Screenshot product detail | □ Pass □ Fail |

### 3.3 User flow — giỏ hàng

| # | Step | Action | Expected result | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| U4 | Thêm sản phẩm vào giỏ | Click "Add to Cart" trên trang chi tiết sản phẩm | Thông báo thành công (toast/message), số lượng giỏ tăng lên 1 | Screenshot sau khi add | □ Pass □ Fail |
| U5 | Thêm sản phẩm thứ 2 | Quay lại danh sách, chọn sản phẩm khác, click "Add to Cart" | Số lượng giỏ tăng lên 2 | Screenshot | □ Pass □ Fail |
| U6 | Xem giỏ hàng | Click vào icon giỏ hàng (hoặc `/cart`) | Danh sách 2 sản phẩm trong giỏ, có tổng tiền, nút "Place Order" | Screenshot cart page | □ Pass □ Fail |

### 3.4 User flow — checkout

| # | Step | Action | Expected result | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| U7 | Bắt đầu checkout | Click "Place Order" | Chuyển sang trang checkout form, hiển thị email + address fields + tổng tiền | Screenshot checkout form | □ Pass □ Fail |
| U8 | Điền thông tin và submit | Điền email (ví dụ: `test@example.com`), address, credit card (số bất kỳ), click "Place Order" | Trang xác nhận đơn hàng hiển thị: Order ID, danh sách sản phẩm, tổng tiền, tracking ID (nếu có) | Screenshot order confirmation | □ Pass □ Fail |
| U9 | Kiểm tra thông báo thành công | Xem nội dung trang xác nhận | Có "Your order is complete" hoặc tương tự, không có lỗi | Screenshot | □ Pass □ Fail |

### 3.5 Post-checkout verification

| # | Step | Action | Expected result | Evidence | Pass/Fail |
|---|---|---|---|---|---|
| V1 | Kiểm tra trace Jaeger | Mở Jaeger, search service `checkout`, chọn trace gần nhất | Trace có đầy đủ spans: frontend → checkout → cart → product-catalog → currency → shipping → quote → payment → email → kafka | Screenshot Jaeger waterfall | □ Pass □ Fail |
| V2 | Kiểm tra log checkout không có error | `kubectl logs -n techx-tf4 -l app=checkout --tail=100 --timestamps \| grep -i "error\|warn\|fail"` | Không có error level log, chỉ có warn từ email (expected) | Terminal output | □ Pass □ Fail |
| V3 | Kiểm tra accounting consumer | `kubectl logs -n techx-tf4 -l app=accounting --tail=50 --timestamps \| grep -i "order"` | Order ID từ checkout xuất hiện trong log accounting | Terminal output | □ Pass □ Fail |
| V4 | Kiểm tra Kafka không có lag | `kubectl exec -n techx-tf4 deploy/kafka -- kafka-consumer-groups --bootstrap-server localhost:9092 --group accounting --describe` | LAG = 0 (hoặc rất thấp) | Terminal output | □ Pass □ Fail |
| V5 | Kiểm tra Grafana checkout dashboard | Mở Grafana dashboard checkout (nếu có) | Error rate = 0, latency p95 bình thường | Screenshot Grafana | □ Pass □ Fail |

---

## 4. Troubleshooting guide

| Symptom | Possible cause | Quick check | Action |
|---|---|---|---|
| ALB 503 | Pod backend chưa ready | `kubectl get pods -n techx-tf4` | Đợi pod Ready; nếu `ImagePullBackOff` thì build lại image |
| Storefront 404 | Frontend-proxy ingress misconfig | `kubectl get ingress -n techx-tf4` | Kiểm tra ALB URL và path rules |
| Cart không add được | Cart service error | `kubectl logs -n techx-tf4 -l app=cart --tail=50` | Kiểm tra cart log; kiểm tra valkey-cart pod |
| Place Order lỗi | Checkout dependency failure | `kubectl logs -n techx-tf4 -l app=checkout --tail=100` | Đọc error message; kiểm tra trace Jaeger |
| Payment lỗi | Payment service unreachable | Check flagd `paymentUnreachable` | Tắt flag nếu đang bật; kiểm tra payment pod |
| Email không gửi | Email service down | `kubectl logs -n techx-tf4 -l app=email --tail=50` | Email fail là non-fatal, order vẫn thành công |
| Không thấy trace | OTel collector down | `kubectl get pods -n techx-tf4 -l app=otel-collector` | Kiểm tra OTel collector pod và OTLP endpoint config |

---

## 5. Pass/Fail criteria

### Overall result

| Kết quả | Điều kiện |
|---|---|
| **PASS** | Tất cả steps P1-P5, U1-U9, V1-V5 đều Pass |
| **PASS (with warnings)** | Các steps Pre-check + User flow đều Pass; Post-checkout có tối đa 1 Fail (V4 hoặc V5) |
| **FAIL** | Bất kỳ step Pre-check hoặc User flow nào Fail |
| **BLOCKED** | Pre-check P1 hoặc P4 Fail (hệ thống chưa sẵn sàng) |

### Decision matrix

| Scenario | Action |
|---|---|
| All Pass | Release/rollback OK |
| PASS (with warnings) | Release OK, tạo ticket cho warning |
| FAIL | Rollback ngay nếu đang deploy; không release |
| BLOCKED | Dừng smoke test, kiểm tra hệ thống trước |

---

## 6. Test data cleanup

| Item | Ghi chú |
|---|---|
| Order được tạo | Order ID: ghi lại từ step U8 — dùng làm evidence |
| Cart sau test | Cart sẽ empty sau checkout thành công (nếu `EmptyCart` chạy OK) |
| Kafka topic `orders` | Order message sẽ persist — cleanup không cần thiết cho smoke test |
| Email test | Email gửi tới `test@example.com` — không phải email thật |

---

## 7. Sample run

*(Mục này điền sau khi chạy trial — hiện tại environment chưa sẵn sàng, các pod core đang ImagePullBackOff)*

| Step | Result | Ghi chú |
|---|---|---|
| P1-P5 | ⏳ Chưa chạy | EKS environment chưa sẵn sàng (ECR image missing) |
| U1-U9 | ⏳ Chưa chạy | Cần pod checkout + cart + payment running |
| V1-V5 | ⏳ Chưa chạy | Cần trace + log từ checkout request thật |

---

## 8. Coverage map

| Dependency | Tested by step | Expected |
|---|---|---|
| frontend-proxy (Envoy) | P4, U1 | HTTP 200, serve storefront |
| frontend (Next.js) | U1, U2, U3 | Render products, no SSR error |
| checkout (Go) | U7, U8, V1, V2 | PlaceOrder gRPC success, trace đầy đủ |
| cart (.NET) | U4, U5, U6, V1 | GetCart/EmptyCart gRPC success |
| valkey-cart | U4, U6 (qua cart) | Cart data persisted |
| product-catalog (Go) | U2, U3, V1 | GetProduct gRPC success |
| postgresql | U3 (qua product-catalog) | Product data available |
| currency (C++) | U8, V1 | Convert gRPC success |
| shipping (Rust) | U8, V1 | /get-quote + /ship-order HTTP success |
| quote (PHP) | U8, V1 (qua shipping) | Quote HTTP success |
| payment (Node.js) | U8, V1 | Charge gRPC success |
| email (Ruby) | V1, V2 | send_order_confirmation HTTP (non-fatal) |
| kafka | V3, V4 | Topic `orders` produced, accounting consumed |
| accounting (.NET) | V3 | Consumer log chứa order ID |
| fraud-detection (Kotlin) | V1 | Consumer trace (nếu có) |
| flagd | U8 (cartFailure, paymentFailure flags) | Feature flags default safe |

---

## 9. Findings

| # | Finding | Risk | Evidence | Proposed follow-up |
|---|---|---|---|---|
| F1 | **Không thể chạy smoke test trial** — core pod ImagePullBackOff | Chưa verify được checklist hoạt động | `kubectl get pods -n techx-tf4` cho thấy checkout, cart, payment, product-catalog, email, shipping đều `ImagePullBackOff` | Build ECR image và deploy lại; re-run smoke test trong 24h |
| F2 | **Thiếu test data preparation step** | Người test có thể không biết cần add sản phẩm vào cart trước | Step U4-U5 đã cover add to cart | (Resolved in checklist) |
| F3 | **Grafana dashboard checkout chưa xác nhận tồn tại** | Step V5 có thể không chạy được nếu dashboard chưa có | Chưa verify được do environment chưa ready | Quyết cần confirm dashboard name hoặc tạo mới |

---

*Reviewed by: [chờ Nguyên review]*
*Status: Draft*