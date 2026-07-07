# CDO08 Week 1 - Rubric Ưu Tiên Backlog

Owner: Hải  
Reviewer: Nguyên  
Status: Draft - Needs Review

## Mục Đích

Rubric này giúp CDO08 có một cách chung để đánh giá mức độ ưu tiên của các finding Security và Reliability trong Tuần 1.

Tuần 1 chưa phải là tuần sửa ngay tất cả vấn đề. Mục tiêu là kiểm tra hiện trạng hệ thống, tìm rủi ro có bằng chứng rõ ràng, rồi biến các rủi ro đó thành backlog có thể bảo vệ được cho Tuần 2-3.

Rubric này dùng để:

- chấm điểm findings từ tất cả owner trong CDO08
- quyết định finding nào đủ mạnh để thành P0/P1 và đưa vào pitch
- giải thích vì sao việc này làm trước, việc kia làm sau
- flag những finding còn thiếu bằng chứng trước khi đưa vào pitch

## Căn Cứ Bối Cảnh

Việc chấm điểm phải bám vào onboarding docs của Phase 3:

- SLO checkout: tỉ lệ checkout thành công >= 99.0%.
- SLO browse/cart: tỉ lệ không lỗi hoặc thao tác thành công >= 99.5%.
- p95 latency storefront: < 1s.
- AI review summary là best-effort, nhưng không được hiển thị tóm tắt sai lệch cho khách hàng.
- Ngân sách TF: khoảng $300/tuần cho hạ tầng AWS.
- Incident history chỉ ra 3 nhóm rủi ro reliability dễ lặp lại:
  - checkout chậm/lỗi khi tải cao
  - mất dữ liệu giỏ hàng sau khi node reschedule
  - lỗi payment khi deploy vì traffic vào pod trước khi pod sẵn sàng

## Thang Điểm

Mỗi tiêu chí được chấm từ 1 đến 5.

| Điểm | Ý nghĩa |
|---:|---|
| 1 | Ảnh hưởng thấp hoặc ít khả năng xảy ra; chủ yếu mang tính thông tin |
| 2 | Ảnh hưởng giới hạn; ảnh hưởng flow không critical hoặc có workaround dễ |
| 3 | Ảnh hưởng vừa; ảnh hưởng service quan trọng hoặc gây khó khăn vận hành |
| 4 | Ảnh hưởng cao; ảnh hưởng customer-facing flow, reliability, security hoặc incident response |
| 5 | Ảnh hưởng critical; có thể làm hỏng checkout, mất dữ liệu, lộ thông tin nhạy cảm, vi phạm luật Phase 3 hoặc đốt error budget |

## Tiêu Chí Chấm Điểm

| Tiêu chí | Câu hỏi cần trả lời | Hướng dẫn chấm điểm |
|---|---|---|
| Likelihood | Rủi ro này có dễ xảy ra trong vận hành thường ngày, deploy, tải cao hoặc incident injection không? | 1 = hiếm/lý thuyết, 3 = có thể xảy ra, 5 = dễ xảy ra hoặc đã từng thấy |
| Severity | Nếu xảy ra thì lỗi kỹ thuật nghiêm trọng đến mức nào? | 1 = degrade nhẹ, 3 = lỗi một phần hoặc dependency degrade, 5 = outage/mất dữ liệu/security exposure |
| Business Impact | Có ảnh hưởng tới khách hàng, checkout, doanh thu, uy tín hoặc cam kết stakeholder không? | 1 = chỉ ảnh hưởng nội bộ, 3 = ảnh hưởng trải nghiệm người dùng, 5 = ảnh hưởng checkout/doanh thu/niềm tin khách hàng |
| SLO Impact | Có thể đốt error budget hoặc làm SLO khó đo/khó bảo vệ không? | 1 = không ảnh hưởng SLO, 3 = rủi ro gián tiếp, 5 = ảnh hưởng trực tiếp checkout/cart/browse SLO |
| Security Impact | Có thể lộ secret, mở rộng quyền, tăng attack surface hoặc vi phạm protected path không? | 1 = không ảnh hưởng security, 3 = hardening gap, 5 = secret exposure/privilege risk/flagd rule risk |
| Cost / Performance Impact | Mitigation có cần đánh đổi cost/perf không, hoặc rủi ro hiện tại có gây lãng phí/latency không? | 1 = không có tradeoff đáng kể, 3 = có cân nhắc resource/perf vừa phải, 5 = quyết định cost/perf lớn cần CDO04 review |
| Evidence Confidence | Bằng chứng hiện tại mạnh đến đâu? | 1 = chỉ là giả định, 3 = có bằng chứng từ source/config, 5 = có source/config cộng với metric/log/trace/screenshot runtime |

