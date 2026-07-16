# TF4AIO-40 detector evidence

## Mục tiêu
- Triển khai detector dưới dạng workload Kubernetes liên tục mà không ảnh hưởng tới service lõi hoặc cơ chế flagd.
- Đặt giới hạn tài nguyên rõ ràng và ghi lại evidence để review.
- Chọn channel đầu ra đầu tiên cho detector và ghi rõ schema/payload/owner response path.

## Thay đổi thực hiện
- Thêm component Helm `detector` trong [techx-corp-chart/values.yaml](../../techx-corp-chart/values.yaml).
- Cho phép schema chấp nhận component `detector` trong [techx-corp-chart/values.schema.json](../../techx-corp-chart/values.schema.json).
- Detector chạy bằng image `busybox:1.36`, thực hiện HTTP query Prometheus mỗi 60 giây và emit structured JSONL to stdout/logs theo kết quả probe; không sửa flagd hoặc config của service khác.

## Reproducible validation setup
- Cài dependency validation: `python -m pip install -r scripts/requirements-detector.txt`
- Chạy validator portable: `python scripts/validate-detector-output.py --schema docs/aio01/evidence/detector-output-schema-v1.json --line '<one JSONL line>'`
- Chạy fixture/test deterministic: `python scripts/test_detector_fixtures.py`

## Pull request liên quan
- Implementation PR: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/137
- PR title: `TF4AIO-40: define detector output channel and payload schema`
- Reviewed head: `115a6bf4429aaf89a21a7d285cac0f06a7007013`
- Nội dung comment mô tả PR đã khớp acceptance kỹ thuật hiện tại:
  - thêm Helm-based detector workload cho chạy liên tục,
  - thêm resource requests/limits,
  - giữ nguyên flagd và incident mechanism hiện có,
  - thêm evidence documentation và planning links,
  - bổ sung contract schema và validation thực sự.

## Quyết định output channel
- Channel đầu tiên được chọn: `stdout-jsonl` (structured JSON lines trên stdout/logs).
- Lý do: phù hợp cho W2 minimum, dễ ingest vào logs/OpenSearch và không cần thay đổi service lõi hay flagd.
- Upgrade path cho W3: có thể chuyển sang Slack webhook, Grafana alert hoặc webhook khác nếu cần.

## Payload schema

Machine-readable contract: [docs/aio01/evidence/detector-output-schema-v1.json](./evidence/detector-output-schema-v1.json)

Compatibility rule:
- `schema_version=1.0` giữ backward compatibility cho consumer hiện tại.
- Field mới chỉ được thêm theo hướng additive; không đổi semantic các field required hiện có trong major `1.x`.

Field contract (`schema_version=1.0`):

| Field | Required | Type | Constraints / Enum | Notes |
| --- | --- | --- | --- | --- |
| `timestamp` | yes | string | RFC3339 UTC | thời điểm emit event |
| `detection_id` | yes | string | non-empty | rule-id + timestamp |
| `detector` | yes | string | `aioops-detector` | detector identity |
| `service` | yes | string | non-empty | affected service |
| `environment` | yes | string | non-empty | runtime env/namespace scope |
| `channel` | yes | string | `stdout-jsonl` | output channel hiện tại |
| `schema_version` | yes | string | `1.0` | payload version |
| `incident_type` | yes | string | `prometheus_probe_ok`/`prometheus_probe_empty`/`prometheus_probe_error` | probe outcome |
| `severity` | yes | string | `info`/`warning`/`critical` | routing severity |
| `summary` | yes | string | non-empty | human summary |
| `observed_value` | yes | string | non-empty | observed metric/result |
| `threshold` | yes | string | non-empty | rule threshold |
| `runbook_url` | yes | string | URI | runbook destination |
| `owner` | yes | string | non-empty | current owner |
| `owner_response_path` | yes | string | non-empty | escalation action |
| `evidence.prometheus_url` | no | string | non-empty | query endpoint |

Validation smoke check cho một emitted line:
```bash
kubectl -n techx-tf4 logs deploy/detector --tail=1 | python scripts/validate-detector-output.py --schema docs/aio01/evidence/detector-output-schema-v1.json
```

