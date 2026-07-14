# Runbook: CDO08-REL-09 — An toàn deploy & Rollback

**Owner:** Quân | **Backlog:** CDO08-REL-09 | **Ngày chốt trạng thái:** 2026-07-14
**Phạm vi deploy:** image `checkout` (Go) + `shipping` (Rust) — không đổi chart, không đổi API/schema, không đổi flagd.

Runbook này chuẩn bị **trước khi merge**, để nếu có sự cố sau deploy thì thao tác theo checklist, không phải suy nghĩ giữa incident.

---

## 1. Đánh giá blast radius (vì sao deploy này khó làm chết hệ thống)

| Yếu tố | Đánh giá |
|---|---|
| Stateless | checkout & shipping đều stateless → rolling update không mất dữ liệu |
| Rolling update + readiness probe | Pod mới phải READY mới nhận traffic; pod cũ giữ traffic tới lúc đó (probe đã được team thêm từ trước, PR #85) |
| HPA | checkout có HPA (CI assert `hpas == {frontend, checkout}`) → tự scale nếu latency/CPU tăng |
| Thay đổi chỉ là client-side timeout | Không đổi contract gọi giữa services; service khác không cần biết gì |
| Deploy fail = giữ nguyên bản cũ | Nếu build-and-push fail (đặc biệt Rust — xem §2), deploy không chạy, hệ thống giữ image cũ |
| Rủi ro thật sự | (a) timeout quá chặt dưới load → false failure; (b) bug runtime trong code mới → xem trigger §5 |

**Lưu ý đã xử lý trước deploy:** khi re-verify đã phát hiện và sửa 1 blocker — đọc `resp.Body` sau khi ctx của attempt bị cancel trong `quoteShipping` (sẽ làm get-quote fail 100% dù shipping khoẻ). Chi tiết: plan doc §0.1 + §5.7. Compile không bắt được lỗi này → **bắt buộc chạy smoke test đặt hàng thật sau deploy (§4, bước T+0)**.

## 2. Trạng thái TRƯỚC deploy (đã chốt 2026-07-14 — dùng làm đích rollback)

```
Image đang chạy (rollback target):
  checkout => 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:6b5058f-checkout
  shipping => 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:6b5058f-shipping

Helm release: techx-corp, namespace techx-tf4, revision 36 (deployed)
Pod baseline:  checkout-5c779d9758-c5p44 1/1 Running 0 restart
               shipping-58bc94d85b-lp7dv 1/1 Running 0 restart
Container name trong deploy: checkout=checkout, shipping=shipping
SLO baseline: checkout success ≥ 99.0% (onboarding/SLO.md)
```

> **[Cập nhật sau code review — 2026-07-14]** PR CI (`app-smoke-build` job) giờ smoke-build **cả checkout lẫn shipping** (trước đó chỉ build checkout — đã sửa vì PR này đụng cả 2 service, Rust build fail lẽ ra phải lộ ở PR-gate thay vì chỉ lộ sau merge). Nếu Rust build fail → PR CI đỏ, chặn merge — an toàn hơn bản trước.

## 3. Checklist TRƯỚC khi merge

- [ ] CI xanh trên PR (lint/test/helm-template/docker smoke checkout).
- [ ] **KHÔNG merge trong/ngay trước cửa sổ flash-sale test 200 user** — retry đọc tạo tối đa 2x tải lên cart/product-catalog/currency khi các service này degrade, và cluster 2 node đang căng CPU (1 node ~124% limit). Deploy vào lúc traffic thấp, có người trực.
- [ ] Báo kênh team trước khi merge: deploy chạm shared release `techx-corp`, sẽ rolling-restart checkout + shipping (kinh nghiệm: mỗi lần redeploy có rủi ro `FailedScheduling: Insufficient cpu` trên cluster này — checkout/shipping request nhỏ nên rủi ro thấp hơn load-generator, nhưng phải theo dõi rollout).
- [ ] Xác nhận image tag rollback target ở §2 vẫn đúng (`kubectl -n techx-tf4 get deploy checkout shipping -o jsonpath='{range .items[*]}{.metadata.name}{" => "}{.spec.template.spec.containers[0].image}{"\n"}{end}'`).

## 4. Verify SAU deploy

### T+0 (ngay khi deploy workflow xong, bắt buộc)

```bash
# 1. Rollout hoàn tất, pod khoẻ
kubectl -n techx-tf4 rollout status deploy/checkout --timeout=180s
kubectl -n techx-tf4 rollout status deploy/shipping --timeout=180s
kubectl -n techx-tf4 get pods -l 'app.kubernetes.io/name in (checkout,shipping)'
# Pass: READY 1/1, RESTARTS 0

# 2. Log sạch — các pattern nguy hiểm phải VẮNG MẶT
kubectl -n techx-tf4 logs deploy/checkout --since=10m | grep -iE "panic|fatal|context canceled|insufficient budget"
# Pass: không dòng nào (deps đang khoẻ thì cả 4 pattern đều phải vắng)

# 3. SMOKE TEST ĐẶT HÀNG THẬT (quan trọng nhất — compile không chứng minh được get-quote sống)
#    Mở UI qua ALB, thêm sản phẩm vào giỏ, checkout hoàn chỉnh:
#    http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/
# Pass: order confirmation hiển thị, thời gian < 2s
kubectl -n techx-tf4 logs deploy/checkout --since=5m | grep -i "order placed"
# Pass: có log "order placed" của order vừa đặt
```

### T+15 phút (Grafana qua SSM tunnel — xem MANDATE-01-VERIFICATION-GUIDE.md, port 13000)

```promql
# Success rate PlaceOrder (metric đã verify tồn tại trên Prometheus cluster này)
sum(rate(traces_span_metrics_calls_total{service_name="checkout", span_name="oteldemo.CheckoutService/PlaceOrder", span_kind="SPAN_KIND_SERVER", status_code!="STATUS_CODE_ERROR"}[5m]))
/
sum(rate(traces_span_metrics_calls_total{service_name="checkout", span_name="oteldemo.CheckoutService/PlaceOrder", span_kind="SPAN_KIND_SERVER"}[5m]))
# Pass: ≥ 0.99 (hoặc NaN nếu chưa có traffic — bật Locust để có tín hiệu)

# Soi dependency nào lỗi/timeout (client span của checkout)
sum by (span_name, status_code) (rate(traces_span_metrics_calls_total{service_name="checkout", span_kind="SPAN_KIND_CLIENT"}[5m]))
```

Jaeger: mở 1 trace PlaceOrder bất kỳ → mọi client span phải có duration ≤ timeout tương ứng (§4.1 plan doc). Đây là evidence chính đính kèm Jira.

### T+60 phút

- Success rate giữ ≥ 99%, RESTARTS vẫn 0, không có pattern lỗi mới trong log.
- Nếu Locust đang chạy: so error rate với baseline trước deploy.

## 5. Ngưỡng TRIGGER rollback (thấy là làm, không debug trên production)

| # | Trigger | Ngưỡng | Hành động |
|---|---|---|---|
| 1 | Smoke test đặt hàng fail sau deploy | 2 lần liên tiếp | Rollback A ngay |
| 2 | Checkout success rate | < 95% trong 5 phút, hoặc < 99% kéo dài 10 phút (vi phạm SLO) | Rollback A ngay |
| 3 | Pod checkout/shipping | CrashLoopBackOff, hoặc RESTARTS tăng liên tục 10 phút đầu | Rollback A ngay |
| 4 | Log `context canceled` khi get-quote / `failed POST to shipping service` tăng đột biến trong khi pod shipping khoẻ | bất kỳ flood nào | Rollback A ngay (dấu hiệu lớp bug body-read còn sót) |
| 5 | Log `insufficient budget ... aborting before charge` xuất hiện đều khi deps khoẻ | > vài lần/phút | KHÔNG cần rollback — nới `CHECKOUT_OVERALL_TIMEOUT` (§7) + điều tra vì sao prep chậm |
| 6 | Quote/get-quote lỗi tăng do shipping timeout 2s quá chặt dưới load | error rate get-quote > 1% | Rollback riêng image shipping (A, chỉ shipping) |

**Nguyên tắc (đồng bộ plan doc §8):** timeout sai giá trị → chỉnh giá trị, không xóa cơ chế guard. Bug code → rollback image.

## 6. Ba phương án rollback (ưu tiên từ trên xuống)

### A — Mitigation tức thì: revert image tag (1–2 phút, chỉ chạm checkout/shipping)

```bash
kubectl -n techx-tf4 set image deploy/checkout  checkout=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:6b5058f-checkout
kubectl -n techx-tf4 set image deploy/shipping  shipping=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:6b5058f-shipping
kubectl -n techx-tf4 rollout status deploy/checkout --timeout=180s
kubectl -n techx-tf4 rollout status deploy/shipping --timeout=180s
# Verify lại bằng smoke test đặt hàng (§4 T+0 bước 3)
```

> ⚠️ Lệnh này tạo **drift so với Helm/CD** — lần deploy kế tiếp của bất kỳ ai sẽ ghi đè lại image lỗi. Vì vậy sau khi mitigation xong **PHẢI làm ngay B** để trạng thái git khớp production. Ghi chú sự cố vào kênh team + Jira ngay khi chạy A.

### B — Rollback bền vững: revert trên main qua CD (~15–25 phút, gồm review)

```bash
# Dùng nút "Revert" trên PR đã merge (GitHub tự tạo branch + PR revert), hoặc:
git checkout main && git pull
git checkout -b cdo08/week2/revert-rel-09
git revert <squash-commit-cua-PR-tren-main>
git push -u origin cdo08/week2/revert-rel-09
# Mở PR, ping Lead/Nguyên duyệt khẩn (main cần 2 approvals) → merge → CD tự build + deploy lại code cũ
```

### C — `helm rollback` (chỉ khi A không khả thi — CẨN TRỌNG)

```bash
helm history techx-corp -n techx-tf4   # xác định revision NGAY TRƯỚC deploy REL-09
helm rollback techx-corp <revision-truoc-do> -n techx-tf4 --wait --timeout 5m
```

> ⚠️ Release `techx-corp` là **shared release cả team** — rollback revision revert **toàn bộ** thay đổi giữa 2 revision, kể cả của team khác nếu họ deploy sau mình. Lịch sử release này từng có revision `failed`/`pending-upgrade` (rev 34 failed còn trong history). Chỉ dùng C khi A hỏng và đã báo team.

## 7. Chỉnh `CHECKOUT_OVERALL_TIMEOUT` không cần rollback (cho trigger #5)

```bash
# Khẩn cấp (tạo drift — sau đó phải đưa vào values để giữ qua lần deploy sau):
kubectl -n techx-tf4 set env deploy/checkout CHECKOUT_OVERALL_TIMEOUT=30s

# Chuẩn (bền qua deploy, cần Lead/mentor approve vì chạm deploy/chart):
# deploy/values-app-stamp.yaml → components.checkout.envOverrides:
#   - name: CHECKOUT_OVERALL_TIMEOUT
#     value: "30s"
```

Per-RPC timeout (cart 2s, product/currency 1s, quote 3s, payment 5s, ship 3s) là **hardcode trong binary** — muốn chỉnh phải sửa code + rebuild. Nếu per-RPC quá chặt dưới load thực tế → fix-forward tăng giá trị (không rollback cơ chế).

## 8. Hành vi cần biết (không phải bug — để không hoảng khi thấy)

1. **Kafka event có thể mất khi budget cạn:** nếu overall deadline cạn sau khi ship xong, `orderResult` không gửi được tới Kafka → accounting/fraud-detection lỡ event, nhưng **order vẫn thành công** với user. Hành vi cũ là treo vô hạn — tệ hơn. Nếu thấy accounting lệch số sau deploy, đối chiếu log `Failed to send message to Kafka within context deadline`.
2. **EmptyCart có thể bị bỏ qua khi budget cạn:** giỏ không được xóa sau order thành công (code cũ cũng đã ignore lỗi này — `_ =`). User có thể thấy giỏ còn hàng sau khi đặt.
3. **Upstream timeout chưa align:** frontend-proxy (Envoy) có thể cắt HTTP request ở timeout riêng của nó (mặc định 15s nếu không cấu hình route timeout) trước khi checkout chạm 20s → user thấy 504 dù server-side vẫn chạy tiếp. Budget-precheck đảm bảo không *bắt đầu* charge khi thiếu budget của checkout, nhưng không biết gì về deadline của Envoy. **Follow-up (không blocker):** dò route timeout thực tế của frontend-proxy và cân nhắc hạ `CHECKOUT_OVERALL_TIMEOUT` xuống dưới nó. Trước deploy này, trường hợp tương đương là treo vô hạn — mọi kịch bản mới đều không tệ hơn hiện trạng.
4. **Retry chỉ nhân đôi tải đọc khi dependency đang lỗi** (1 retry, có backoff, tôn trọng ctx) — payment/ship-order không bao giờ retry.

## 9. Nhật ký sự cố (điền khi có)

| Thời điểm | Trigger # | Hành động | Kết quả | Người thao tác |
|---|---|---|---|---|
| | | | | |
