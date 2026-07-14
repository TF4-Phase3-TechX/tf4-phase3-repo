# AUD-14 — Storefront public access

**Reviewer:** Bùi Thành Nghĩa
**Team thực hiện:** CDO07
**Ngày thực hiện:** 2026-07-14

## Lệnh kiểm tra

```bash
ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"
curl -sS -D - -o /dev/null "$ALB/"
```

## Bằng chứng thực tế (Output)

```text
HTTP/1.1 200 OK
Date: Tue, 14 Jul 2026 00:13:17 GMT
Content-Type: text/html; charset=utf-8
Content-Length: 11347
Connection: keep-alive
cache-control: private, no-cache, no-store, max-age=0, must-revalidate
x-powered-by: Next.js
etag: "xx8rtnan878r7"
vary: Accept-Encoding
x-envoy-upstream-service-time: 8
server: envoy
```

## Kết luận

**Trạng thái:** ✅ PASS
Storefront hiện đang mở public đúng như yêu cầu của Mandate 01, phản hồi mã `200 OK`.
