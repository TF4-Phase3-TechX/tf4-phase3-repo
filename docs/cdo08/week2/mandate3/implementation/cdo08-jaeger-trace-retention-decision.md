# Báo cáo CDO08 - Jaeger Trace Retention và Persistence

| Hạng mục | Giá trị |
| --- | --- |
| Phạm vi | Lưu trữ trace Jaeger phục vụ mandate Week 2 |
| Pillar | Reliability, Auditability, Security |
| Ngày kiểm tra | 2026-07-13 |
| Trạng thái | Đã xác nhận issue trên runtime; đã cập nhật chart values để review/deploy |
| Quyết định | Dùng OpenSearch làm persistent trace backend cho Jaeger, bật OpenSearch PVC và retention cleaner 3 ngày |

## 1. Tóm tắt

Jaeger hiện đang lưu trace trong memory. Đây không chỉ là rủi ro từ cấu hình tĩnh. Runtime evidence cho thấy pod Jaeger đã restart nhiều lần và gần đây bị `OOMKilled` dù memory request/limit đã được tăng lên `768Mi`.

Vấn đề này ảnh hưởng đến Directive #2 vì bài kiểm tra flash sale yêu cầu evidence cho workload 200 concurrent users trong 15 phút. Nếu Jaeger chỉ giữ trace trong memory, trace ở đầu hoặc giữa bài test có thể bị ghi đè hoặc mất trước khi mentor/CDO07 kịp verify.

Hướng đã chọn:

- Không giải quyết bằng cách chỉ tăng memory cho Jaeger.
- Dùng persistent trace backend.
- Tận dụng OpenSearch hiện có làm trace backend cho Jaeger.
- Bật OpenSearch persistence/PVC trước khi lưu trace vào OpenSearch.
- Đặt retention ngắn cho trace để kiểm soát chi phí.
- Dùng sampling policy để giảm trace volume nhưng không làm mất checkout/payment/error evidence.

## 2. Hiện trạng

### 2.1 Runtime Jaeger

Runtime `Deployment/jaeger`:

```text
Namespace: techx-observability
Image: jaegertracing/jaeger:2.17.0
Helm chart: jaeger-4.7.0
MEMORY_MAX_TRACES=25000
Memory request/limit: 768Mi / 768Mi
```

Runtime `ConfigMap/user-config`:

```yaml
jaeger_query:
  storage:
    traces: memory_backend

jaeger_storage:
  backends:
    memory_backend:
      memory:
        max_traces: ${env:MEMORY_MAX_TRACES}

exporters:
  jaeger_storage_exporter:
    trace_storage: memory_backend
```

Runtime pod evidence:

```text
Restart Count: 14
Last State: Terminated
Reason: OOMKilled
Exit Code: 137
```

Kết luận: Jaeger đang đọc và ghi trace từ `memory_backend`, và pod đã có bằng chứng memory pressure trên runtime.

### 2.2 Runtime OpenSearch

OpenSearch đang tồn tại trong observability stack:

```text
statefulset.apps/opensearch   1/1
service/opensearch            ClusterIP 9200/TCP,9300/TCP,9600/TCP
```

Tuy nhiên namespace hiện không có PVC:

```text
kubectl -n techx-observability get pvc
No resources found in techx-observability namespace.
```

Parent chart trước thay đổi đang tắt OpenSearch persistence:

```yaml
opensearch:
  persistence:
    enabled: false
```

Kết luận: OpenSearch có tồn tại, nhưng hiện chưa phải durable storage backend.

## 3. OpenSearch hiện đang lưu gì?

OpenSearch hiện đang dùng để lưu logs, chưa dùng để lưu Jaeger traces.

OTel Collector pipeline trong `techx-corp-chart/values.yaml`:

```yaml
service:
  pipelines:
    traces:
      exporters: [otlp/jaeger, debug, spanmetrics]
    metrics:
      exporters: [otlphttp/prometheus, debug]
    logs:
      exporters: [opensearch, debug]
```

OpenSearch exporter:

```yaml
opensearch:
  logs_index: otel-logs
  logs_index_time_format: "yyyy-MM-dd"
  http:
    endpoint: http://opensearch:9200
```

