# CDO-04 — Tổng hợp Gap Performance + Cost

## 1. Mục tiêu

Tài liệu này tổng hợp lại các lỗ hổng thuộc phạm vi **CDO-04** sau khi đối chiếu lại Gap Assessment, Gap-to-Pillar Mapping và EPIC-01 checklist.

Phạm vi của nhóm CDO-04:

- **Performance Efficiency** — Hiệu quả hiệu năng
- **Cost Optimization** — Tối ưu chi phí

Mục tiêu của file này:

- Chỉ lọc các gap thuộc phạm vi Performance + Cost.
- Phân biệt gap nào nhóm CDO-04 sở hữu chính, gap nào nhóm chỉ hỗ trợ.
- Ghi rõ mức độ ưu tiên, evidence cần có, runtime validation cần làm và follow-up cho W2+.
- Dùng làm input cho Week 1 Pitch, EPIC-01 gap summary và remediation backlog.

---

## 2. Nguồn tài liệu đã đối chiếu

| Nguồn | Mục đích sử dụng |
|---|---|
| `docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md` | Xác định gap gốc và tác động |
| `docs/GAP-TO-PILLAR-MAPPING.md` | Xác định gap nào thuộc phạm vi CDO-04 |
| `docs/epic-01-addressing-system-gap/EPIC-01-SYSTEM-GAP-FIX-CHECKLIST.md` | Xác định evidence file, validation và điều kiện hoàn thành |
| Runtime evidence của nhóm | Đối chiếu với trạng thái deploy, performance và cost hiện tại |

---

## 3. Tóm tắt phạm vi CDO-04

Theo Gap-to-Pillar Mapping, CDO-04 sở hữu:

```txt
Performance Efficiency + Cost Optimization
```

CDO-04 có tổng cộng **5 owned gaps**, toàn bộ ở mức **Medium**:

| Trụ | Số gap sở hữu | Mức độ |
|---|---:|---|
| Performance Efficiency | 2 | Medium x2 |
| Cost Optimization | 3 | Medium x3 |
| Tổng cộng | 5 | Medium x5 |

Ngoài ra, CDO-04 còn hỗ trợ một số phần cross-pillar:

- Performance cung cấp baseline p95/p99 latency cho `REL-04` timeout budget.
- Cost review resource impact cho `K8S-02` replica/PDB baseline.
- Cost cung cấp input cho trade-off `K8S-04` managed service vs PVC.

---

## 4. Các gap CDO-04 sở hữu

| Gap ID | Trụ | Mức độ | Gap | Trạng thái hiện tại | Đầu ra Week 1 | Hướng xử lý W2+ |
|---|---|---|---|---|---|---|
| `PERF-01` | Performance | Medium | N currency conversions trên mỗi browse page | Đã xác nhận qua source review | Phân tích bottleneck dựa trên source + kế hoạch metric | Cache/batch currency conversion, validate bằng Jaeger trace fan-out |
| `PERF-02` | Performance | Medium | Search query không giới hạn và khó tận dụng index | Đã xác nhận qua source review | Phân tích bottleneck dựa trên source + kế hoạch đo | Thêm LIMIT/pagination/index; validate bằng `EXPLAIN ANALYZE` |
| `COST-01` | Cost | Medium | Load-generator tự chạy trong default values | Đã xác nhận qua config/runtime scan | Làm rõ hành vi load-generator | Đảm bảo môi trường giống production không tự sinh synthetic load |
| `COST-02` | Cost | Medium | Observability stack nặng/overkill nhưng vẫn OOMKilled và chưa có durability rõ ràng | Đã xác nhận qua config + runtime OOMKilled evidence | Ghi nhận footprint, OOMKilled và trade-off retention/right-sizing | Right-size Grafana/Jaeger, giảm overkill an toàn và định nghĩa retention/persistence |
| `K8S-03` | Cost | Medium | Resource model chưa hoàn chỉnh; có nguy cơ conflict với `quota.yaml` | Cần runtime validation | Ghi nhận measured resource baseline / quota gap | Thêm requests/limits sau khi có runtime metrics và quota validation |

---

## 5. Review chi tiết từng gap

### 5.1 PERF-01 — N currency conversions trên mỗi browse page