```json
{
  "timestamp": "2026-07-14T07:30:00Z",
  "detection_id": "prometheus-up-probe-v1-2026-07-14T07:30:00Z",
  "detector": "aioops-detector",
  "service": "prometheus",
  "environment": "techx-observability",
  "channel": "stdout-jsonl",
  "schema_version": "1.0",
  "incident_type": "prometheus_probe_ok",
  "severity": "info",
  "summary": "Prometheus probe succeeded with up==1",
  "observed_value": "1",
  "threshold": "at_least_one_up_target",
  "runbook_url": "https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/audit/runbooks/detector-prometheus-probe.md",
  "evidence": {
    "prometheus_url": "http://prometheus.techx-observability.svc.cluster.local:9090/api/v1/query?query=up%20%3D%3D%201"
  },
  "owner": "AIOps-oncall",
  "owner_response_path": "open-runbook-then-create-incident-ticket"
}
```

## Owner response path
- Owner (`AIOps-oncall`) đọc entry detector từ logs.
- Nếu `incident_type=prometheus_probe_empty` hoặc `prometheus_probe_error`, owner mở runbook ở `runbook_url` và tạo incident ticket theo `owner_response_path`.
- Payload đã có các field phục vụ route/escalation trực tiếp: `service`, `environment`, `detection_id`, `observed_value`, `threshold`, `runbook_url`.
- Đường dẫn escalation được ghi trong biến môi trường `OWNER_RESPONSE_PATH` và payload JSON.

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

## Evidence update theo review 2026-07-15

### Positive evidence (repo + manifest)
- Chart values có component detector: [techx-corp-chart/values.yaml](../../techx-corp-chart/values.yaml).
- Chart schema chấp nhận detector: [techx-corp-chart/values.schema.json](../../techx-corp-chart/values.schema.json).
- Helm render thành công và sinh Deployment detector kèm env/output schema/resource limits: [docs/aio01/evidence/tf4aio40-detector-render-snippet.yaml](./evidence/tf4aio40-detector-render-snippet.yaml).
- Payload contract machine-readable: [docs/aio01/evidence/detector-output-schema-v1.json](./evidence/detector-output-schema-v1.json).
- Validation script: [scripts/validate-detector-output.py](../../scripts/validate-detector-output.py).
- Deterministic fixture test: [scripts/test_detector_fixtures.py](../../scripts/test_detector_fixtures.py).
- Validation dependency manifest: [scripts/requirements-detector.txt](../../scripts/requirements-detector.txt).
- Concrete runbook: [docs/audit/runbooks/detector-prometheus-probe.md](../../docs/audit/runbooks/detector-prometheus-probe.md).

### Negative evidence / blocker (cluster runtime)
- Chưa lấy được bằng chứng live inventory trong namespace `techx-tf4` do local kube context chưa được cấu hình.
- `kubectl config current-context` trả về `error: current-context is not set`.
- `kubectl get ns` trả về kết nối mặc định `http://localhost:8080` bị từ chối.
- `aws sts get-caller-identity` trả về `InvalidClientTokenId` nên chưa chạy được bước cập nhật kubeconfig EKS.

### Bounded conclusion
- Detector đã ở trạng thái deploy-ready và đáp ứng acceptance kỹ thuật ở mức manifest:
  - workload chạy tự động dạng continuous Deployment,
  - có requests/limits,
  - không có thay đổi flagd/openfeature,
  - có evidence link và schema output.
- Cluster deployment impact (pod/deployment inventory thực tế trong `techx-tf4`) đang pending do blocker xác thực hạ tầng, chưa thể xác nhận từ môi trường hiện tại.

## Lệnh verify khi credential sẵn sàng

### 1) Thiết lập kube context EKS
```bash
aws eks update-kubeconfig --name <cluster-name> --region <region>
kubectl config current-context
```

### 2) Chứng minh detector có mặt trong inventory
```bash
kubectl -n techx-tf4 get deploy detector -o wide
kubectl -n techx-tf4 get pods -l app.kubernetes.io/name=detector -o wide
kubectl -n techx-tf4 logs deploy/detector --tail=20
```

### 3) Chứng minh không có flagd mutation
```bash
kubectl -n techx-tf4 get deploy flagd -o yaml > /tmp/flagd-current.yaml
git diff -- techx-corp-chart/values.yaml techx-corp-chart/values.schema.json
```

## Tham chiếu review drill
- Tổng hợp positive/negative evidence của silent attack drill: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/138
