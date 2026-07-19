# D5-PM-01 — Đầu vào ADR cho Hiệu năng và Chi phí

## Thông tin chung

| Trường | Giá trị |
|---|---|
| Chỉ thị | Directive #5 — Resource Governance & Safe Admission Enforcement |
| Nhóm | CDO-04 |
| Trụ chính | Performance Efficiency, Cost Optimization |
| Người phụ trách | An |
| Trạng thái | Sẵn sàng review |
| Ngày | 2026-07-19 |
| Công việc liên quan | D5-PERF-01, D5-PERF-02, D5-PERF-03, D5-PERF-05 |

---

## 1. Tên quyết định

**Áp dụng resource contract dựa trên số đo thực tế, triển khai remediation theo từng đợt qua GitOps và kiểm thử hồi quy hiệu năng cho workload ứng dụng và observability của TechX.**

---

## 2. Bối cảnh

Directive #5 yêu cầu các workload của TechX phải có CPU và memory requests/limits rõ ràng, có cơ sở kỹ thuật và phù hợp với tải thực tế. Cấu hình tài nguyên phải hỗ trợ:

- hiệu năng ổn định;
- lập lịch chính xác;
- HPA hoạt động đúng;
- rollout an toàn;
- sử dụng hạ tầng hiệu quả;
- kiểm soát chi phí compute.

Phạm vi rà soát gồm workload ứng dụng trong namespace `techx-tf4` và các workload observability hỗ trợ trong `techx-observability`.

Kết quả inventory và đo đạc Prometheus cho thấy:

- một số workload sử dụng memory cao hơn đáng kể so với request;
- một số memory limit thấp hơn hoặc quá sát mức peak đo được;
- một số workload có CPU throttling đáng kể;
- `accounting` và `jaeger` từng xảy ra `OOMKilled`;
- `opensearch` có mức scheduler reservation thấp so với memory usage thực tế;
- `frontend` và `payment` cần bổ sung memory headroom;
- kịch bản HPA-max cần khoảng `8450m` CPU limits trong khi quota hiện tại là `8000m`;
- triển khai toàn bộ resource changes trong một lần sẽ tạo blast radius lớn vì ứng dụng được quản lý qua một Argo CD Application tự động;
- việc so sánh trước và sau remediation cần dùng cùng load profile, cùng cách tính metric và cùng cửa sổ thời gian UTC.

Vì vậy, phương án được chọn là kết hợp:

1. sizing dựa trên số đo;
2. rollout theo từng wave;
3. đối chiếu quota và node capacity;
4. kiểm thử hồi quy hiệu năng;
5. quản lý capacity theo chi phí.

---

## 3. Quyết định

CDO-04 đề xuất áp dụng mô hình resource governance gồm các phần sau.

### 3.1. Resource contract dựa trên số đo

CPU và memory requests/limits phải được xác định dựa trên:

- cấu hình Kubernetes đang chạy thực tế;
- baseline và peak từ Prometheus;
- CPU throttling;
- restart và lịch sử OOM;
- hành vi HPA;
- mức độ quan trọng của workload;
- đặc điểm runtime;
- yêu cầu headroom;
- tác động tới scheduler và quota.

Không sử dụng một ảnh chụp `kubectl top` duy nhất để chốt sizing cuối.

Mỗi workload phải phân biệt rõ:

- giá trị đang chạy;
- số đo thực tế;
- giá trị đề xuất;
- giá trị đã áp dụng;
- giá trị đã được xác minh sau rollout.

### 3.2. Triển khai remediation theo từng wave qua GitOps

Các thay đổi tài nguyên được chia thành năm wave:

1. workload stateless rủi ro thấp;
2. workload stateless thuộc luồng doanh thu;
3. workload stateful và messaging;
4. workload observability;
5. các ngoại lệ còn lại đã được review.

Mỗi wave phải có:

- Git commit được review;
- change window được duyệt;
- Argo CD sync;
- kiểm tra sức khỏe runtime;
- evidence hiệu năng và tài nguyên;
- kết quả PASS/FAIL rõ ràng.

Chỉ chuyển sang wave tiếp theo sau khi wave trước hoàn thành các validation gate.

### 3.3. Đối chiếu quota và capacity

Trước khi promote mỗi wave, cần đối chiếu với:

