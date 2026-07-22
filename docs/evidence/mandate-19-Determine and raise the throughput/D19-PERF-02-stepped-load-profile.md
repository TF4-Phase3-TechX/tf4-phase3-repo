# D19-PERF-02 — Kế hoạch stepped load profile để tìm breakpoint thực tế

## 1. Trạng thái và phạm vi

- **Owner:** CDO04
- **Profile ID:** `d19-breakpoint-v1`
- **Dependency:** D19-PERF-01
- **Loại deliverable:** Plan only
- **Cách thực thi:** Cấu hình và điều khiển qua UI trong approved test window
- **Runtime execution:** NOT RUN
- **Helm/deploy verification:** N/A

Tài liệu này chỉ khóa kế hoạch kiểm thử. Task không thay đổi application source, load-generator source, Helm, Terraform, HPA, node hoặc flagd.

Baseline và post-tuning phải dùng cùng schedule, endpoint weights, test data, UI configuration và SLO contract. Nếu thay đổi bất kỳ thành phần nào, hai run không còn so sánh trực tiếp và phải chạy lại.

## 2. Immutable stepped schedule

Load được điều khiển theo concurrent users. Offered, achieved và successful RPS phải được đo tại từng step; không suy diễn RPS từ user count.

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

Tổng planned runtime là 75 phút. Không thay đổi step size hoặc duration giữa baseline và post-tuning.

Nếu 275 users vẫn đạt toàn bộ SLO và không có saturation hoặc throughput plateau, verdict bắt buộc là `NO_BREAKPOINT_FOUND_WITHIN_PROFILE`. Chỉ được kết luận breakpoint lớn hơn mức đã đo; phải tạo profile v2 và chạy lại cả baseline lẫn post-tuning.

## 3. Endpoint weights cố định

Giữ nguyên workload và task weights đang được triển khai tại thời điểm approved window.

| Flow | Tasks | Weight | Task-selection share |
|---|---|---:|---:|
| Browse/product | index 10; product list 8; product detail 12; recommendations 8; reviews 6 | 44 | 43.56% |
| Cart | view cart 12; add to cart 13 | 25 | 24.75% |
| Checkout | checkout 8; multi-item checkout 7 | 15 | 14.85% |
| Background/production-like | AI assistant 10; ads 6 | 16 | 15.84% |
| Flag-gated | flood home 1 | 1 | 0.99% |

Task-selection share không phải HTTP request share vì Cart và Checkout có nested requests. Request mix thực tế phải lấy từ raw UI export/Locust statistics. `loadGeneratorFloodHomepage` phải giữ nguyên và disabled trong cả hai run.

## 4. Test data và correlation plan

- Baseline và post-tuning dùng cùng load-generator image digest và runtime configuration.
- Dùng cùng `people.json`, product fixture, wait-time policy và randomization behavior.
- Mỗi virtual-user journey dùng correlation ID riêng theo implementation đang triển khai; không thay đổi source trong task này.
- Không chia sẻ cart identity giữa virtual users.
- Không ghi PII hoặc credential vào evidence.
- Cart state, transaction result và duplicate order được kiểm tra theo D19-PERF-01.
- HTTP 2xx có payload hoặc transaction state sai vẫn được tính là correctness failure.

## 5. UI execution plan

Trước approved window, operator phải review và chụp lại toàn bộ UI configuration:

1. target environment và storefront URL;
2. concurrent users và spawn rate của từng phase;
3. endpoint/task mix;
4. load-generator image/runtime configuration;
5. feature-flag state;
6. baseline node count, node identity, instance type và allocatable capacity;
7. HPA, quota và workload replica state;
8. dashboard queries dùng cho SLO và saturation.

Trong lúc chạy:

1. operator chuyển từng phase theo schedule đã khóa;
2. ghi actual UTC timestamp khi UI bắt đầu phase;
3. ghi actual UTC timestamp khi active users đạt target;
4. chỉ đánh giá phase sau khi actual users đạt target;
5. export raw statistics/logs sau mỗi phase;
6. chụp CPU, memory, throttling và restart của load generator;
7. ghi node name, UID/provider ID và instance type mỗi phút;
8. áp dụng hard-stop theo D19-PERF-01 khi correctness hoặc safety gate gãy.

Không dùng planned timestamp thay cho actual UI timestamp.

## 6. Evaluation contract

