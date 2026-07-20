# D19-PERF-02 — Stepped load profile để tìm breakpoint thực tế

## 1. Trạng thái và phạm vi

- **Owner:** CDO04
- **Profile ID:** `d19-breakpoint-v1`
- **Implementation:** `D19BreakpointShape` trong `techx-corp-platform/src/load-generator/locustfile.py`
- **Runner:** `scripts/run-d19-breakpoint-test.sh`
**Dependency:** D19-PERF-01

Profile này dùng nguyên trạng cho baseline và post-tuning. Mọi thay đổi schedule, task weight, fixture, wait time hoặc feature flag tạo một profile version mới và buộc chạy lại cả hai phía.

## 2. Immutable stepped schedule

Load được điều khiển bằng concurrent users vì workload hiện tại dùng `HttpUser` với think time `between(1, 10)`. Offered, achieved và successful RPS vẫn được đo ở từng step; không suy diễn RPS từ user count.

| Phase | Target users | Spawn rate | Duration | Evaluation |
|---|---:|---:|---:|---|
| Warm-up | 25 | 5 users/s | 5 phút | Không dùng làm breakpoint |
| Step 01 | 50 | 5 users/s | 5 phút | 3 phút cuối |
| Step 02 | 75 | 5 users/s | 5 phút | 3 phút cuối |
| Step 03 | 100 | 5 users/s | 5 phút | 3 phút cuối |
| Step 04 | 125 | 5 users/s | 5 phút | 3 phút cuối |
| Step 05 | 150 | 5 users/s | 5 phút | 3 phút cuối |
| Step 06 | 175 | 5 users/s | 5 phút | 3 phút cuối |
| Step 07 | 200 | 5 users/s | 5 phút | 3 phút cuối |
| Fine 01 | 210 | 2 users/s | 5 phút | 3 phút cuối |
| Fine 02 | 220 | 2 users/s | 5 phút | 3 phút cuối |
| Fine 03 | 230 | 2 users/s | 5 phút | 3 phút cuối |
| Fine 04 | 240 | 2 users/s | 5 phút | 3 phút cuối |
| Fine 05 | 250 | 2 users/s | 5 phút | 3 phút cuối |
| Overload | 275 | 2 users/s | 10 phút | Graceful-degradation evidence |

Tổng planned runtime là 75 phút. Các bước 10-user ở vùng 200–250 là fine-grained search dựa trên mốc 200-user đã từng được dùng trong repository. Nếu First Failing Step nằm ngoài vùng này, không sửa profile giữa baseline và post-tuning: tạo profile v2 được review và chạy lại cả hai.

## 3. Endpoint weights cố định

Giữ nguyên `WebsiteUser`, `wait_time = between(1, 10)` và tổng task weight 101.

| Flow | Tasks | Weight | Task-selection share |
|---|---|---:|---:|
| Browse/product | index 10; product list 8; product detail 12; recommendations 8; reviews 6 | 44 | 43.56% |
| Cart | view cart 12; add to cart 13 | 25 | 24.75% |
| Checkout | checkout 8; multi-item checkout 7 | 15 | 14.85% |
| Background/production-like | AI assistant 10; ads 6 | 16 | 15.84% |
| Flag-gated | flood home 1 | 1 | 0.99% |

Checkout và Cart task có nested requests, vì vậy bảng trên là task-selection mix, không phải HTTP request share. Raw `stats_history.csv` và route stats là nguồn đo request mix thực tế. `loadGeneratorFloodHomepage` phải giữ nguyên và disabled ở cả hai run.

## 4. User data và correlation

- Mỗi session tạo UUID v4 và gắn baggage `session.id`; mọi synthetic request có `synthetic_request=true`.
- Mỗi cart/checkout journey tạo UUID v1 riêng làm `userId`; nested add-to-cart và checkout dùng cùng ID để correlation.
- Product được chọn từ danh sách cố định trong source; checkout identity lấy từ cùng revision của `people.json`.
- Baseline và post-tuning phải dùng cùng load-generator Git SHA/image digest, `people.json`, product list và randomization implementation.
- Không dùng chung cart identity giữa virtual users; không đưa PII hoặc credential vào log.
- Correctness phải đối chiếu cart state, transaction result và duplicate order theo D19-PERF-01; HTTP 2xx sai nội dung vẫn là failure.