- ResourceQuota hiện tại;
- HPA-min;
- HPA-max;
- HPA-max cộng rolling-update surge;
- node allocatable;
- giới hạn số pod;
- topology spread;
- phân mảnh tài nguyên theo từng node.

Mọi thay đổi quota phải được thực hiện qua GitOps source of truth.

### 3.4. Kiểm thử hồi quy hiệu năng

Sau khi thay đổi, hệ thống phải được so sánh với baseline trước remediation.

Hai lần chạy phải dùng:

- cùng load-generator profile;
- cùng duration;
- cùng endpoint mix;
- cùng bộ Prometheus query;
- cùng quy tắc tính SLO;
- cùng cách tính request denominator;
- exact UTC window;
- raw Kubernetes và Prometheus evidence.

Thiếu metric hoặc artifact thì run không được kết luận PASS.

### 3.5. Source of truth

Tất cả resource và quota changes phải được quản lý qua Git và Argo CD.

Lệnh runtime chỉ được dùng để kiểm tra hoặc xử lý khẩn cấp. Cấu hình cuối cùng phải được reconcile về GitOps source of truth.

---

## 4. Kết quả phân tích hiệu năng

| Khu vực | Phát hiện | Ảnh hưởng tới quyết định |
|---|---|---|
| Accounting | Từng OOMKilled với memory limit cũ `256Mi`; peak khoảng `416.4Mi`; CPU throttling đạt `92.69%` | Cần tăng memory headroom và CPU limit, sau đó kiểm chứng lại dưới tải |
| Jaeger | Từng OOMKilled và restart do áp lực bộ nhớ trace in-memory; peak khoảng `1131Mi` | Cần tăng memory headroom và xác minh lại hành vi lưu trữ trace |
| OpenSearch | Memory usage thực tế cao hơn nhiều so với request và sát limit cũ | Cần điều chỉnh request/limit để scheduler reservation phản ánh đúng usage |
| Frontend | Memory peak vượt hoặc quá sát limit cũ `320Mi` | Cần tăng memory limit và kiểm tra Browse latency/error |
| Payment | Memory usage vượt request và thiếu headroom | Cần điều chỉnh request/limit theo measured peak |
| HPA | HPA-max cần khoảng `8450m` CPU limits | Cần nâng quota và xác minh HPA-max cộng rollout surge |
| Scheduler | Tổng capacity có thể đủ nhưng chưa chứng minh đầy đủ per-node placement, surge và N-1 | Cần xác minh theo từng wave |
| Regression | Đã có fail-closed regression harness | Dùng để so sánh chính thức trước và sau thay đổi |

---

## 5. Các điều chỉnh tài nguyên đề xuất

| Workload | Vấn đề hiện tại | Điều chỉnh đề xuất | Điều kiện xác minh |
|---|---|---|---|
| `accounting` | OOMKilled và CPU throttling cao | Memory `512Mi`; CPU limit `400m` | Không có OOM mới; throttling giảm; consumer hoạt động ổn định |
| `jaeger` | OOMKilled do áp lực memory của trace buffer | Memory `1536Mi` | Trace ingestion ổn định; không có restart burst |
| `opensearch` | Request thấp hơn nhiều so với usage thực tế | Tăng scheduler reservation và memory headroom theo peak | Pod ổn định; request phản ánh đúng usage |
| `frontend` | Memory limit cũ thiếu headroom | Memory limit `512Mi` | Browse latency và error rate không regress |
| `payment` | Memory request/limit cũ thiếu headroom | Memory limit `384Mi`; request căn theo usage thực tế | Checkout đúng và latency ổn định |
| Namespace quota | HPA-max vượt CPU-limit quota hiện tại | Nâng `limits.cpu` từ `8` lên `10` | HPA-max và rollout surge được admit thành công |

Giá trị cuối cùng phải được xác nhận qua controlled rollout và runtime evidence.

---

## 6. Các gate xác minh hiệu năng

Mỗi wave phải đạt:

- không có `OOMKilled` mới;
- không có `CrashLoopBackOff` mới;
- không có `Pending` hoặc `FailedScheduling` kéo dài;
- CPU throttling không tăng đáng kể;
- HPA có current metrics hợp lệ;
- HPA vẫn `ScalingActive=True`;
- surge pod được schedule thành công;
- Browse, Cart và Checkout không tăng lỗi đáng kể;
- Storefront p95 duy trì dưới `1 giây`;
- memory working set nằm trong headroom được duyệt;
- restart count không tăng bất thường;
- Argo CD trở lại `Healthy` và `Synced`;
- runtime values khớp GitOps configuration đã review.

