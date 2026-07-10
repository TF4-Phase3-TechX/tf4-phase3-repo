# 06. Performance Risk & Follow-up Backlog

Tài liệu này tổng hợp các rủi ro hiệu năng còn lại của hệ thống TechX và danh sách các tác vụ follow-up (backlog) cần thực hiện trong Week 2 để tối ưu hóa hệ thống.

---

## 1. Danh Sách Rủi Ro Hiệu Năng Còn Lại (Performance Risks)

| STT | Rủi Ro (Risk) | Khả năng xảy ra / Ảnh hưởng | Mô Tả Chi Tiết | Giải Pháp Giảm Thiểu (Mitigation) |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **`accounting` OOMKilled / CrashLoopBackOff** | Cao / Cao | Runtime evidence xác nhận `accounting` từng `OOMKilled`, exit code `137`, restart hơn 118 lần trong khoảng 15 giờ với memory limit `120Mi`. Đây là blocker P0 trước compute right-sizing vì async accounting pipeline vẫn không ổn định. | Điều tra .NET runtime, Kafka consumer workload và telemetry; thử memory request/limit theo measured trial, ví dụ `200Mi` đến `256Mi`, rồi xác nhận restart count không tăng trong ít nhất 24 giờ. |
| **2** | **Thiếu CPU request và resource baseline** | Trung bình / Cao | Hầu hết service chưa có CPU request/limit. Thiếu CPU request làm scheduling, CPU share khi contention và HPA CPU utilization thiếu cơ sở; effective memory request cần kiểm tra trên rendered/live manifest. | Thu Prometheus/Grafana CPU-memory trend trong 48 đến 72 giờ, rồi đặt requests/limits theo từng service. HPA chỉ là P2 có điều kiện sau khi có CPU requests, probes ổn định và controlled load test. |
| **3** | **Rủi ro memory của `checkout` khi tải cao** | Trung bình / Trung bình | `checkout` có limit `20Mi` và `GOMEMLIMIT=16MiB`, headroom khoảng `4Mi`. Đây là config-based risk estimate, chưa phải `OOMKilled` đã xác nhận; restart hiện có liên quan Kafka startup race. | Sau khi có metrics, thử limit `64Mi` và `GOMEMLIMIT` khoảng 80% limit, sau đó xác nhận lại bằng Grafana/Prometheus, p95/p99, error rate và restart count. |
| **4** | **PostgreSQL bị nghẽn (Database Saturation)** | Thấp / Trung bình | Search catalog dùng `LOWER()` với `LIKE %query%`, chưa có `LIMIT` hoặc pagination. Khi dữ liệu lớn, query có thể full scan, trả response lớn và làm tăng CPU database. | Thêm `LIMIT`/pagination trước; chạy `EXPLAIN ANALYZE` với dữ liệu thực tế. Chỉ cân nhắc trigram hoặc full-text index nếu evidence cho thấy cần thiết. |


---

## 2. Kế Hoạch Hành Động & Follow-up Backlog (Week 2)

Dưới đây là các task cần đưa vào backlog để giải quyết triệt để trong Week 2:

### Task 1: Xử lý `accounting` OOMKilled trước right-sizing
* **Mô tả**: Điều tra root cause của `accounting` OOM/restart, triển khai measured memory trial có rollback và xác nhận async accounting pipeline ổn định trước mọi compute right-sizing.
* **Người thực hiện**: CDO-04 / Dev Team
* **Độ ưu tiên**: P0, vì `accounting` đã có `OOMKilled` và restart cao; tiếp tục right-sizing khi async accounting pipeline chưa ổn định có thể che khuất reliability failure.
* **Tiêu chí hoàn thành**: Không có `OOMKilled` mới, restart count không tăng trong ít nhất 24 giờ và Kafka consumer vẫn xử lý bình thường.

### Task 2: Hoàn thiện Prometheus/Grafana metrics baseline
* **Mô tả**: Dùng Prometheus/Grafana làm source of truth trong 48 đến 72 giờ, tách idle baseline với controlled load test và lưu CPU/memory trend theo pod/node.
* **Người thực hiện**: CDO-04
* **Độ ưu tiên**: P1, vì đây là prerequisite cho measured right-sizing và HPA, nhưng không tự khắc phục một runtime failure đã xác nhận như Task 1.
* **Tiêu chí hoàn thành**: Có CPU/memory trend và restart/OOM history từ Prometheus/Grafana cho app và observability.

### Task 3: Thiết lập measured resources, quota và search guardrail
* **Mô tả**: Đề xuất CPU/memory requests/limits theo từng service từ metrics, render manifest và chạy ResourceQuota server-side dry-run. Đồng thời thêm `LIMIT`/pagination cho search, rồi xác nhận bằng `EXPLAIN ANALYZE` và search p95/p99.
* **Người thực hiện**: CDO-04 / Dev Team
* **Độ ưu tiên**: P1, vì quota incompatibility có thể chặn rollout và search có thể làm bão hòa database, nhưng cả hai cần metrics và query evidence để chọn cấu hình an toàn.
* **Tiêu chí hoàn thành**: Rendered manifest và quota dry-run thành công; search query có bounded result; evidence ghi rõ query plan và latency trước/sau.

### Task 4: Hoàn thiện cost guardrail trước conditional scaling
* **Mô tả**: Xác nhận ownership trước khi đặt CloudWatch retention cho non-critical log groups; verify ECR lifecycle policy đã khai báo trong Terraform, review lifecycle preview và bảo vệ release/rollback tags. HPA chỉ được đánh giá sau CPU requests, Prometheus/Grafana evidence, probes ổn định và controlled load test.
* **Người thực hiện**: CDO-04
* **Độ ưu tiên**: P1, vì retention và ECR policy là cost guardrail ít rủi ro nhưng cần owner/AWS verification. HPA là P2 có điều kiện vì thiếu CPU requests, Prometheus/Grafana evidence, probes ổn định và controlled load-test evidence.
* **Tiêu chí hoàn thành**: Retention và ECR policy có evidence runtime/AWS; HPA chỉ có proposal hoặc rollout evidence sau khi hoàn tất toàn bộ prerequisite.
