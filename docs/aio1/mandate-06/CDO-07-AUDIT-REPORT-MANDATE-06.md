# CDO-07 Audit Report — Mandate 06

**Document type:** Audit Sign-off Record  
**Status:** Reviewed — no Audit blocker within verified scope  
**Audit owner:** CDO-07  
**Decision reference:** `ADR-006-bedrock-model-and-safety.md`  
**Đối tượng:** PR #280 — `docs(aio1): close Mandate 06 runtime acceptance`  
**Audited head:** `8abf298395f5780f3fb837bf99f57fc65e7fa5c0`  
**Tiêu chuẩn:** MANDATE-06 AI Trust & Safety và yêu cầu Auditability/metadata-only.

## 1. Phạm vi audit

Audit xác nhận:

- Evidence là metadata-only.
- Không chứa credentials, Secret, canary, prompt/review/response hoặc PII thô.
- ADR/checklist có traceability tới evidence cụ thể.
- Production evidence, synthetic/non-routing drill và historical rollback được phân biệt.
- Synthetic input trong test/runbook không được xem là retained evidence content;
  kết luận metadata-only áp dụng cho committed evidence/report/output.
- Eval có thể tái tạo từ script, dataset, schema và report đã commit.
- Safety controls có evidence cho injection, unsupported question, PII, action refusal, provider failure/fallback và no-mock-fallback.
- Human review không biến deterministic failure thành pass.
- Các limitation hoặc claim chỉ dựa trên self-attestation được ghi nhận.

Audit không thay thế CDO08 approval về Pod Identity, controlled canary, workload health, SLO hoặc rollback ownership; cũng không thay thế AIO1/Tech Lead approval về model/application.

## 2. Evidence đã kiểm tra

PR #280 thay đổi 9 file thuộc các nhóm:

- ADR-006, README và CDO handoff.
- Runtime acceptance record.
- Evidence checklist.
- Human-review record.
- Bake-off runner.
- Prometheus/cost monitoring và readiness documentation.

Các evidence liên kết đã kiểm tra:

- GitOps controlled canary PR #22.
- Exact-image preflight.
- Application/safety-path evidence.
- Provider timeout/error/deadline/circuit evidence.
- Prometheus/SLO evidence.
- OpenSearch/Jaeger metadata schema probe.
- Actual protected rollback PR #16.

## 3. Verification kết quả

Fresh verification trên đúng audited head cho kết quả:

```text
changed_files_scanned=9
report_records=270
record_fields=13
local_links_verified=30
credential_signature_matches=0
verification=PASS
```

Các kiểm tra bổ sung:

- `git diff --check`: PASS.
- `run_bakeoff.py` compile: PASS.
- `bakeoff-report.json`: 270 records.
- Report chỉ chứa metadata fields; không có raw prompt/review/response fields.
- Local Markdown links: 30/30 tồn tại.

### Phân loại mức độ kiểm chứng

- **Kiểm chứng trực tiếp trong workspace/commit:** diff, file list, JSON structure,
  record count/field set, credential-signature scan, Python compile và local links.
- **Kiểm chứng trực tiếp qua GitHub:** PR #280, PR #22, PR #16, diff, PR metadata,
  review/comment timeline và các evidence comment được liên kết.
- **Kiểm chứng trực tiếp trên EKS:** current workload readiness, pod identity
  configuration names, content-capture flag và current retained logs của
  `product-reviews`/`llm`.
- **Không kiểm chứng độc lập trong phiên này:** raw historical OpenSearch/Jaeger
  values, AWS account/role read-back và Secret values. Các nội dung này vẫn dựa
  trên evidence/attestation đã liên kết.

### Kết quả quét thực tế trên PR artifact

Đã quét toàn bộ artifact thuộc PR head bằng các kiểm tra reproducible:

- High-confidence credential signatures (`AKIA`, `ASIA`, private-key headers,
  `aws_secret_access_key`, `x-amz-security-token`, bearer token): **0 matches**.
- Report JSON: **270 records**, **13 case fields**.
- Raw-content field names (`prompt`, `question`, `review`, `response`, `answer`,
  `message`, `content`, `PII`, `canary`, `secret`, `credential`, `system_prompt`):
  **0 matches**. Trường `quarantined_reviews` là counter metadata, không phải
  review content.