## Công Thức Ưu Tiên

Dùng công thức này làm điểm xuất phát:

```text
Risk Score = Likelihood + Severity + Business Impact + SLO Impact + Security Impact
Evidence Adjusted Score = Risk Score + Evidence Confidence
```

`Cost / Performance Impact` không cộng trực tiếp vào priority. Tiêu chí này dùng như cờ quyết định:

- Nếu mitigation làm tăng cost hoặc thay đổi performance đáng kể, đánh dấu `Needs CDO04 Review`.
- Nếu evidence còn yếu nhưng nghi ngờ impact cao, đánh dấu `Needs Info` thay vì đẩy priority quá mạnh.

## Quy Đổi Priority

| Priority | Quy tắc |
|---|---|
| P0 | Evidence Adjusted Score >= 24, hoặc bất kỳ item nào có thể trực tiếp làm hỏng checkout, gây mất dữ liệu, lộ secret thật, vi phạm flagd rule, hoặc làm team không sẵn sàng cho pitch Tuần 1 |
| P1 | Evidence Adjusted Score 19-23, hoặc rủi ro có evidence khá chắc trên service critical và nên đưa vào kế hoạch Tuần 2-3 |
| P2 | Evidence Adjusted Score 14-18, là cải tiến hữu ích hoặc candidate backlog, nhưng không bắt buộc cho pitch Tuần 1 |
| P3 | Evidence Adjusted Score <= 13, mức độ thấp, cleanup tài liệu, hoặc item để xem lại sau |

## Field Bắt Buộc Cho Finding P0/P1

Mỗi finding P0/P1 phải có:

- owner
- area / ownership
- affected service hoặc file
- current risk
- business impact
- evidence
- proposed follow-up
- test plan
- rollback plan
- dependency với CDO04/CDO07/AIO nếu có
- reviewer status: `Approved`, `Needs Info`, hoặc `Defer`

## Trạng Thái Review

Dùng các trạng thái sau khi review finding:

| Status | Ý nghĩa |
|---|---|
| Approved | Finding đủ bằng chứng và có thể dùng trong backlog/pitch |
| Needs Info | Finding có thể đúng nhưng cần thêm evidence, scope rõ hơn hoặc test/rollback plan tốt hơn |
| Defer | Finding đúng nhưng chưa urgent cho pitch Tuần 1 hoặc kế hoạch Tuần 2-3 |

## Ví Dụ 1 - Checkout Thiếu Timeout / Retry / Fallback Rõ Ràng

Finding: checkout gọi một dependency critical nhưng chưa thấy timeout/retry/fallback rõ ràng.

| Tiêu chí | Điểm | Lý do |
|---|---:|---|
| Likelihood | 4 | Dependency chậm là tình huống có thể xảy ra khi tải cao hoặc incident injection |
| Severity | 5 | Checkout có thể treo, fail hoặc degrade khi dependency lỗi |
| Business Impact | 5 | Checkout là luồng revenue-critical |
| SLO Impact | 5 | Ảnh hưởng trực tiếp checkout success rate >= 99.0% và latency |
| Security Impact | 1 | Không có ảnh hưởng security trực tiếp |
| Cost / Performance Impact | 2 | Mitigation có thể ít tốn chi phí, nhưng retry phải tránh làm tăng tải dây chuyền |
| Evidence Confidence | 3 | Có thể có evidence từ source/config; vẫn cần runtime trace |

Evidence Adjusted Score:

```text
4 + 5 + 5 + 5 + 1 + 3 = 23
```

Priority: P1, hoặc P0 nếu runtime evidence cho thấy checkout fail/latency tăng khi dependency degrade.

Follow-up cần có:

- Inspect behavior của checkout client với từng dependency.
- Bổ sung trace/log evidence khi EKS sẵn sàng.
- Đề xuất timeout/retry/fallback hardening kèm test và rollback plan.

## Ví Dụ 2 - Valkey Cart Có Rủi Ro Persistence / Single Point Of Failure

Finding: cart state phụ thuộc vào Valkey, và cấu hình persistence/replica hiện tại có thể làm mất cart khi restart hoặc node reschedule.