---

## 7. Kết quả phân tích chi phí

Resource governance phải cân bằng giữa độ an toàn và chi phí.

Requests quá thấp có thể:

- làm scheduler đánh giá sai capacity;
- tăng node contention;
- gây OOM hoặc eviction;
- tăng chi phí xử lý incident;
- làm HPA và autoscaling thiếu chính xác.

Requests quá cao có thể:

- giảm bin-packing;
- làm Karpenter tạo thêm node không cần thiết;
- tăng worker node-hours;
- tạo overcapacity kéo dài;
- làm giảm hiệu quả của Spot/Graviton optimization.

Do đó, team chọn workload-specific sizing dựa trên số đo, thay vì tăng đồng loạt theo một tỷ lệ chung.

---

## 8. Đánh đổi theo số lượng worker

| Kịch bản | Mục đích | Góc nhìn hiệu năng/độ tin cậy | Góc nhìn chi phí |
|---|---|---|---|
| 2 workers | Managed baseline tối thiểu | Headroom hạn chế khi tải cao hoặc maintenance | Chi phí định kỳ thấp nhất |
| 3 workers | Vận hành bình thường khi có tải | Có thể phục vụ workload hiện tại nhưng maintenance headroom còn hạn chế | Cân bằng hơn cho steady state |
| 4 workers | Controlled rollout, maintenance, high-load validation hoặc temporary safety margin | Tăng khả năng surge và reschedule | Tăng node-hours tạm thời |

Kịch bản bốn worker chỉ là phương án capacity tạm thời, không phải steady-state mặc định.

Sau khi remediation và validation hoàn tất, cluster phải quay về resting capacity được phê duyệt khi demand cho phép.

---

## 9. Cost guardrails

- Không tăng worker vĩnh viễn nếu không có measured evidence.
- Không tăng resources nếu không có workload-specific rationale.
- Worker thứ tư phải có điều kiện kết thúc rõ.
- Candidate values phải được đối chiếu lại với node capacity.
- Theo dõi node count và Karpenter sau rollout.
- Loại bỏ temporary capacity sau validation window.
- Ghi lại node count và node-hours sau remediation.
- Tách chi phí steady state khỏi chi phí change window.

---

## 10. Các phương án đã xem xét

| Phương án | Quyết định | Lý do |
|---|---|---|
| Giữ nguyên resource values | Không chọn | Đã có OOM, throttling và scheduler risk |
| Tăng toàn bộ workload theo cùng một tỷ lệ | Không chọn | Không phản ánh đặc điểm từng runtime và làm tăng reservation |
| Apply toàn bộ thay đổi trong một rollout | Không chọn | Blast radius quá lớn |
| Giữ bốn worker vĩnh viễn | Không chọn cho steady state | Tăng chi phí định kỳ |
| Measured sizing và staged rollout | Chọn | Cân bằng hiệu năng, độ an toàn và chi phí |
| Fail-closed regression evidence | Chọn | Không cho phép dữ liệu thiếu được xem là thành công |
| GitOps làm source of truth | Chọn | Có audit trail và khả năng lặp lại |

---

## 11. Kế hoạch rollout

### Wave 01 — Low-risk stateless

Xác minh:

- rollout hoàn tất;
- pod Ready;
- restart/OOM delta;
- CPU throttling;
- smoke test cơ bản.

### Wave 02 — Revenue-critical stateless

Xác minh:

- Browse success và latency;
- Cart success và latency;
- Checkout success và latency;
- HPA;
- quota và rolling surge;
- PDB và workload spread.

### Wave 03 — Stateful và messaging

Xác minh:

- Kafka readiness;
- message flow và consumer lag;
- PostgreSQL connections;
- Valkey availability;
- PVC attachment;
- restart/OOM;
- dependency health.

### Wave 04 — Observability

Xác minh:

- Prometheus;
- Grafana;
- Jaeger trace ingestion;
- OpenSearch health;
- evidence continuity;
- fallback evidence bằng Kubernetes và Prometheus.

### Wave 05 — Remaining reviewed exceptions

Xác minh:

- lý do ngoại lệ;
- owner;
- ngày review lại;
- hành động tiếp theo;
- workload-specific gates.

---

## 12. Hợp đồng kiểm thử hồi quy

