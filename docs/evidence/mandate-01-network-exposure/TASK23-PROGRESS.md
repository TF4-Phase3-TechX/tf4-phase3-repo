# Task 23 — Tiến độ và hướng đi

| Task | Independent Verification — Mandate-01 for CDO04 |
|---|---|
| Owner | CDO07 — [Tên] |
| File output chính | `VERIFICATION-REPORT.md` |
| ALB thật | `k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com` |

---

## Phân loại: làm ngay vs chờ

```
LÀM NGAY (hôm nay, không cần ai):
  ✅ ST-3.1  — Chuẩn bị môi trường
  ✅ ST-3.2  — Curl test external / baseline "before"

CHỜ CDO08 (SEC-05 deploy + Bastion):
  ⏳ ST-3.2  — Curl test "after" (routes phải 404)
  ⏳ ST-3.3  — SSM tunnel test (private access phải pass)

CHỜ CDO04 (access Prometheus/Locust):
  ⏳ ST-3.4  — Raw stats load test
```

---

## File mapping

| Sub-task | File điền output | Trạng thái |
|---|---|---|
| ST-3.1 | `st31-env-setup.txt` | Tạo mới — điền ngay |
| ST-3.2 before | `st32-curl-before.txt` | Tạo mới — điền ngay |
| ST-3.2 after | `st32-curl-after.txt` | Tạo mới — điền khi CDO08 xong |
| ST-3.3 | `st33-vpn-tunnel.txt` | Tạo mới — điền khi CDO08 xong |
| ST-3.4 | `st34-loadtest-stats.txt` | Tạo mới — điền khi CDO04 ready |
| ST-3.5 | `VERIFICATION-REPORT.md` | Tạo mới — tổng hợp cuối |