| Hạng mục | Chi tiết |
|---|---|
| Trụ | Performance Efficiency |
| Mức độ | Medium |
| Chủ sở hữu | CDO-04 |
| Nguồn evidence | `ProductCatalog.service.ts` |
| Component bị ảnh hưởng | `frontend`, `currency` |
| Tác động business | Browse page latency có thể tăng, đặc biệt với traffic dùng currency khác USD |
| Tác động SLO | Rủi ro tăng browse p95/p99 latency |
| Runtime validation cần có | Đếm số trace fan-out từ frontend sang currency service |

Việc cần làm trong Week 1:

- Ghi nhận đây là suspected bottleneck từ source code.
- Định nghĩa metric cần đo: số lượng gRPC call, latency của currency service, browse p95/p99.
- Capture Jaeger trace nếu có.

Hướng xử lý W2+:

- Cache exchange rate.
- Thêm batch conversion API.
- Validate cải thiện p95/p99 sau tối ưu.

---

### 5.2 PERF-02 — Product search query không giới hạn và khó tận dụng index

| Hạng mục | Chi tiết |
|---|---|
| Trụ | Performance Efficiency |
| Mức độ | Medium |
| Chủ sở hữu | CDO-04 |
| Nguồn evidence | `product-catalog/main.go` |
| Component bị ảnh hưởng | `product-catalog`, `postgresql` |
| Tác động business | Search/browse có thể chậm khi catalog lớn |
| Tác động SLO | Rủi ro tăng browse/search p95 latency và DB saturation |
| Runtime validation cần có | `EXPLAIN ANALYZE`, DB query time, Postgres CPU/IO |

Việc cần làm trong Week 1:

- Ghi nhận query risk và cách đo.
- Đưa vào performance bottleneck backlog.

Hướng xử lý W2+:

- Thêm `LIMIT 20` hoặc pagination.
- Cân nhắc PostgreSQL trigram index / full-text search.
- Validate bằng `EXPLAIN ANALYZE` và search p95 latency.

---

### 5.3 COST-01 — Load Generator tự chạy trong default values

| Hạng mục | Chi tiết |
|---|---|
| Trụ | Cost Optimization |
| Mức độ | Medium |
| Chủ sở hữu | CDO-04 |
| Nguồn evidence | `techx-corp-chart/values.yaml`, `.env`, docker-compose / Helm values |
| Component bị ảnh hưởng | `load-generator`, `frontend-proxy`, downstream services |
| Tác động business | Cost/performance baseline có thể bị méo do synthetic traffic |
| Tác động SLO | Làm nhiễu latency/error metric của baseline |
| Runtime validation cần có | Rendered env values, trạng thái load-generator, telemetry labels |

Việc cần làm trong Week 1:

- Set/confirm `LOCUST_AUTOSTART=false` cho production-like baseline.
- Chỉ bật load-generator khi chạy performance test có kiểm soát.
- Ghi nhận là quick win trong COST-06 / COST-05.

Hướng xử lý W2+:

- Tag synthetic traffic rõ ràng.
- Giữ load-generator sẵn sàng nhưng kiểm soát thời điểm chạy.

---

### 5.4 COST-02 — Observability stack nặng/overkill, có OOMKilled và chưa có durability rõ ràng

| Hạng mục | Chi tiết |
|---|---|
| Trụ | Cost Optimization |
| Mức độ | Medium |
| Chủ sở hữu | CDO-04 |
| Nguồn evidence | `techx-corp-chart/values.yaml`, `techx-corp-platform/src/jaeger/config.yml`, runtime OOMKilled evidence từ Grafana/Jaeger |
| Component bị ảnh hưởng | Grafana, Prometheus, Jaeger, OpenSearch, OTel Collector |
| Tác động business | Always-on resource cost nhưng vẫn không ổn định; khi OOM/restart có thể mất dashboard/trace evidence trong lúc cần điều tra sự cố |
| Tác động SLO | Gián tiếp: observability pressure và restart loop có thể ảnh hưởng capacity của app, đồng thời làm giảm khả năng debug p95/p99/incident |
| Runtime validation cần có | CPU/memory/storage usage, restart count/OOMKilled history, quyết định retention, hành vi persistence khi restart |

Evidence:

- Ảnh bằng chứng Grafana overkill: 
![Grafana overkill](../epic-04-cost-optimization/runtime/screenshots/Grafana%20overkill.jpg)
- Ảnh bằng chứng Jaeger overkill:
![Jaeger overkill](../epic-04-cost-optimization/runtime/screenshots/Jaeger%20overkill.jpg)