## 5. UTC timeline và timestamps

Không hard-code lịch chạy chưa được duyệt. Runner ghi exact UTC thực tế vào `run-metadata.env`:

- `RUN_START_UTC` ngay trước khi Locust bắt đầu;
- `RUN_END_UTC` ngay sau khi Locust kết thúc;
- `phase-timeline.csv` khóa start/end offset của từng phase; ghép với `RUN_START_UTC` để có exact UTC;
- node timeline mỗi 60 giây với `TIMESTAMP_UTC`;
- Locust history theo thời gian và pod log có timestamp.

Mốc phase được tính từ `RUN_START_UTC` theo schedule ở mục 2. Operator phải lập bảng phase timestamp từ raw history; dữ liệu ngoài evaluation window không được trộn vào verdict.

## 6. Chạy profile

```bash
bash scripts/run-d19-breakpoint-test.sh baseline
bash scripts/run-d19-breakpoint-test.sh post-tuning
```

Runner không tự thay đổi replica, HPA, node hoặc flagd. Trước run, runner bắt buộc SHA-256 của `locustfile.py` trong load-generator pod khớp source đã review; mismatch làm preflight fail. Dừng theo hard-stop của D19-PERF-01 nếu correctness/safety gate gãy; giữ toàn bộ artifact đã tạo và ghi `RESULT=FAIL` trong evidence review.

## 7. Raw evidence contract

Mỗi run tạo thư mục `runtime/<run-type>-<RUN_ID>/` gồm:

```text
RESULT
run-metadata.env
load/locust-console.log
load/pod.log
load/phase-timeline.csv
load/stats.csv
load/stats_history.csv
load/failures.csv
load/exceptions.csv
load/report.html
kubernetes/nodes-before.txt
kubernetes/nodes-after.txt
kubernetes/node-timeline.log
kubernetes/hpa-before.yaml
kubernetes/capacity-guards-before.yaml
kubernetes/pods-before.txt
```

Không chỉnh tay raw artifact. `PROFILE_SHA256`, Git SHA, image digest, Kubernetes context và node count cho phép chứng minh baseline/after dùng cùng profile và hạ tầng cố định. SLO/saturation dashboard exports được bổ sung theo checkpoints của D19-PERF-01.

## 8. Quy tắc so sánh và verdict

Run chỉ hợp lệ khi:

1. profile ID và SHA-256 giống nhau;
2. endpoint weights, fixture, wait time và flagd giống nhau;
3. đủ 75 phút hoặc dừng bởi hard-stop có evidence;
4. load generator không saturation và tạo được target users;
5. node count/type, allocatable capacity và cluster topology không đổi;
6. có raw history để tính offered/achieved/successful RPS từng step;
7. có dữ liệu cho Last Passing, First Failing và saturation đồng timeline;
8. post-tuning không được dùng step/profile khác baseline.

Conservative breakpoint là successful RPS ở Last Passing Step. Overload phase không được dùng làm passing breakpoint; nó dùng để đánh giá load shedding, ưu tiên Checkout và khả năng phục hồi.

## 9. Acceptance checklist

- [x] Có immutable load profile và profile ID.
- [x] Có endpoint weights.
- [x] Có production-like background traffic.
- [x] Có user data/correlation strategy.
- [x] Có stepped ramp.
- [x] Có fine-grained steps gần vùng breakpoint dự kiến.
- [x] Runner ghi exact UTC timestamps.
- [x] Runner lưu raw load-generator logs/CSV/HTML.
- [x] Baseline và post-tuning dùng cùng implementation/profile SHA.
- [x] Không tự thay đổi node, HPA, flagd hoặc runtime capacity.

## 10. Trạng thái

```text
D19-PERF-02 PROFILE: COMPLETE
PROFILE VERSION: d19-breakpoint-v1
RUNTIME EXECUTION: PENDING APPROVED TEST WINDOW
```