Grafana OpenSearch datasource:

```yaml
database: otel-logs-*
type: grafana-opensearch-datasource
url: http://opensearch:9200/
```

Luồng dữ liệu hiện tại:

```text
Traces  -> Jaeger memory backend
Metrics -> Prometheus
Logs    -> OpenSearch index otel-logs-*
```

Nếu chuyển Jaeger traces sang OpenSearch, OpenSearch sẽ trở thành backend dùng chung cho logs và traces. Hướng này hợp lý vì tận dụng component có sẵn, nhưng sẽ làm tăng áp lực storage và ingestion. Vì vậy phải đi kèm persistence, retention và capacity review.

## 4. Mapping với mandate

### Directive #1 - Storefront public, operational portals private

Yêu cầu liên quan:

- Storefront vẫn public.
- Jaeger không được public internet truy cập.
- Mentor vẫn phải có cách truy cập Jaeger qua đường private khi cần kiểm tra.

Trạng thái:

- Runbook `CDO08-SEC-05` xác nhận Jaeger hiện public tại `/jaeger/ui/`.
- Phương án private access đã chốt: SSM Bastion + internal ALB.
- Public ALB chỉ giữ storefront.
- Jaeger và các operational portals đi qua internal ALB, người có quyền truy cập bằng SSM Bastion.

Kết luận từ báo cáo này:

- Việc làm persistent trace cho Jaeger không được làm Jaeger public trở lại.
- Jaeger trace retention phải hoạt động sau khi Jaeger được đưa vào private access path.
- Mentor/BTC kiểm tra Jaeger qua SSM Bastion tới internal ALB, không dùng public ALB.

### Directive #2 - Flash sale trong ngân sách

Yêu cầu liên quan:

- 200 concurrent users trong 15 phút qua load-generator.
- Giữ SLO: checkout >= 99%, browse/cart >= 99.5%, storefront p95 < 1s.
- Không vượt budget hiện tại.
- Nộp load-test result và cho mentor cách re-check hoặc chứng kiến test.

Ảnh hưởng tới Jaeger:

- Trace retention phải cover ít nhất toàn bộ bài test 15 phút cộng thêm thời gian review.
- Trace evidence phải sống sót qua Jaeger restart trong hoặc sau bài test.
- Storage/cost phải nằm trong budget hiện tại.

Kết luận từ báo cáo này:

- Retention tối thiểu nên là 24 giờ sau acceptance run.
- Retention tốt hơn là 72 giờ nếu storage cost và node headroom cho phép.
- Checkout/payment/error traces nên được giữ 100% trong acceptance window nếu capacity cho phép.

## 5. Findings từ chart

### 5.1 Jaeger chart có pattern dùng Elasticsearch-style backend

Chart `techx-corp-chart/charts/jaeger-4.7.0.tgz` có ví dụ `userconfig` dùng Elasticsearch backend:

```yaml
jaeger_query:
  storage:
    traces: primary_store

jaeger_storage:
  backends:
    primary_store:
      elasticsearch:
        server_urls: ["http://jaeger-elasticsearch-es-jaeger:9200"]

exporters:
  jaeger_storage_exporter:
    trace_storage: primary_store
```

Chart cũng có các Elasticsearch maintenance jobs:

- `esIndexCleaner`
- `esRollover`
- `esLookback`

Các job này đang disabled mặc định và cần được review nếu dùng Elasticsearch/OpenSearch index retention.

Ý nghĩa:

- Chart có sẵn pattern để chuyển khỏi `memory_backend`.
- Backend key là `elasticsearch`, không phải `opensearch`.
- Cần verify compatibility giữa OpenSearch và Jaeger `2.17.0`, vì OpenSearch tương thích nhiều Elasticsearch API nhưng không nên mặc định là mọi feature/config đều chạy.

### 5.2 OpenSearch chart hỗ trợ PVC, nhưng parent values đang tắt

Default của bundled OpenSearch chart:

```yaml
persistence:
  enabled: true
  size: 8Gi
```

Current parent override:

```yaml
opensearch:
  persistence:
    enabled: false
```

Runtime cũng xác nhận không có PVC.