- Source evidence của limit RAM nằm trong `techx-corp-chart/values.yaml`: Jaeger bật memory storage và `MEMORY_MAX_TRACES=25000` ở dòng `1037-1045`, đặt `resources.limits.memory: 600Mi` ở dòng `1056-1058`, user config dùng `memory.max_traces: ${env:MEMORY_MAX_TRACES}` ở dòng `1095-1097`; Grafana đặt `resources.limits.memory: 300Mi` ở dòng `1211-1213`.
- Source config Jaeger tương ứng cũng có trong `techx-corp-platform/src/jaeger/config.yml:34-41`, nơi Jaeger query trỏ trace storage về `memory_backend` và dùng `max_traces: ${env:MEMORY_MAX_TRACES}`.
- Kết luận gap: Observability stack đang vừa nặng cho baseline/demo, vừa chưa được right-size theo dữ liệu runtime. Grafana/Jaeger không chỉ tiêu thụ capacity thường trực mà đã có bằng chứng bị OOMKilled, làm tăng rủi ro mất trace/dashboards đúng thời điểm cần evidence để phân tích performance hoặc incident.

Việc cần làm trong Week 1:

- Ghi nhận resource footprint của observability stack.
- Ghi nhận OOMKilled evidence của Grafana/Jaeger như runtime finding cho `COST-02`.
- Xác định quick wins an toàn.
- Không tắt observability một cách mù quáng.
- Không giảm OpenSearch/Grafana/Jaeger nếu usage đã gần hoặc vượt limit.
- Right-size Grafana/Jaeger từ từ và cần reviewer approval.

Hướng xử lý W2+:

- Định nghĩa retention policy cho logs/traces/metrics.
- Quyết định store nào cần persistence.
- Tối ưu requests/limits dựa trên runtime data; riêng Grafana/Jaeger cần kiểm tra lại memory peak trước khi giảm footprint.

---

### 5.5 K8S-03 — Resource model chưa hoàn chỉnh / quota compatibility gap

| Hạng mục | Chi tiết |
|---|---|
| Trụ | Cost Optimization |
| Mức độ | Medium |
| Chủ sở hữu | CDO-04 |
| Trụ hỗ trợ | Performance Efficiency |
| Nguồn evidence | `deploy/quota.yaml`, Helm resource values |
| Component bị ảnh hưởng | Tất cả workload |
| Tác động business | Quota/admission hoặc resource contention có thể ảnh hưởng deploy/performance |
| Tác động SLO | Rủi ro latency/error nếu CPU/memory requests/limits sai |
| Runtime validation cần có | `kubectl top`, server dry-run/apply result, rendered resource values |

Việc cần làm trong Week 1:

- Ghi nhận hạn chế hiện tại.
- Đánh dấu CPU/memory right-sizing là pending cho tới khi Metrics API/Grafana/Prometheus data đáng tin cậy.
- Không downsize node hoặc critical services quá sớm.

Hướng xử lý W2+:

- Enable/fix Metrics API hoặc dùng Prometheus/Grafana resource metrics.
- Thêm requests/limits dựa trên số đo thật.
- Validate quota compatibility bằng server dry-run.
- Feed kết quả vào COST-05 và PERF-05.

---

## 6. Trách nhiệm hỗ trợ / cross-pillar

| Gap liên quan | Vai trò của CDO-04 | Vì sao cần CDO-04 | Output hiện tại |
|---|---|---|---|
| `REL-04` checkout dependency timeout budget | Cung cấp input performance | Reliability cần baseline p95/p99 latency để đặt timeout an toàn | Evidence PERF-01/PERF-02/PERF-04 |
| `K8S-02` stateless replicas/PDB | Review tác động cost | Tăng replica có thể tăng resource/cost footprint | Input COST-01/COST-05 |
| `K8S-04` data persistence | Cung cấp input cost | Managed service vs PVC ảnh hưởng trực tiếp tới budget | Cost trade-off / follow-up |

---

## 7. Deliverables Week 1 của CDO-04