Primary evaluation window là 3 phút cuối của phase và phải nằm hoàn toàn sau thời điểm actual users đạt target. Nếu không đủ trọn 3 phút sau khi đạt target, phase là `INSUFFICIENT_DATA`.

| Flow | Minimum successful samples cho p95 | Minimum successful samples cho p99 |
|---|---:|---:|
| Browse | 100 | 100 |
| Cart | 100 | 100 |
| Checkout | 100 | 100 |

Flow thiếu sample không được PASS/FAIL latency. Error, timeout và correctness hard gates vẫn có hiệu lực ngay theo D19-PERF-01.

## 7. Evidence plan

Mỗi baseline/post-tuning run phải lưu:

- screenshot UI configuration trước run;
- actual phase start và target-achieved timestamps theo UTC;
- raw Locust/UI CSV, HTML report, failures, exceptions và console logs;
- offered, achieved và successful RPS theo phase;
- Browse, Cart và Checkout p95/p99, success, error và timeout ratios;
- correctness và duplicate-order results;
- load-generator CPU, memory, throttling và restart timeline;
- node count, name, UID/provider ID, instance type và replacement timeline;
- HPA, pod replicas, quota và scheduling state;
- CPU, memory, connection, worker/thread pool, queue và downstream saturation;
- image digest, runtime configuration, fixture fingerprints và Git SHA;
- Last Passing Step, First Failing Step và conservative breakpoint result.

Không chỉnh tay raw artifact. Missing mandatory evidence không được coi là PASS.

## 8. Quy tắc hợp lệ và verdict

Run chỉ hợp lệ khi:

1. baseline/post-tuning dùng cùng profile và UI configuration;
2. endpoint weights, fixtures, wait time và flagd không đổi;
3. node count/type/identity và allocatable capacity không đổi;
4. load generator tạo được target users và không saturation;
5. evaluation chỉ bắt đầu sau target-achieved timestamp;
6. đủ minimum samples và mandatory telemetry;
7. có raw evidence cho Last Passing, First Failing và saturation cùng timeline.

`RESULT` chỉ được chứa một trong các verdict:

| Verdict | Điều kiện |
|---|---|
| `PASS` | Run hợp lệ, tìm được Last Passing và First Failing Step, đủ SLO/correctness/saturation evidence |
| `FAIL` | Run hoàn tất nhưng vi phạm acceptance không thuộc hard-stop |
| `INVALID` | Infrastructure, profile, fixture hoặc runtime invariant thay đổi |
| `HARD_STOP` | Run dừng theo safety/correctness hard-stop của D19-PERF-01 |
| `INSUFFICIENT_DATA` | Thiếu target-achieved timestamp, minimum samples hoặc mandatory telemetry |
| `NO_BREAKPOINT_FOUND_WITHIN_PROFILE` | 275 users vẫn đạt SLO và không có saturation/plateau |

Conservative breakpoint là successful RPS tại Last Passing Step. Overload phase dùng để đánh giá graceful degradation và Checkout protection, không tự động được xem là breakpoint.

## 9. Acceptance checklist

- [x] Có immutable load profile và profile ID.
- [x] Có endpoint weights và production-like background traffic.
- [x] Có test data/correlation plan.
- [x] Có stepped ramp và fine-grained steps.
- [x] Có overload phase và no-breakpoint verdict.
- [x] Có UI execution plan.
- [x] Có actual UTC timestamp plan.
- [x] Evaluation chỉ hợp lệ sau khi actual users đạt target.
- [x] Có minimum sample count cho Browse, Cart và Checkout.
- [x] Có load-generator saturation evidence plan.
- [x] Có node identity/replacement evidence plan.
- [x] Có closed RESULT enum.
- [x] Baseline/post-tuning dùng cùng profile.
- [x] Không thay đổi application/load-generator source.
- [x] Không thay đổi Helm, Terraform, HPA, node hoặc flagd.
- [ ] Runtime execution — NOT RUN.
- [ ] Runtime evidence — pending approved test window.

## 10. Verification status

| Verification | Status |
|---|---|
| Documentation review | PASS |
| Source-code change | NONE |
| Runner/automation script | NONE |
| Runtime execution | NOT RUN |
| Helm/deploy verification | N/A |

```text
D19-PERF-02 DELIVERABLE: PLAN ONLY
PROFILE VERSION: d19-breakpoint-v1
RUNTIME EXECUTION: NOT RUN
UI EXECUTION: PENDING APPROVED TEST WINDOW
```
