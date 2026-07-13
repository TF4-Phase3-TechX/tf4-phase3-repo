# Evidence Index: Mandate 01 - Network Exposure

## 1. Ngữ cảnh (Context)
Các thông tin về hệ thống tại thời điểm lấy bằng chứng được ghi nhận chi tiết tại file [`metadata.json`](./metadata.json). Thông tin bao gồm UTC window, ALB DNS, Git SHA, Helm tag, và team xác minh (CDO07).

## 2. Danh sách Bằng chứng (Evidence List)

Theo yêu cầu từ CDO04-DIRECTIVE-02 và CDO04-CROSS-TEAM-STORAGE-REQUIREMENTS cũng như Mandate 01: "Storefront công khai, mọi cổng vận hành phải riêng tư". Dưới đây là các bằng chứng (evidence) thô được thu thập từ các test độc lập (AUD-14/15/16):

| Test ID | Thành phần | Mô tả | File bằng chứng | Trạng thái dự kiến | Kết quả thực tế |
|---|---|---|---|---|---|
| AUD-14 | Storefront | Kiểm tra truy cập public vào storefront | [aud-14-storefront-curl.txt](./aud-14-storefront-curl.txt) | `HTTP 200 OK` | `PASS` |
| AUD-15 | Grafana | Kiểm tra truy cập public vào Grafana | [aud-15-grafana-curl.txt](./aud-15-grafana-curl.txt) | `HTTP 403 / 404` (Chặn public) | `PASS` |
| AUD-15 | Jaeger | Kiểm tra truy cập public vào Jaeger | [aud-15-jaeger-curl.txt](./aud-15-jaeger-curl.txt) | `HTTP 403 / 404` (Chặn public) | `PASS` |
| AUD-16 | ArgoCD | Kiểm tra truy cập public vào ArgoCD | [aud-16-argocd-curl.txt](./aud-16-argocd-curl.txt) | `HTTP 403 / 404` (Chặn public) | `PASS` |

## 3. Lưu ý Auditability
- Các file bằng chứng trên là kết quả từ lệnh `curl` trực tiếp đến các endpoint từ internet công khai.
- Bằng chứng này được lưu trữ tập trung tại đây nhằm đảm bảo bất kỳ ai (bao gồm Mentor và CDO07) đều có thể truy xuất lại "lúc đó hệ thống ở trạng thái nào, test ra kết quả gì".
