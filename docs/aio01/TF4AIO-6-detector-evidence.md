# TF4AIO-6 detector evidence

## Mục tiêu
- Triển khai detector dưới dạng workload Kubernetes liên tục mà không ảnh hưởng tới service lõi hoặc cơ chế flagd.
- Đặt giới hạn tài nguyên rõ ràng và ghi lại evidence để review.

## Thay đổi thực hiện
- Thêm component Helm `detector` trong [techx-corp-chart/values.yaml](../../techx-corp-chart/values.yaml).
- Cho phép schema chấp nhận component `detector` trong [techx-corp-chart/values.schema.json](../../techx-corp-chart/values.schema.json).
- Detector chạy bằng image `busybox:1.36`, query Prometheus mỗi 60 giây và in kết quả ra stdout; không sửa flagd hoặc config của service khác.

## Yêu cầu đáp ứng
- Tự động chạy: detector là Deployment liên tục, chạy theo vòng lặp nội bộ.
- Có resource limits: requests/limits đã đặt cho CPU và memory.
- Không flagd mutation: không chỉnh file flagd, không đổi command/config của flagd.
- Evidence linked: tài liệu này nối tới chart values và planning doc.

## Lệnh kiểm tra render
- `helm template techx-corp ./techx-corp-chart > /tmp/rendered.yaml`
- `grep -n "kind: Deployment\|name: detector\|resources:" /tmp/rendered.yaml | head -n 20`
