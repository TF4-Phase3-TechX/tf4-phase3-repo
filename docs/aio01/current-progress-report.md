# TF4 AIO1 — Current Progress Report

> Cập nhật: 2026-07-17 13:05 (Asia/Saigon)  
> Trọng tâm: đóng Mandate 06 production evidence + review Mandate 7a  
> Hạn 7a: 2026-07-18 · Hạn 7b: 2026-07-25

## 1. Executive status

**Mandate 06 đã hoàn tất toàn bộ runtime gate và chỉ còn named approvals trên PR closure. Mandate 7a đã đủ implementation, analysis và owner-signed ADR để đưa vào review.** Không có PR nào được tự merge hoặc Jira ticket nào được chuyển Done trước khi review hoàn tất.

| Hạng mục | Trạng thái | Evidence |
|---|---|---|
| Mandate 06 production runtime | **PASS, chờ sign-off** | [PR #280](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/280), [GitOps PR #22](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/22) |
| Mandate 06 application/safety/SLO/rollback | **PASS** | Runtime, provider-failure, observability và rollback evidence đã link trong PR #280 |
| Mandate 06 Jira | `In Review` | `TF4AIO-64` đến `TF4AIO-70` |
| Mandate 7a detector + baseline | Hoàn thành, chờ review | [PR #281](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281) |
| Mandate 7a analysis + ADR | Hoàn thành ở design/7a boundary | ADR-007 và Jira `TF4AIO-71` |
| Mandate 7a unit/integration | 20 tests pass | `techx-corp-platform/src/aiops/tests/` |
| Mandate 7a offline RCA benchmark | Hoàn thành | Top-1 0.7667, Top-3 0.9333, MRR 0.8644 |
| GitHub CI | #280 và #281 đều xanh, mergeable | Helm, YAML, Docker smoke và changed-area checks applicable |
| Mandate 7b live E2E/precision/recall | Chưa làm | Chờ merge/deploy AIOps component và controlled drill trước 2026-07-25 |

PR #280 và PR #281 hiện đều **mergeable**, không phải draft, CI xanh và đang ở trạng thái `REVIEW_REQUIRED`.

## 2. Mandate 06 — production closure

### Yêu cầu đã được kiểm chứng

Mandate 06 yêu cầu AI grounded product-review Q&A chạy qua Amazon Bedrock, không cho model tự query DB/call shopping action, chống direct/stored prompt injection, bảo vệ PII, validate citation/evidence, fail closed khi provider lỗi, không silent fallback sang mock, có telemetry token/cost và không lưu raw content trong log/trace. Model phải được chọn bằng bake-off thay vì chọn theo brand hoặc model lớn nhất.

### Kết quả implementation và production

- Bedrock Runtime dùng `Converse` qua EKS Pod Identity.
- Model thắng bake-off: `us.amazon.nova-2-lite-v1:0`.
- Guardrail accepted canary: `e2svpiawj1v5:3`.
- Pod Identity association: `a-ytlbepsjqae4uvmr7`.
- Source role account 511 assume target role account 589.
- Product Reviews generation 22: Ready/Updated/Available `1/1/1`, restart `0`.
- Load Generator đã được khôi phục Ready `1/1` sau quota-recovery window.
- Không còn AIO probe Job trong namespace.

### Runtime gates đã PASS

- Exact-image preflight trên đúng PR head/image/model/Guardrail.
- Deployed gRPC application path: grounded, unsupported, direct attack, shopping action, PII và dependency failure.
- Stored malicious review được quarantine trước provider call bằng exact production image + live Pod Identity + real Nova/Guardrail; không mutate production DB.
- Provider timeout, throttling/ClientError, deadline 4.5 giây và circuit breaker đều trả safe unavailable; không gọi mock.
- Prometheus có token, completion token, call và estimated-cost series từ successful real-model traffic.
- Storefront p95/error-rate/traffic gate PASS.
- Bedrock `Converse` p95 dưới 4.5 giây; application AI p95 dưới 5 giây.
- Private in-cluster access tới Prometheus, OpenSearch `demo-cluster` 3.6.0 và Jaeger 19 services hoạt động.
- Log/trace field-capabilities check chỉ xuất metadata; không có application prompt/question/review/response/canary field.
- Actual protected GitOps rollback evidence được giữ từ failed canary; không rollback healthy canary chỉ để tạo evidence giả.

### Closure package

- [PR #280](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/280) chứa runtime acceptance record, human review của bake-off failures, pricing snapshot, ADR-006 và checklist.
- `run_bakeoff.py` đã từ chối overwrite report canonical trừ khi chủ động dùng `--force`.
- Deployed cost series được xác nhận là `app_llm_estimated_cost_usd_USD_total`; PromQL docs đã sửa theo tên thực tế.
- PR #260 đã đóng vì bị supersede bởi clean closure PR #280; lịch sử no-go cũ vẫn được giữ để audit.
- Jira `TF4AIO-64` đến `TF4AIO-70` đã có evidence theo owner và đều ở `In Review`.

### Phần còn lại

Không còn blocker kỹ thuật/runtime cho Mandate 06. Còn đúng bước quản trị:

1. AIO1 Tech Lead review/sign-off PR #280.
2. CDO08 deployment owner xác nhận identity/canary/rollback evidence.
3. CDO-07 Audit xác nhận metadata-only trust/safety evidence.
4. Merge PR #280 rồi mới chuyển `TF4AIO-64` đến `TF4AIO-70` sang Done.

## 3. Mandate 7a implementation đã hoàn thành

Runtime hợp nhất nằm tại:

```text
tf4-phase3-repo/techx-corp-platform/src/aiops/
```

Các phần đã có:

- FastAPI AIOps worker chạy polling liên tục.
- Prometheus range-query client cho baseline và anomaly detection.
- OpenSearch log correlation dùng đúng OTel fields:
  - `resource.service.name`
  - `resource.deployment.environment`
- Jaeger trace lookup qua in-cluster path `/jaeger/ui/api/*`.
- Read-only telemetry probe: `GET /v1/telemetry/status`.
- Structured incident store với cooldown/deduplication.
- Incident detail API, audit events, RCA candidates và runbook mapping.
- Operator Markdown summary:
  - `GET /v1/incidents/{id}/summary`
  - Giữ nguyên exact evidence queries.
  - Có URL-encoded Grafana Explore link.
- Prometheus metrics endpoint tại `/metrics`.
- Helm component, ServiceAccount và RBAC.
- CI build/push support cho image `aiops`.
- GitOps promotion bootstrap cho service mới chưa tồn tại trong `image-revisions.yaml`.

### Detection methods

- Absolute safety floor để tránh adaptive baseline che mất sự cố rõ ràng.
- Ratio so với rolling baseline.
- Z-score.
- EWMA residual score.
- Isolation Forest làm supporting evidence, không tự quyết định firing.
- Sustained breach: mặc định hai polls, mỗi poll 45 giây.
- Incident cooldown: mặc định 10 phút để giảm alert spam.

### SOTA-lite được giữ lại

- **BARO-lite:** baseline-versus-incident scoring và service localization.
- **TORAI-lite:** weighted metric/log/trace/deployment/AI evidence.
- Khi source unavailable, trọng số được renormalize trên các source còn hoạt động.
- Không claim đây là full reproduction của BARO hoặc TORAI paper.

## 4. Phân tích ba signal cho Mandate 7a

Đây là **initial design baseline** cho 7a, chưa được trình bày như live production measurement. Giá trị sẽ được recalibrate bằng labelled normal window ở 7b.

| Signal | Scope | Initial normal | Anomaly gate | Method |
|---|---|---:|---|---|
| p95 span latency | `frontend`, `checkout`, `product-reviews`, `llm` | 200–800 ms | ≥1,000 ms và đồng thời ≥1.5× baseline, z-score ≥3 hoặc EWMA ≥1; sustained 2 polls | PromQL p95 + rolling statistics |
| Service error rate | Các service trọng yếu phía trên | 0–2% | ≥5% và có adaptive evidence; ≥10% là critical-equivalent; sustained 2 polls | OTel error calls / all calls |
| LLM/provider error rate | `product-reviews`, `llm` | 0–2% | ≥5% hoặc ≥3 scoped timeout/rate-limit/error logs; sustained 2 polls | `app_llm_*` counters + OpenSearch + TORAI-lite |

Metrics thực tế được query:

- `traces_span_metrics_duration_milliseconds_bucket`
- `traces_span_metrics_calls_total`
- `app_llm_calls_total`
- `app_llm_errors_total`

## 5. Full response flow

```text
Prometheus metrics --------+
OpenSearch logs -----------+--> rolling per-service baseline
Jaeger traces -------------+    --> sustained anomaly decision
                                --> RCA candidates + evidence + confidence
                                --> bounded incident store + audit log
                                --> Prometheus incident event counter
                                --> Alertmanager
                                --> Slack/email on-call notification
                                --> no approved action: runbook + escalation
                                --> approved allowlisted action: dry-run/gated rollback
                                --> rollout + p95 + error-rate verification
                                --> resolve OR restore original template + escalate
```

### Automation safety boundary

- `REMEDIATION_MODE=dry-run` là mặc định.
- Mỗi incident cần approval riêng và approval có TTL.
- Chỉ Deployment trong allowlist mới có thể được xử lý.
- Live rollback cần đồng thời bật Helm RBAC gate `aiopsRemediation.liveEnabled=true`.
- Rollout phải ready và SLO phải phục hồi.
- Verification fail thì restore original pod template và escalate.
- LLM output không được chọn hoặc execute action.
- Không đụng, tắt hoặc thay đổi incident mechanism của `flagd`.

## 6. Observability và on-call integration

Input adapters đã dùng đúng private in-cluster endpoints:

- Prometheus: `prometheus.techx-observability.svc.cluster.local:9090`
- OpenSearch: `opensearch-cluster-master.techx-observability.svc.cluster.local:9200`
- Jaeger: `jaeger.techx-observability.svc.cluster.local:16686/jaeger/ui`
- Grafana: `grafana.techx-observability.svc.cluster.local/grafana`

Output notification:

- Prometheus scrape `/metrics` từ AIOps pod.
- Incident mới increment `aiops_incidents_created_total` với labels `incident_type`, `service`, `severity`.
- Rule `AIOpsIncidentDetected` route qua Alertmanager hiện có.
- Alertmanager tiếp tục dùng Slack/email receiver do observability stack quản lý.
- Telemetry polling failure có warning rule riêng: `AIOpsTelemetryPollingDegraded`.

## 7. RCAEval-v2 benchmark

Archive nguồn:

```text
E:\xBrain-capstone3\RCAEval-v2.zip
```

Lưu ý: file có extension `.zip` nhưng thực tế là gzip-compressed tar. Benchmark reader tự detect format và stream case, không cần extract toàn bộ archive khoảng 4.46 GB.

Kết quả deterministic stratified 60-case run:

| Metric | Result |
|---|---:|
| Top-1 service localization | **0.7667** |
| Top-3 service localization | **0.9333** |
| Mean Reciprocal Rank | **0.8644** |
| Processing failures | **0** |

Evidence:

- `docs/aiops/evidence/RCAEVAL_V2_BARO_LITE_BENCHMARK.md`
- `docs/aiops/evidence/rcaeval-v2-baro-lite-results.json`

Boundary:

- Đây là offline service-localization evidence.
- Không thay thế live precision/recall/lead-time của Mandate 7b.
- Benchmark dùng metrics; runtime còn correlation log/trace.
- Dataset không được commit hoặc redistribute vì archive không chứa README/license rõ ràng.

## 8. Team work consolidation

Work của team không bị bỏ:

- Đã merge nhánh implementation với latest `origin/main` thay vì làm trên snapshot cũ.
- Đã preserve logic detector, incident store, remediation và planning SOTA-lite tồn tại trước đó.
- Đã audit [PR #208](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/208).
- Các phần độc nhất từ PR #208 đã được port vào unified runtime:
  - Correct `app_llm_*` metrics.
  - `unavailable != healthy zero` semantics.
  - Missing-source-aware weighted RCA.
  - Scoped environment/tenant incident fields.
  - Operator Markdown summary.
  - Exact evidence queries và URL-encoded Grafana Explore link.
- Không copy nguyên `aiops-detector` prototype tree để tránh hai runtime trùng chức năng.
- PR #208 vẫn được link để giữ attribution và review traceability.

## 9. Validation result

Local validation:

- `python -m pytest -q`: **20 passed**.
- `python -m compileall -q app benchmark`: pass.
- `docker compose config --quiet`: pass.
- YAML parse: pass.
- Scoped whitespace/conflict check: pass.

GitHub CI trên PR #281:

| Check | Result |
|---|---|
| Detect changed areas | Pass |
| YAML parse check | Pass |
| Helm lint and render | Pass |
| Docker smoke build checkout + shipping | Pass |
| Terraform infra plan | Correctly skipped — không có infra change |

CI có warning từ GitHub về các action dùng Node.js 20 bị force sang Node.js 24. Đây không phải failure của PR #281 nhưng nên nâng version action trong maintenance task riêng.

## 10. Jira synchronization

Mandate 06 đã được đồng bộ:

- `TF4AIO-64` đến `TF4AIO-70`: đều `In Review`.
- Mỗi ticket đã có comment evidence đúng scope owner.
- Chưa ticket nào chuyển Done trước khi PR #280 đủ approval và merge.

Evidence Mandate 7 đã được comment vào:

- `TF4AIO-71`
- `TF4AIO-73`
- `TF4AIO-74`
- `TF4AIO-75`
- `TF4AIO-76`
- `TF4AIO-78`

Các task W2/W3 cũ cũng đã được nối với implementation hợp nhất:

- `TF4AIO-38`
- `TF4AIO-41`
- `TF4AIO-42`
- `TF4AIO-43`
- `TF4AIO-44`
- `TF4AIO-45`

Không ticket nào bị chuyển Done khi vẫn còn review hoặc live evidence chưa hoàn tất.

Trạng thái hiện tại:

- `TF4AIO-71`: In Progress.
- `TF4AIO-73`: In Review.
- `TF4AIO-74`, `TF4AIO-75`, `TF4AIO-76`, `TF4AIO-78`: In Progress.

## 11. GitOps deployment sequence

Không tạo GitOps enable PR trước khi chart/image tồn tại vì GitOps CI hiện render chart revision cũ và chưa biết component `aiops`.

Thứ tự an toàn:

1. `tf4-leads` review và merge PR #281.
2. Main CI build/push image `aiops`.
3. Promotion workflow tự thêm `components.aiops.imageOverride` nếu key chưa tồn tại.
4. Workflow tạo/cập nhật GitOps `promotion/production` PR với:
   - New chart source SHA.
   - New AIOps image tag.
5. Review và merge promotion PR.
6. Tạo PR riêng bật `components.aiops.enabled=true`.
7. Chạy read-only telemetry smoke.
8. Chỉ bật live remediation trong controlled drill đã được phê duyệt.

## 12. Blockers và remaining risks

### Blocker hiện tại

- Mandate 06: không còn blocker kỹ thuật; chỉ còn named reviews/signatures trên PR #280.
- Mandate 7a: PR #281 chưa được `tf4-leads` approve/merge.
- Mandate 7b: AIOps component chưa được promotion/enable trên cluster nên chưa có live detector E2E, precision/recall hoặc lead-time evidence.

Shared production access không còn là blocker: ngày 2026-07-17 profile `511825856493_TF4-AIReadOnlyOrLimitedInvoke` đã query được cluster, và in-cluster probe đã chạm thành công Prometheus/OpenSearch/Jaeger. Cần dùng đúng `AWS_SHARED_CREDENTIALS_FILE=E:\xBrain-capstone3\.aws\credentials.txt`; profile `default` có thể hết hạn độc lập.

### Risks cần xử lý ở 7b

- Calibrate baseline bằng labelled normal production window.
- Kiểm chứng Prometheus scrape thấy AIOps counters.
- Kiểm chứng Alertmanager gửi đúng Slack/email và không duplicate spam.
- Kiểm chứng OpenSearch index/fields và Grafana datasource UID trong cluster thật.
- Đo precision, recall và lead-time trên labelled incident set.
- Kiểm chứng incident history sau pod restart; MVP hiện dùng bounded in-memory store.
- Live rollback chỉ được thử trong controlled, allowlisted incident drill.

## 13. Immediate next actions

### Trước deadline 7a

1. AIO/CDO/Audit review và merge PR #280; sau đó đóng Jira Mandate 06.
2. `tf4-leads` review PR #281.
3. Fix review comments nếu có.
4. Merge PR #281.
5. Giữ Jira `TF4AIO-71` làm canonical 7a evidence ticket.

### Sau merge, chuẩn bị 7b

1. Merge GitOps promotion PR.
2. Dùng shared read-only profile đã verify và ghi rõ environment setup trong runbook/script.
3. Enable AIOps component qua reviewed GitOps PR.
4. Chạy `/v1/telemetry/status` và lưu raw evidence.
5. Xác nhận AIOps metrics xuất hiện trong Prometheus.
6. Bơm controlled incident qua cơ chế được mentor/CDO phê duyệt.
7. Lưu detector log, incident summary, alert screenshot và notification timestamp.
8. Tính precision, recall và lead-time; cập nhật Jira 7b.

## 14. Canonical links

- Mandate 06 closure PR: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/280
- Mandate 06 accepted canary: https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/22
- Mandate 06 actual rollback: https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/16

- Mandate 7a implementation PR: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281
- Team prototype attribution: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/208
- Runtime documentation: `tf4-phase3-repo/docs/aiops/README.md`
- Signed ADR: `tf4-phase3-repo/docs/aiops/ADR-007-hybrid-anomaly-detection-and-safe-response.md`
- Benchmark report: `tf4-phase3-repo/docs/aiops/evidence/RCAEVAL_V2_BARO_LITE_BENCHMARK.md`
- Benchmark JSON: `tf4-phase3-repo/docs/aiops/evidence/rcaeval-v2-baro-lite-results.json`