Ý nghĩa:

- Chart đã hỗ trợ cấu hình persistent volume.
- Deployment hiện tại chủ động tắt persistence.
- Chuyển Jaeger traces sang OpenSearch mà không bật persistence là không đạt mục tiêu.

## 6. Quyết định và thay đổi chart

Quyết định:

```text
Dùng OpenSearch làm persistent trace backend cho Jaeger,
đồng thời bật OpenSearch persistence/PVC và retention cleaner.
```

Lý do:

- OpenSearch đã tồn tại trong observability stack.
- Jaeger chart có pattern cấu hình backend kiểu Elasticsearch.
- OpenSearch phù hợp hơn Jaeger RAM cho dữ liệu observability cần index/query theo thời gian.
- Persistent OpenSearch storage giúp trace sống sót qua Jaeger pod restart.
- Retention/TTL kiểm soát tăng trưởng storage và cost.
- Sampling kiểm soát ingestion volume khi load test.

Đây không phải quyết định "chỉ cần lưu trace vào OpenSearch". Đây là một quyết định gồm bốn phần:

```text
Jaeger memory_backend -> OpenSearch backend
OpenSearch ephemeral storage -> OpenSearch PVC
Unlimited growth risk -> retention cleaner 3 ngày
High trace volume risk -> sampling policy
```

Thay đổi đã thực hiện trong `techx-corp-chart/values.yaml`:

```yaml
jaeger:
  jaeger:
    storage:
      type: elasticsearch
  userconfig:
    extensions:
      jaeger_query:
        storage:
          traces: opensearch_backend
      jaeger_storage:
        backends:
          opensearch_backend:
            elasticsearch:
              server_urls: ["http://opensearch:9200"]
    exporters:
      jaeger_storage_exporter:
        trace_storage: opensearch_backend
  storage:
    type: elasticsearch
    elasticsearch:
      url: http://opensearch:9200
  esIndexCleaner:
    enabled: true
    numberOfDays: 3
```

```yaml
opensearch:
  protocol: http
  persistence:
    enabled: true
    size: 8Gi
```

Các điểm không thay đổi trong task này:

- Không sửa public/internal ingress.
- Không sửa SSM Bastion hoặc internal ALB.
- Không đổi OTel Collector trace exporter, vì collector đã gửi trace tới service `jaeger:4317`.

## 7. Phương án và trade-off

| Phương án | Tóm tắt | Ưu điểm | Nhược điểm | Quyết định |
| --- | --- | --- | --- | --- |
| A | Tăng RAM Jaeger / `MEMORY_MAX_TRACES` | Nhanh, đơn giản | Vẫn mất trace khi restart; runtime đã OOMKilled ở 768Mi; tăng node pressure | Không chọn làm hướng chính |
| B | Chỉ dùng sampling | Giảm memory/cost pressure | Không giải quyết persistence; có thể làm mất evidence cần verify | Dùng như guardrail bổ sung |
| C | Jaeger -> OpenSearch với PVC + retention | Tận dụng stack hiện có; trace sống sót qua Jaeger restart; hỗ trợ mentor/CDO07 re-check | Cần deploy/test compatibility và theo dõi disk/memory | Đã chọn |
| D | Managed/external trace backend | Tốt hơn cho dài hạn | Tăng cost, credential, network/IAM complexity | Để sau, trừ khi OpenSearch path bị chặn |

## 8. Kế hoạch triển khai đề xuất

### Phase 1 - Render configuration

- Render chart sau khi đổi Jaeger trace storage từ `memory_backend` sang Elasticsearch-compatible backend trỏ tới `http://opensearch:9200`.
- Giữ metrics backend trên Prometheus.
- Render chart và xác nhận:
  - Jaeger query dùng persistent backend cho traces.
  - `jaeger_storage_exporter` ghi vào persistent backend.
  - Trace storage config không còn reference `memory_backend`.

### Phase 2 - Bật OpenSearch persistence

- Bật `opensearch.persistence.enabled`.
- Dùng PVC size ban đầu `8Gi`.
- Bắt đầu với retention 3 ngày bằng `esIndexCleaner.numberOfDays: 3`.
- Xác nhận `kubectl -n techx-observability get pvc` thấy OpenSearch PVC.
- Xác nhận OpenSearch vẫn healthy sau rollout.

