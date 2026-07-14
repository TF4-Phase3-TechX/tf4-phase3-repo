# AUD-15 — Jaeger public access test

**Reviewer:** Bùi Thành Nghĩa
**Team thực hiện:** CDO07
**Ngày thực hiện:** 2026-07-14

## Lệnh kiểm tra

```bash
ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"
curl -sS -D - -o /dev/null "$ALB/jaeger/ui/"
```

## Bằng chứng thực tế (Output)

```text
HTTP/1.1 404 Not Found
Date: Tue, 14 Jul 2026 00:13:35 GMT
Content-Length: 0
Connection: keep-alive
server: envoy
```

## Kết luận

**Trạng thái:** ✅ PASS
Jaeger đã bị chặn truy cập từ Public Internet (trả về mã lỗi 404), đúng theo yêu cầu của Mandate 01 về việc giới hạn các cổng vận hành nội bộ.