| Deliverable | Gap liên quan | Trạng thái |
|---|---|---|
| Critical Flows & Metrics Matrix | PERF-01/PERF-02 | Done |
| Performance Baseline Plan | PERF-01/PERF-02/REL-04 input | Done |
| Suspected Bottleneck Analysis | PERF-01/PERF-02 | Done |
| Runtime Performance Evidence | PERF-01/PERF-02/K8S-03 | In Progress / đã có một phần evidence |
| Baseline Cost Estimate | COST-01/COST-02/K8S-03 | Done |
| Cost Quick Wins | COST-01/COST-02 | Ready for Review |
| Right-sizing & Cost Saving Recommendation | COST-02/K8S-03 | Pending / sau quick wins và runtime evidence |
| Prioritized Remediation Backlog | Tất cả 5 gap | File này |

---

## 8. Backlog remediation ưu tiên của CDO-04

### P0 — Cần rõ trước Week 1 Pitch

| Hạng mục | Gap | Hành động | Trạng thái |
|---|---|---|---|
| Làm rõ hành vi load-generator | COST-01 | Set/confirm `LOCUST_AUTOSTART=false` trong production-like baseline | Ready for Review |
| Capture runtime observability/performance evidence | PERF-01/PERF-02/K8S-03/COST-02 | Evidence Grafana/Prometheus/Jaeger + OOMKilled known gaps | In Progress |
| Xác nhận cost baseline so với $300/tuần | COST-01/COST-02 | Current fixed baseline estimate và budget check | Done |

### P1 — Evidence Week 1 / thực thi W2

| Hạng mục | Gap | Hành động | Trạng thái |
|---|---|---|---|
| Validate currency fan-out bằng trace | PERF-01 | Capture Jaeger trace cho Browse non-USD flow | Pending |
| Validate search query plan | PERF-02 | Chạy `EXPLAIN ANALYZE` trên search query | Pending |
| Right-size observability an toàn | COST-02 | Right-size Grafana/Jaeger từng bước sau OOMKilled evidence; đưa OpenSearch vào watchlist | Ready for Review |
| Fix Metrics API / thu thập CPU-memory evidence | K8S-03 | Dùng `kubectl top pods/nodes` hoặc Prometheus equivalent | Pending |

### P2 — Tối ưu W2+

| Hạng mục | Gap | Hành động | Trạng thái |
|---|---|---|---|
| Thêm batch/cached currency conversion | PERF-01 | Giảm số currency calls trên mỗi browse page | Future |
| Thêm search LIMIT/index/pagination | PERF-02 | Giảm rủi ro DB full-scan | Future |
| Định nghĩa retention/persistence policy cho observability | COST-02 | Quyết định retention vs cost | Future |
| Thêm requests/limits đo được và validate quota compatibility | K8S-03 | Right-size toàn bộ workload an toàn | Future |

---

## 9. Rủi ro / giả định

| Rủi ro / giả định | Tác động | Cách giảm thiểu |
|---|---|---|
| Runtime load test chưa chạy đầy đủ | Chưa thể claim official performance baseline | Ghi rõ chỉ là runtime evidence; controlled load test sẽ làm sau |
| Metrics API chưa khả dụng | Chặn `kubectl top` CPU/memory evidence | Dùng Grafana/Prometheus nếu có; fix metrics-server |
| Memory headroom không đồng nghĩa giảm AWS bill ngay lập tức | Cost saving có thể là gián tiếp | Giải thích là right-sizing/headroom, không claim giảm bill trực tiếp |
| OpenSearch/Grafana usage gần limit | Có nguy cơ OOM nếu giảm quá mạnh | Đưa vào watchlist, không giảm trong Week 1 |
| Performance fix có thể ảnh hưởng correctness | Tối ưu currency/search có thể đổi hành vi | Thêm test và validate trước khi implement |

---

## 10. Tuyên bố tổng kết cho Week 1 Pitch

CDO-04 đã xác định và tổ chức lại toàn bộ các gap Performance + Cost được giao cho nhóm. Năm owned gaps đều ở mức Medium và phần lớn cần runtime baseline trước khi thực hiện fix lớn.

Trong Week 1, nhóm tập trung vào:

1. Kế hoạch baseline performance metrics.
2. Phân tích bottleneck dựa trên source code.
3. Runtime observability/performance evidence.
4. Baseline cost estimate.
5. Cost quick wins và right-sizing recommendations.
6. Backlog remediation rõ ràng cho W2+.

Điều này nghĩa là CDO-04 không claim rằng toàn bộ performance/cost gaps đã được fix trong Week 1. Thay vào đó, nhóm đã tạo baseline evidence và kế hoạch ưu tiên cần thiết để xử lý các gap an toàn sau khi có runtime validation.

---