### Phase 3 - Deploy Jaeger persistent backend

- Deploy thay đổi config Jaeger.
- Xác nhận log Jaeger initialize persistent backend thay vì `memory_backend`.
- Xác nhận OTel Collector vẫn export traces.
- Chạy checkout smoke test và verify trace trong Jaeger UI/API.

### Phase 4 - Retention và sampling

- Verify CronJob `jaeger-es-index-cleaner` được tạo.
- Trong acceptance:
  - Giữ 100% checkout/payment/error traces nếu capacity cho phép.
  - Sample lower-value traces nếu trace volume đe dọa capacity của OpenSearch.
- Sau acceptance:
  - Giảm sampling nếu cần để hạ cost vận hành.

### Phase 5 - Persistence test

- Tạo một trace đã biết.
- Query trace đó trong Jaeger.
- Restart Jaeger pod.
- Query lại cùng trace.
- Pass nếu trace vẫn còn trong retention window.

## 9. Verification checklist

Trước thay đổi:

```bash
date -Iseconds
kubectl -n techx-observability get deploy jaeger -o yaml
kubectl -n techx-observability get configmap user-config -o yaml
kubectl -n techx-observability describe pod -l app.kubernetes.io/name=jaeger
kubectl -n techx-observability get pvc
```

Sau thay đổi:

```bash
date -Iseconds
kubectl -n techx-observability get pvc
kubectl -n techx-observability rollout status deploy/jaeger
kubectl -n techx-observability logs deploy/jaeger --tail=120
kubectl -n techx-observability get pod -l app.kubernetes.io/name=jaeger
kubectl -n techx-observability get cronjob | grep jaeger-es-index-cleaner
```

Trace persistence test:

```text
1. Tạo một checkout trace.
2. Query trace đó trong Jaeger.
3. Restart Jaeger pod.
4. Query lại cùng trace.
5. Pass nếu trace vẫn còn.
```

Acceptance evidence:

- Trace ở đầu, giữa và cuối bài test 15 phút.
- Jaeger restart count không tăng trong lúc chạy test.
- Không có `OOMKilled` mới.
- OpenSearch PVC tồn tại và còn disk headroom.
- Retention cleaner CronJob tồn tại.
- Jaeger truy cập được qua SSM Bastion + internal ALB sau hardening SEC-05.

## 10. Rollback

Rollback triggers:

- Jaeger không ready.
- Jaeger UI không query được traces.
- OTel Collector không export được traces.
- OpenSearch unhealthy hoặc bị disk pressure.
- Storefront hoặc checkout bị ảnh hưởng gián tiếp do observability pressure.

Rollback path:

1. Helm rollback về observability release trước đó.
2. Nếu cần, tạm thời đưa Jaeger về `memory_backend`.
3. Giảm trace volume bằng sampling trong lúc sửa persistent storage.
4. Ghi rõ limitation: rollback về memory backend nghĩa là trace không persistent.

Không dùng hướng tăng memory vô hạn làm rollback nếu node headroom chưa được xác nhận.

## 11. Khuyến nghị cuối

Chỉ merge/deploy OpenSearch-backed Jaeger storage khi các điều kiện sau đã được đáp ứng:

- OpenSearch persistence được render đúng và tạo PVC sau deploy.
- Retention cleaner 3 ngày được render đúng.
- Config Jaeger tương thích OpenSearch/Elasticsearch đã được render và test.
- Sampling policy giữ checkout/payment/error traces trong acceptance window.
- Private access vào Jaeger dùng SSM Bastion + internal ALB theo SEC-05.
- Cost và capacity đã được review trước rollout.

Mitigation ngắn hạn nếu chưa kịp triển khai trước acceptance:

- Tạm giữ Jaeger memory backend.
- Không tăng memory mù quáng.
- Giảm trace volume bằng sampling.
- Capture trace evidence ngay trong lúc chạy test.
- Ghi rõ limitation: evidence có thể mất nếu Jaeger restart.