| Tiêu chí | Điểm | Lý do |
|---|---:|---|
| Likelihood | 3 | Node reschedule/restart là tình huống có thể xảy ra khi bảo trì hoặc incident |
| Severity | 4 | Mất cart ảnh hưởng user journey và checkout conversion |
| Business Impact | 4 | Khách có thể mất giỏ hàng và bỏ mua |
| SLO Impact | 4 | Cart operation success target >= 99.5%; mất cart có thể ảnh hưởng checkout |
| Security Impact | 1 | Không có ảnh hưởng security trực tiếp |
| Cost / Performance Impact | 4 | HA/persistence improvement có thể cần thêm resource hoặc managed service review |
| Evidence Confidence | 3 | Có thể có evidence từ chart/config; vẫn cần restart test |

Evidence Adjusted Score:

```text
3 + 4 + 4 + 4 + 1 + 3 = 19
```

Priority: P1.

Follow-up cần có:

- Xác nhận cấu hình persistence và replica hiện tại của Valkey.
- Mô tả rõ tình huống có thể mất cart.
- Phối hợp CDO04 nếu mitigation làm tăng cost.

## Ví Dụ 3 - Hardcoded Secret / Sensitive Config

Finding: password, token, API key hoặc connection string nhạy cảm được lưu trực tiếp trong chart, deploy values hoặc source config.

| Tiêu chí | Điểm | Lý do |
|---|---:|---|
| Likelihood | 4 | Hardcoded config tồn tại ở bất kỳ nơi nào repo/config có thể được đọc |
| Severity | 4 | Lộ secret có thể compromise service hoặc làm rotate khó |
| Business Impact | 3 | Impact tới khách phụ thuộc phạm vi của secret |
| SLO Impact | 2 | Thường gián tiếp, trừ khi rotation/leak gây incident |
| Security Impact | 5 | Đây là rủi ro security hygiene trực tiếp |
| Cost / Performance Impact | 1 | Migration sang Kubernetes Secret thường ít tốn chi phí |
| Evidence Confidence | 4 | Có thể chỉ rõ file path và key |

Evidence Adjusted Score:

```text
4 + 4 + 3 + 2 + 5 + 4 = 22
```

Priority: P1, hoặc P0 nếu secret là thật, đang active, có quyền cao, dùng được từ bên ngoài, hoặc liên quan protected incident infrastructure.

Follow-up cần có:

- Phân loại item là real secret hay placeholder.
- Đề xuất target Kubernetes Secret hoặc config path an toàn hơn.
- Thêm rollout, verification và rollback plan trước khi migrate.

## Ví Dụ 4 - Service Critical Thiếu Readiness Probe

Finding: một service trên checkout path thiếu readiness gating, nên Kubernetes có thể route traffic vào pod trước khi pod sẵn sàng.

| Tiêu chí | Điểm | Lý do |
|---|---:|---|
| Likelihood | 4 | Deploy và restart sẽ xảy ra trong Tuần 2-3 |
| Severity | 4 | Request có thể fail trong lúc rollout |
| Business Impact | 5 | Lỗi trên checkout path có thể ảnh hưởng doanh thu |
| SLO Impact | 5 | Ảnh hưởng trực tiếp checkout/cart/browse SLO tùy service |
| Security Impact | 1 | Không có ảnh hưởng security trực tiếp |
| Cost / Performance Impact | 2 | Thêm probe ít tốn chi phí, nhưng threshold sai có thể gây false restart |
| Evidence Confidence | 4 | Helm values/templates có thể chứng minh thiếu coverage |

Evidence Adjusted Score:

```text
4 + 4 + 5 + 5 + 1 + 4 = 23
```

Priority: P1, hoặc P0 nếu service bị ảnh hưởng là checkout/payment/cart và team dự kiến rollout trước khi bổ sung readiness.

Follow-up cần có:

- Xác định affected service/template.
- Đề xuất readiness check và threshold.
- Verify bằng Helm template và rollout/smoke test.

## Quy Tắc Ra Quyết Định Khi Điểm Gần Nhau

Khi hai finding có điểm gần nhau, ưu tiên theo các rule sau:

1. Ưu tiên risk trên checkout/revenue-critical flow hơn non-critical flow.
2. Ưu tiên risk có evidence rõ hơn risk chỉ là giả định.
3. Ưu tiên mitigation low-cost/high-impact trước thay đổi kiến trúc đắt tiền.
4. Ưu tiên thay đổi giảm incident blast radius mà không vi phạm flagd rules.
5. Escalate CDO04 nếu mitigation thay đổi replica, resource, managed service, retention hoặc performance.
6. Escalate CDO07 nếu chưa rõ yêu cầu evidence, ADR, audit trail hoặc decision log.

## Ghi Chú Review

| Reviewer | Status | Notes |
|---|---|---|
| Nguyên | Needs Review | Validate scoring criteria, priority bands và ví dụ trước khi dùng để rank backlog cuối cùng |