- Diff-added sensitive-content signature scan: **0 matches**.
- Markdown local links: **30/30 verified**.

Đây là scan thực tế trên repository artifact ở đúng PR head. Kết quả audit trực
tiếp current retained pod logs được ghi riêng bên dưới; historical OpenSearch
storage vẫn dựa trên field-capabilities evidence và attestation đã liên kết.

### Kết quả audit trực tiếp log AI pod

Audit đã kết nối read-only tới EKS context
`arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster` và kiểm tra trực
tiếp namespace `techx-tf4`.

Workload được kiểm tra:

- `Deployment/product-reviews`, generation 22, Ready `1/1`, ServiceAccount
  `product-reviews-bedrock`.
- `Pod/product-reviews-5498f47dc8-v2h4k`, restart count 0.
- `Deployment/llm`, generation 13, Ready `1/1`.
- `Pod/llm-6698f99997-ntfgj`, restart count 0.

Phạm vi log:

| Workload | Stream | Lines | Bytes |
|---|---|---:|---:|
| `product-reviews` | current, tối đa 24 giờ/pod age | 2,427 | 642,874 |
| `product-reviews` | previous container | 0 | 0 |
| `llm` | current, tối đa 24 giờ/pod age | 14 | 7,737 |
| `llm` | previous container | 0 | 0 |

Kết quả scan trực tiếp:

| Pattern | `product-reviews` | `llm` |
|---|---:|---:|
| AWS access-key signature | 0 | 0 |
| AWS secret/session-token assignment | 0 | 0 |
| Private-key header | 0 | 0 |
| Bearer token | 0 | 0 |
| Email candidate | 0 | 0 |
| Standalone Vietnamese phone candidate | 0 | 0 |
| Raw prompt/question/review/response key | 0 | 0 |
| Raw message/content key | 0 | 0 |
| Canary label/key | 0 | 0 |

Regex phone ban đầu phát hiện 9 substring dạng số trong log `product-reviews`.
Phân loại theo line metadata cho thấy các hit nằm trong alphanumeric trace/span
identifiers; khi áp dụng boundary PII chặt, số điện thoại độc lập còn **0**.
Không có raw value nào được in hoặc đưa vào report trong quá trình phân loại.

Deployment read-back xác nhận:

- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false`.
- `BEDROCK_SYSTEM_CANARY` lấy từ Secret
  `product-reviews-bedrock-canary`, key `marker`.

Audit role bị Kubernetes RBAC từ chối `get Secret`, vì vậy không đọc hoặc hiển
thị canary value và không thể exact-match giá trị canary với log. Đây là
least-privilege control phù hợp; kết luận canary dựa trên absence of canary
field/key patterns và content-capture configuration, không phải exact-value scan.

Kết quả trên là direct pod-log audit tại thời điểm kiểm tra. Nó không bao phủ log
đã hết retention, log của pod cũ không còn tồn tại hoặc toàn bộ historical
OpenSearch storage.

## 4. Kết quả theo tiêu chí

| Tiêu chí | Kết quả | Nhận xét |
|---|---|---|
| Metadata-only evidence | PASS | Runtime, human-review và observability evidence chỉ ghi metadata/counts/status/latency/token-cost/field names |
| Credentials / Secret / canary | PASS trong artifact đã audit | Không phát hiện credential signature, access/session token, private key, Secret value hoặc canary value |
| Prompt / review / response / PII thô | PASS trong artifact đã audit | Không có raw content trong evidence package |
| ADR/checklist traceability | PASS | Có liên kết tới runtime record, human-review, eval report, canary và rollback evidence |
| Production vs synthetic evidence | PASS | Các loại evidence được phân biệt rõ |
| Eval reproducibility | PASS | Có script, dataset, schema, report và 270 records |
| Injection control | PASS dựa trên linked evidence | Có quarantine trước provider call và deployed direct-attack evidence; chưa independently rerun bởi CDO-07 |
| Unsupported question | PASS dựa trên linked evidence | Có canonical `insufficient` outcome và grounded validation; chưa independently rerun bởi CDO-07 |
| PII control | PASS trong artifact/evidence đã cung cấp | Không phát hiện PII thô trong artifact/evidence được audit; chưa xác nhận độc lập toàn bộ live cluster/historical storage |
| Action refusal | PASS dựa trên linked evidence | Shopping/checkout action bị block; chưa independently rerun bởi CDO-07 |
| Provider failure/fallback | PASS dựa trên linked evidence | Timeout, ClientError/throttling, deadline và circuit-open được báo cáo là fail closed; chưa independently rerun bởi CDO-07 |
| No silent mock fallback | PASS dựa trên linked evidence | Evidence ghi rõ không route sang mock; chưa independently rerun bởi CDO-07 |
| Human review integrity | PASS dựa trên committed review record | Failure được giữ nguyên, không manual promote; Audit không tái dựng nội dung không retain |
| Direct AI pod log audit | PASS trong current retained pod logs | Đã quét trực tiếp `product-reviews` và `llm`; không phát hiện credential, raw-content key, email hoặc standalone phone candidate |
| Independent evidence quality | PARTIAL / non-blocking | Current pod logs đã được kiểm tra trực tiếp; một số historical/runtime drill claim vẫn là AIO1-authored attestation |

## 5. Findings và limitations

### Finding A — Không có Audit blocker về raw sensitive content

Trong các artifact và evidence comment đã được cung cấp/kiểm tra, không phát hiện
credentials, Secret value, canary value, raw prompt/review/response hoặc PII.
Kết luận này không phải là tuyên bố đã quét toàn bộ live cluster hoặc mọi historical
log storage.

**Trạng thái:** PASS trong artifact/evidence đã cung cấp.

### Finding B — Traceability đầy đủ cho closure package

ADR-006, README và checklist có traceability links tới runtime acceptance,
human-review, eval report/schema/script, GitOps canary và rollback evidence;
key linked PR evidence đã được inspect, nhưng không phải mọi external link đều
được independently validated end-to-end.

**Trạng thái:** PASS — traceability links are present and key linked PR evidence was inspected.

### Finding C — Observability evidence ở mức schema/field

OpenSearch/Jaeger evidence ghi field names/counts và xác nhận không có content fields. Đây là cách phù hợp với metadata-only policy.

**Limitation:** Audit xác nhận schema/field-level evidence; không khẳng định tuyệt đối mọi historical log value trong cluster nếu không có independent raw-store retention audit.

**Trạng thái:** PASS với limitation đã ghi nhận.

### Finding D — Một phần evidence là self-attestation

Các comment runtime chính do AIO1 đăng. Có CDO08 references và approval trong GitOps flow, nhưng không phải mọi claim trong PR #280 đều có independent Audit/mentor witness trực tiếp.

**Trạng thái:** PARTIAL / non-blocking.

**Khuyến nghị:** CDO08 hoặc reviewer độc lập nên ghi comment riêng xác nhận runtime identity/canary/rollback; CDO-07 chỉ xác nhận evidence integrity và traceability.

### Finding E — Direct AI pod log audit

Current retained logs của `product-reviews` và `llm` đã được quét trực tiếp.
Không phát hiện credential/token/private-key signatures, raw prompt/review/response
keys, email hoặc standalone Vietnamese phone candidate. GenAI message-content
capture được read-back là `false`.

**Limitation:** Không có previous-container logs; Audit role không được đọc Secret
value để exact-match canary; historical logs ngoài current pod retention chưa
được quét trực tiếp.

**Trạng thái:** PASS trong current retained pod logs.

## 6. Kết luận

Trong phạm vi artifact và evidence được cung cấp, package đáp ứng yêu cầu về:

- Metadata-only evidence.
- Không phát hiện credentials, Secret, canary, prompt/review/response hoặc PII thô trong artifact/evidence đã audit.
- Traceability giữa ADR/checklist và evidence artifacts.
- Reproducibility của eval.
- Integrity của human review.
- Auditability của trust/safety và fallback controls dựa trên evidence liên kết.

Các runtime control được đánh giá dựa trên linked evidence, không phải
independent live rerun bởi CDO-07. Audit không kết luận về toàn bộ live cluster
hoặc historical log storage.

**Kết luận:** `CDO-07 AUDIT — SIGN-OFF WITH EVIDENCE-SCOPE LIMITATION / NO AUDIT BLOCKER`

Sign-off này không thay thế:

- CDO08 sign-off về Pod Identity, controlled canary, final workload health, SLO và rollback.
- AIO1/Tech Lead sign-off về model/application implementation.