Official regression run phải thu:

- exact UTC start/end;
- Git SHA;
- Argo CD revision;
- load-generator config;
- request total và errors của Browse/Cart/Checkout;
- Storefront p95;
- CPU throttling;
- memory utilization;
- restart/OOM delta;
- Pending pod;
- HPA metrics;
- requested CPU/memory so với allocatable;
- surge result;
- raw Prometheus range responses;
- load-generator logs;
- summary và verdict cuối.

Baseline và post-change run phải tương đương về:

- load profile;
- duration;
- endpoint mix;
- query set;
- application condition;
- evidence format.

---

## 13. Xử lý khi rollout không đạt

Khi một wave xuất hiện Pending pod, OOM, restart bất thường, rollout timeout, throttling tăng đáng kể hoặc customer-path regression:

1. dừng promote wave tiếp theo;
2. ghi kết quả wave là FAIL;
3. lưu toàn bộ raw evidence;
4. revert Git commit của wave khi cần bảo vệ runtime;
5. để Argo CD reconcile về previous-known-good revision;
6. chạy Browse/Cart/Checkout smoke test;
7. điều chỉnh candidate values;
8. chạy lại bằng RUN_ID mới.

Không cần rollback drill riêng cho wave PASS, nhưng phải xác định previous-known-good revision, rollback owner và revert command.

---

## 14. Danh mục evidence

| Hạng mục | Evidence | Trạng thái |
|---|---|---|
| D5-PERF-01 | Resource inventory và violation classification | Hoàn tất |
| D5-PERF-02 | Measured requests and limits matrix | Hoàn tất |
| D5-PERF-03 | Năm wave GitOps, promotion tool, validation và runbook | Sẵn sàng controlled execution |
| D5-PERF-05 | Fail-closed performance regression harness | Đã triển khai |
| ResourceQuota analysis | So sánh HPA-min, live, HPA-max và quota | Hoàn tất |
| Worker capacity analysis | Kịch bản 2, 3 và 4 workers | Hoàn tất |
| PR #34 | Staged resource remediation rollout preparation | Sẵn sàng review |
| PR #35 | Post-change regression harness | Sẵn sàng review |

### Vị trí evidence

```text
docs/evidence/directive-05/performance/
docs/evidence/directive-05/official-<RUN_ID>/resource-rollout/
docs/evidence/directive-05/official-<RUN_ID>/performance-regression/
environments/production/resource-rollout/
environments/production/performance-regression/
scripts/resource_rollout.py
scripts/performance_regression.py
scripts/validate.py
```

---

## 15. Trạng thái quyết định hiện tại

```text
ĐẦU VÀO ADR PERFORMANCE VÀ COST: HOÀN TẤT
CHUẨN BỊ STAGED ROLLOUT: HOÀN TẤT
REGRESSION HARNESS: HOÀN TẤT
RUNTIME EVIDENCE: BỔ SUNG TRONG CONTROLLED EXECUTION
```

Tài liệu này sẵn sàng để review kỹ thuật và đưa vào ADR cuối của Directive #5.

---

## 16. Bảng ký xác nhận

| Vai trò | Nội dung review | Sign-off |
|---|---|---|
| An / CDO-04 | Quyết định Performance và Cost | |
| Hoàng / Tech Lead | Candidate resource values và technical risk | |
| Vinh / Platform và Cost | Quota, node capacity và cost scenarios | |
| Huy / Metrics | Prometheus windows và measured values | |
| CDO-08 / Platform | GitOps rollout và quota update | |
| Reliability / SRE | Runtime validation gates | |
| Mentor | Final acceptance | |

---

## 17. Checklist hoàn thành

- [x] Tổng hợp resource inventory.
- [x] Tổng hợp measured resource matrix.
- [x] Ghi nhận OOM, throttling và scheduler risk.
- [x] Ghi candidate resource targets.
- [x] Ghi tác động HPA-max và quota.
- [x] Ghi staged five-wave rollout.
- [x] Ghi performance regression contract.
- [x] Ghi performance gates.
- [x] Ghi cost guardrails.
- [x] Ghi trade-off 2, 3 và 4 workers.
- [x] Ghi nguyên tắc temporary capacity.
- [x] Ghi phương án xử lý khi rollout không đạt.
- [x] Ghi evidence index.
- [x] Có bảng sign-off.
- [x] Tài liệu sẵn sàng ADR review.