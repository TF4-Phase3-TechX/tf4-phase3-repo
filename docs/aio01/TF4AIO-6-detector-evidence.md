# TF4AIO-6 detector evidence

## Mục tiêu
- Triển khai detector dưới dạng workload Kubernetes liên tục mà không ảnh hưởng tới service lõi hoặc cơ chế flagd.
- Đặt giới hạn tài nguyên rõ ràng và ghi lại evidence để review.
- Chọn channel đầu ra đầu tiên cho detector và ghi rõ schema/payload/owner response path.

## Thay đổi thực hiện
- Thêm component Helm `detector` trong [techx-corp-chart/values.yaml](../../techx-corp-chart/values.yaml).
- Cho phép schema chấp nhận component `detector` trong [techx-corp-chart/values.schema.json](../../techx-corp-chart/values.schema.json).
- Detector chạy bằng image `busybox:1.36`, query Prometheus mỗi 60 giây và emit structured JSONL to stdout/logs; không sửa flagd hoặc config của service khác.

## Quyết định output channel
- Channel đầu tiên được chọn: `stdout-jsonl` (structured JSON lines trên stdout/logs).
- Lý do: phù hợp cho W2 minimum, dễ ingest vào logs/OpenSearch và không cần thay đổi service lõi hay flagd.
- Upgrade path cho W3: có thể chuyển sang Slack webhook, Grafana alert hoặc webhook khác nếu cần.

## Payload schema
```json
{
  "timestamp": "2026-07-14T07:30:00Z",
  "detector": "aioops-detector",
  "channel": "stdout-jsonl",
  "schema_version": "1.0",
  "incident_type": "prometheus_probe",
  "severity": "info",
  "summary": "Prometheus probe executed",
  "evidence": {
    "prometheus_url": "http://prometheus:9090/api/v1/query?query=up"
  },
  "owner": "AIOps-oncall",
  "owner_response_path": "review-runbook-and-create-ticket"
}
```

## Owner response path
- Owner (`AIOps-oncall`) đọc entry detector từ logs.
- Nếu phát hiện bất thường, owner kiểm tra evidence từ Prometheus/Grafana và cập nhật runbook hoặc tạo ticket phản ứng.
- Đường dẫn này được ghi trong biến môi trường `OWNER_RESPONSE_PATH` và payload JSON.

## Validation plan cho task 3
- Mục tiêu: validate detector với controlled load test hoặc failure drill phối hợp với CDO.
- Kịch bản đề xuất:
  1. Chạy một controlled load test lên storefront/checkout hoặc kích hoạt một failure drill nhẹ.
  2. Quan sát output detector trong logs và kiểm tra liệu detector có phát hiện degradation/incident hay không.
  3. Nếu detector không phát hiện được, ghi nhận limitation và nguyên nhân có thể là threshold quá cao, sample quá ít, hoặc dữ liệu chưa đủ.
- Kết quả cần ghi nhận:
  - Detector có catch được controlled degradation hay không.
  - Nếu không, ghi rõ limitation và next action.
  - False positive/false negative cần được record vào evidence.

## Evidence template cho validation
- Scenario: <load test / failure drill>
- Timestamp: <UTC>
- Expected signal: <latency spike / error spike / timeout>
- Detector output: <yes/no>
- Result: <caught / missed / ambiguous>
- False positive/negative: <none / details>
- Notes: <owner follow-up>

## Yêu cầu đáp ứng
- Tự động chạy: detector là Deployment liên tục, chạy theo vòng lặp nội bộ.
- Có resource limits: requests/limits đã đặt cho CPU và memory.
- Không flagd mutation: không chỉnh file flagd, không đổi command/config của flagd.
- Channel decision + payload schema + owner response path: đã được document rõ ràng.
- Evidence linked: tài liệu này nối tới chart values và planning doc.

## Lệnh kiểm tra render
- `helm template techx-corp ./techx-corp-chart > /tmp/rendered.yaml`
- `grep -n "kind: Deployment\|name: detector\|OUTPUT_CHANNEL\|schema_version" /tmp/rendered.yaml | head -n 40`
