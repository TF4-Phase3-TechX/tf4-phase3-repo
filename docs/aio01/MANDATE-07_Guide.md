# Hướng Dẫn Chi Tiết Thực Hiện MANDATE #7 — AIOps Detection

> **Nguồn gốc:** [MANDATE-07-aiops-detection.md](../../mandates/MANDATE-07-aiops-detection.md)
> **Hạn nộp:** `#7a` — Thứ Bảy 18/07/2026 · `#7b` — Thứ Bảy 25/07/2026
> **Nộp qua:** 2 Jira ticket `AI MANDATE #7a` và `AI MANDATE #7b`

---

## Mục Lục

1. [Tổng Quan & Mục Tiêu](#1-tổng-quan--mục-tiêu)
2. [Hiểu Sơ Đồ 2 Chặng (#7a và #7b)](#2-hiểu-sơ-đồ-2-chặng-7a-và-7b)
3. [Bước 1 — Chọn ≥ 3 Metrics Từ Service Trọng Yếu](#bước-1--chọn--3-metrics-từ-service-trọng-yếu)
4. [Bước 2 — Xác Định Baseline "Bình Thường"](#bước-2--xác-định-baseline-bình-thường)
5. [Bước 3 — Định Nghĩa Ngưỡng Bất Thường](#bước-3--định-nghĩa-ngưỡng-bất-thường)
6. [Bước 4 — Implement Detector + Alert Rules](#bước-4--implement-detector--alert-rules)
7. [Bước 5 — Viết ADR](#bước-5--viết-adr)
8. [Bước 6 — Nộp Jira #7a (Hạn 18/07)](#bước-6--nộp-jira-7a-hạn-1807)
9. [Bước 7 — Chạy Thật E2E + Bơm Sự Cố (#7b)](#bước-7--chạy-thật-e2e--bơm-sự-cố-7b)
10. [Bước 8 — Đo Precision/Recall/Lead-Time (#7b)](#bước-8--đo-precisionrecalllead-time-7b)
11. [Bước 9 — Alert Theo Mức Ảnh Hưởng (#7b)](#bước-9--alert-theo-mức-ảnh-hưởng-7b)
12. [Bước 10 — Nộp Jira #7b (Hạn 25/07)](#bước-10--nộp-jira-7b-hạn-2507)
13. [Checklist Hoàn Thành](#checklist-hoàn-thành)

---

## 1. Tổng Quan & Mục Tiêu

### Mandate yêu cầu gì?

Mandate #7 yêu cầu xây dựng **"đôi mắt" tự động** cho hệ thống — thay vì người phải ngồi soi Grafana, hệ thống phải **tự phát hiện bất thường và cảnh báo** trước khi user phản ánh.

| Khía cạnh | Yêu cầu | Vì sao? |
| --- | --- | --- |
| **Phát hiện đa tín hiệu** | Theo dõi latency, error rate, saturation, cost | Một loại metric không đủ; LLM có thể chậm nhưng không lỗi, hoặc lỗi nhưng không chậm |
| **Có baseline** | Biết "bình thường" là bao nhiêu theo từng service | Không có baseline → không phân biệt được spike bất thường vs tải cao bình thường |
| **Cảnh báo có ý nghĩa** | Không spam, ưu tiên triệu chứng user-visible | 100 alert/giờ = tương đương 0 alert vì on-call bỏ qua hết |
| **Chạy E2E** | Bơm sự cố → detector kêu | Chứng minh bằng hành động, không phải bằng lời |

### Kiến trúc Detection

```
Telemetry Sources                  Detection Engine              Output
┌─────────────────┐
│ Prometheus       │──metrics──►  ┌──────────────────┐
│ (OTel metrics)   │              │                  │         ┌──────────────┐
├─────────────────┤              │  Alert Rules      │────────►│ Alertmanager │
│ OpenSearch       │──logs────►  │  (PromQL/DSL)     │         │ / Dashboard  │
│ (otel-logs-*)    │              │                  │         └──────────────┘
├─────────────────┤              │  Baseline +       │
│ Jaeger           │──traces──►  │  Threshold Logic  │
│ (jaeger-span-*)  │              │                  │
└─────────────────┘              └──────────────────┘
```

---

## 2. Hiểu Sơ Đồ 2 Chặng (#7a và #7b)

Mandate #7 chia thành **2 chặng** với deadline khác nhau:

| Chặng | Nội dung | Cách chấm | Hạn |
| --- | --- | --- | --- |
| **#7a** | Implement detector + phân tích ≥3 metrics + ADR | Như **document** (chưa cần chạy thật) | T7 18/07 |
| **#7b** | Chạy thật e2e, bơm sự cố, đo precision/recall, alert theo burn-rate | **Bằng chứng chạy được** | T7 25/07 |

### Vì sao chia 2 chặng?

- **Giảm rủi ro "demo fail".** Nếu gộp tất cả vào 1 deadline mà drill thất bại (như đợt 14/07) → mất trắng. Chia ra → ít nhất #7a đạt điểm phân tích.
- **Buộc phải suy nghĩ trước khi chạy.** #7a là "thiết kế trên giấy" → hiểu bài toán rõ → #7b chạy thật hiệu quả hơn.

---

## Bước 1 — Chọn ≥ 3 Metrics Từ Service Trọng Yếu

### Phải làm gì?

Chọn tối thiểu 3 metrics từ các service nằm trên **critical path** (luồng mà user trực tiếp bị ảnh hưởng). Dưới đây là gợi ý dựa trên kiến trúc TechX:

| # | Metric | Service | PromQL / Query | Vì sao chọn? |
| --- | --- | --- | --- | --- |
| 1 | **p95 Latency** | `product-reviews`, `checkout`, `cart` | `histogram_quantile(0.95, sum by (le, service_name) (rate(traces_span_metrics_duration_milliseconds_bucket{service_name=~"product-reviews\|checkout\|cart"}[3m])))` | Latency spike = user thấy trang chậm → churn. Đây là triệu chứng user-visible rõ nhất |
| 2 | **Error Rate** | `product-reviews`, `checkout`, `cart` | `sum(rate(traces_span_metrics_calls_total{service_name=~"product-reviews\|checkout\|cart", status_code="STATUS_CODE_ERROR"}[3m])) / sum(rate(traces_span_metrics_calls_total{service_name=~"product-reviews\|checkout\|cart"}[3m]))` | Error rate tăng = request fail → user thấy lỗi. Đo burn-rate SLO trực tiếp |
| 3 | **LLM Throughput Drop** | `product-reviews` (AI) | `rate(app_ai_assistant_counter_total[3m])` | Throughput rớt về 0 trong khi có traffic = LLM chết âm thầm. Nếu chỉ đo error rate thì miss trường hợp LLM im lặng (không trả lời gì cả) |

### Vì sao phải làm bước này?

- **Mandate yêu cầu ≥ 3 metrics — đây là sàn tối thiểu.** Chọn ít hơn = không đạt #7a.
- **Mỗi metric phải có lý do rõ ràng.** Mentor sẽ hỏi "vì sao chọn p95 mà không phải p50?" → câu trả lời: p50 quá nhạy (dao động liên tục), p99 quá chậm phản ứng. p95 là cân bằng tốt nhất giữa độ nhạy và độ ổn định.
- **Metric phải đo từ telemetry thật.** Không được tự bịa metric — phải map được vào PromQL/OpenSearch query thực tế trên cluster.

> **Lưu ý quan trọng về tên metric:**
> - Span metrics có prefix `traces_span_metrics_` (ví dụ: `traces_span_metrics_calls_total`, KHÔNG phải `calls_total`).
> - OTel counter tự thêm hậu tố `_total` khi export sang Prometheus (ví dụ: `app_ai_assistant_counter` → `app_ai_assistant_counter_total`).

---

## Bước 2 — Xác Định Baseline "Bình Thường"

### Phải làm gì?

Với mỗi metric đã chọn, xác định **khoảng giá trị bình thường** dựa trên dữ liệu lịch sử hoặc quan sát cluster:

| Metric | Baseline "bình thường" | Cách xác định | Vì sao chọn khoảng này? |
| --- | --- | --- | --- |
| p95 Latency (product-reviews) | 200–800ms | Quan sát Grafana spanmetrics dashboard trong 48h traffic bình thường | Dưới 200ms = tải rất thấp (off-peak). Trên 800ms = bắt đầu gần ngưỡng SLO 2000ms |
| Error Rate (checkout) | 0–2% | Baseline từ flash-sale-alerts.yaml hiện tại | Dưới 2% = noise level bình thường (retry, transient failures) |
| LLM Throughput | > 0.1 req/s khi có traffic | Đo từ `app_ai_assistant_counter_total` trong giờ có load | Throughput > 0 chứng minh LLM đang hoạt động. = 0 khi có traffic = dead |

### Vì sao phải làm bước này?

- **Không có baseline = không phân biệt được bất thường.** p95 = 1500ms có phải bất thường không? Nếu baseline bình thường là 500ms → có, đó là spike 3x. Nếu baseline là 1200ms (service nặng) → không, chỉ tăng nhẹ.
- **Baseline theo từng service, không chung.** `checkout` có baseline latency khác `cart` vì logic nghiệp vụ khác nhau. Dùng 1 baseline chung → false positive hàng loạt.
- **Mandate yêu cầu "baseline biết thế nào là bình thường"** — thiếu mục này = #7a không đạt.

---

## Bước 3 — Định Nghĩa Ngưỡng Bất Thường

### Phải làm gì?

Với mỗi metric, xác định **thế nào thì coi là bất thường** (trigger alert):

| Metric | Ngưỡng Warning | Ngưỡng Critical | Sustained Duration | Vì sao? |
| --- | --- | --- | --- | --- |
| p95 Latency | > 1000ms | > 2000ms | 3 phút (`for: 3m`) | Warning ở 1000ms cho thời gian phản ứng. Critical ở 2000ms = SLO vi phạm. 3 phút loại bỏ cold-start noise |
| Error Rate | > 5% | > 10% | 3 phút | 5% = đáng lo. 10% = user bị ảnh hưởng rõ ràng. 3 phút loại bỏ transient spikes |
| LLM Throughput | — | == 0 khi có traffic | 3 phút | Throughput = 0 + traffic > 0 = LLM chết. Không có warning vì 0 là binary (chết hoặc sống) |

### Vì sao phải làm bước này?

- **Ngưỡng quá thấp = spam alert → on-call mệt mỏi → bỏ qua alert thật.** Đây gọi là "alert fatigue" — kẻ thù lớn nhất của monitoring.
- **Ngưỡng quá cao = miss sự cố.** Nếu đặt critical ở 5000ms thì khi SLO 2000ms đã vỡ mà detector vẫn im.
- **Duration `for: 3m` loại bỏ noise.** Container restart, connection pool warm-up tạo spike ngắn (< 1 phút). 3 phút đủ để phân biệt spike thật vs noise.
- **2 mức severity (Warning/Critical) cho phép phản ứng phân cấp.** Warning → giám sát. Critical → hành động ngay.

---

## Bước 4 — Implement Detector + Alert Rules

### Phải làm gì?

1. **Viết Prometheus Alert Rules (YAML):**
   - Tạo file `prometheus/aiops-detection-rules.yaml` (hoặc tương tự).
   - Mỗi rule có `expr` (PromQL), `for`, `labels.severity`, `annotations`.

2. **Viết OpenSearch DSL Queries:**
   - Cho các tín hiệu dựa trên log (ví dụ: LLM HTTP 429 errors).
   - Dùng `match_phrase` chính xác để tránh nhiễu.

3. **Commit code thật vào repo:**
   - Link PR cho thấy implementation có thật (không phải chỉ viết trên giấy).

### Ví dụ Alert Rule (Latency Spike)

```yaml
groups:
  - name: aiops-latency-alerts
    rules:
      - alert: AIOpsServiceLatencySpikeCritical
        expr: |
          histogram_quantile(
            0.95,
            sum by (le, service_name) (
              rate(traces_span_metrics_duration_milliseconds_bucket{
                service_name=~"product-reviews|checkout|cart"
              }[3m])
            )
          ) > 2000
        for: 3m
        labels:
          severity: critical
          team: aiops
        annotations:
          summary: "Critical latency spike on {{ $labels.service_name }}"
          description: "p95 latency = {{ $value }}ms (threshold: 2000ms) for 3+ minutes"
```

### Vì sao phải làm bước này?

- **#7a yêu cầu "đã bắt tay implement" — link PR/commit.** Nếu chỉ có phân tích trên giấy mà không có code → thiếu deliverable.
- **Code trong repo = reproducible.** Mentor clone repo, apply YAML vào Prometheus → alert rules hoạt động.
- **Alert rules là "đôi mắt" cụ thể.** Không phải concept trừu tượng — là YAML file mà Prometheus đọc và thực thi.

---

## Bước 5 — Viết ADR

### Phải làm gì?

Tạo ADR ký tên bao gồm:

| Mục | Nội dung |
| --- | --- |
| **Phương pháp phát hiện** | Rule-based (static threshold + sustained duration). Vì sao không dùng ML anomaly detection? (quá phức tạp cho MVP, cần training data lớn) |
| **Metrics đã chọn** | 3+ metrics, mỗi cái có lý do |
| **Trade-offs** | Sensitivity vs specificity (ngưỡng thấp = bắt nhiều nhưng false positive cao). Duration ngắn = phản ứng nhanh nhưng nhiều noise |
| **Giới hạn** | Univariate only (mỗi metric độc lập). Chưa correlate nhiều tín hiệu. Cold-start noise |

### Vì sao phải làm bước này?

- **#7a yêu cầu "ADR ký tên"** — đây là deliverable bắt buộc.
- **ADR giải thích vì sao chọn rule-based thay vì ML.** Với baseline traffic hiện tại (vài trăm req/s), ML model không có đủ data để train. Rule-based đơn giản, dễ debug, dễ tune.

---

## Bước 6 — Nộp Jira #7a (Hạn 18/07)

### Template ticket `AI MANDATE #7a`:

```markdown
**Summary:** AI MANDATE #7a

**Labels:** ai-mandate, m7

**Description:**
Detection · implement + phân tích

---

### 1. Link PR/Commit
- PR #XXX: [link] — implement detector + baseline + alert rules

### 2. Phân Tích ≥ 3 Metrics

#### Metric 1: p95 Latency (product-reviews, checkout, cart)
- **Vì sao chọn:** Latency spike là triệu chứng user-visible rõ nhất...
- **Baseline bình thường:** 200–800ms (đo từ Grafana spanmetrics 48h bình thường)
- **Ngưỡng bất thường:** Warning > 1000ms, Critical > 2000ms, sustained 3m
- **Phương pháp:** Static threshold trên histogram_quantile PromQL

#### Metric 2: Error Rate (product-reviews, checkout, cart)
- **Vì sao chọn:** Error rate tăng = SLO error budget bị đốt nhanh...
- **Baseline bình thường:** 0–2%
- **Ngưỡng bất thường:** Warning > 5%, Critical > 10%, sustained 3m
- **Phương pháp:** Ratio rate() PromQL

#### Metric 3: LLM Throughput Drop
- **Vì sao chọn:** LLM chết âm thầm không tạo error...
- **Baseline bình thường:** > 0.1 req/s khi có traffic vào product-reviews
- **Ngưỡng bất thường:** == 0 khi traffic > 0, sustained 3m
- **Phương pháp:** Correlation 2 tín hiệu (throughput + traffic) trong PromQL

### 3. ADR
- [Link ADR](link-to-adr-file)
```

---

## Bước 7 — Chạy Thật E2E + Bơm Sự Cố (#7b)

> **Áp dụng cho chặng #7b — hạn 25/07**

### Phải làm gì?

1. **Deploy alert rules lên cluster Prometheus.**
    - Sử dụng quy trình Controlled Drill qua GitOps; không sửa trực tiếp ConfigMap production:
      ```bash
      # 1. Ghi GitOps commit/Argo revision/flag pre-state và deployment window.
      # 2. Tạo PR chỉ đổi llmRateLimitError=on; CDO/flag owner approve + merge.
      # 3. Chờ Argo Synced/Healthy, chạy probe và thu detector/alert evidence.
      # 4. Revert PR về pre-state; chờ Argo Synced/Healthy và verify flag/pod revision.
      ```
    - Hoặc tạo load test gây latency spike.

3. **Chụp ảnh/log cho thấy detector kêu:**
   - Alertmanager UI hiển thị alert firing.
   - Hoặc Grafana dashboard hiển thị metric vượt ngưỡng + alert annotation.

### Vì sao phải làm bước này?

- **"Chạy được end-to-end" — mandate yêu cầu rõ ràng.** Code alert rule không đủ — phải chứng minh nó kêu khi có sự cố thật.
- **Bơm sự cố = controlled experiment.** Biết chính xác khi nào sự cố bắt đầu → đo được lead-time (thời gian từ sự cố đến khi alert kêu).
- **Đây là lần đầu tiên hệ thống "tự phát hiện" thay vì người soi.** Nếu thành công = mandate hoàn thành ý nghĩa cốt lõi.

---

## Bước 8 — Đo Precision/Recall/Lead-Time (#7b)

### Phải làm gì?

Mentor sẽ bơm **K sự cố** (xen kẽ với giai đoạn bình thường). Bạn đo:

| Metric | Công thức | Ý nghĩa |
| --- | --- | --- |
| **Recall** | `Số sự cố bắt được / K` | Detector có bỏ sót sự cố nào không? |
| **Precision** | `Số lần kêu đúng / Tổng số lần kêu` | Detector có kêu nhầm lúc bình thường không? |
| **Lead-Time** | `Thời điểm alert - Thời điểm sự cố bắt đầu` | Detector phản ứng nhanh cỡ nào? |

### Ví dụ tính toán

```
Mentor bơm 5 sự cố. Detector:
- Kêu đúng 4 lần (bắt được 4/5 sự cố)
- Kêu nhầm 1 lần (lúc bình thường)

Recall = 4/5 = 80%
Precision = 4/(4+1) = 80%
Lead-Time trung bình = (3m + 4m + 3m + 5m) / 4 = 3.75 phút
```

### Vì sao phải làm bước này?

- **Mandate yêu cầu "số precision/recall/lead-time"** — không có số = không đạt #7b.
- **Precision đo chất lượng alert.** Precision thấp = spam → on-call ignore → miss sự cố thật.
- **Recall đo coverage.** Recall thấp = bỏ sót sự cố → user report trước detector → vô nghĩa.
- **Lead-time đo giá trị.** Nếu lead-time = 10 phút mà user report sau 2 phút → detector thua user → chưa đạt mục tiêu "phát hiện trước user".

---

## Bước 9 — Alert Theo Mức Ảnh Hưởng (#7b)

### Phải làm gì?

1. **Phân cấp severity dựa trên user impact:**
   - `critical` = ảnh hưởng trực tiếp đến user (SLO vỡ, checkout fail).
   - `warning` = tiền dấu hiệu (latency tăng nhưng chưa vỡ SLO).

2. **Áp dụng error budget burn-rate (nếu có SLO):**
   - Thay vì cảnh báo "error rate > 10%", cảnh báo "SLO error budget burn rate > 10x" (đang "đốt" budget 10 lần nhanh hơn bình thường).

3. **Không spam:**
   - `for: 3m` đảm bảo chỉ alert sau khi vấn đề kéo dài.
   - Grouping trong Alertmanager: gom các alert cùng service thành 1 notification.

### Vì sao phải làm bước này?

- **Mandate yêu cầu "cảnh báo có ý nghĩa, không spam".** Mỗi cái gợn mà kêu = on-call burnout.
- **Burn-rate alert thông minh hơn static threshold.** Nó tự thích ứng theo SLO: 0.1% error rate trên service có SLO 99.99% nghiêm trọng hơn 1% error rate trên service có SLO 99%.
- **Mở rộng thêm service** cho thấy detector scale được, không phải hardcode cho 1 service duy nhất.

---

## Bước 10 — Nộp Jira #7b (Hạn 25/07)

### Template ticket `AI MANDATE #7b`:

```markdown
**Summary:** AI MANDATE #7b

**Labels:** ai-mandate, m7

**Description:**
Detection · chạy thật + đo đạc

---

### 1. Ảnh/Log Detector Kêu E2E
- [Ảnh Alertmanager khi bơm sự cố]
- [Ảnh Grafana dashboard khi bơm sự cố]
- **Cách chạy lại:** Link Promotion/GitOps drill PR, approval/deployment window, Argo revision, probe command và rollback PR theo controlled-drill section của guide này.

### 2. Số Precision/Recall/Lead-Time
| Metric | Giá trị |
| --- | --- |
| Recall | X/K = XX% |
| Precision | Y/Z = YY% |
| Lead-Time (avg) | X.X phút |

### 3. Alert Theo Mức Ảnh Hưởng
- Warning: [mô tả]
- Critical: [mô tả]
- Burn-rate logic: [mô tả nếu có]

### 4. Mở Rộng Service
- Đã cover: product-reviews, checkout, cart, [thêm?]
```

---

## Checklist Hoàn Thành

### #7a (hạn 18/07)

- [ ] Đã chọn ≥ 3 metrics từ service trọng yếu
- [ ] Mỗi metric có: lý do chọn, baseline bình thường, ngưỡng bất thường
- [ ] Phương pháp phát hiện đã mô tả (PromQL expression cụ thể)
- [ ] Code detector/alert rules đã commit (link PR)
- [ ] ADR đã viết và ký tên
- [ ] Jira ticket `AI MANDATE #7a` đã tạo với đủ evidence

### #7b (hạn 25/07)

- [ ] Alert rules đã deploy lên cluster Prometheus
- [ ] Đã bơm ≥ 1 sự cố và detector kêu thành công (có ảnh/log)
- [ ] Đã đo precision/recall/lead-time trên bộ sự cố có nhãn
- [ ] Alert phân cấp theo mức ảnh hưởng (warning/critical)
- [ ] Đã mở rộng thêm ít nhất 1 service so với #7a
- [ ] Jira ticket `AI MANDATE #7b` đã tạo với đủ evidence
