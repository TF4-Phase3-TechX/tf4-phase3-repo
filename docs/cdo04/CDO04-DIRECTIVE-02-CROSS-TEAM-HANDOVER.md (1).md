# Output cần bàn giao — Acceptance Run Directive #2

**Điều phối:** CDO04 · **Bàn giao:** CDO08, CDO07  
**Run chung:** 200 concurrent users × 15 phút, dùng **cùng UTC test window**.  
**Mục đích:** CDO04 cần các input sau để chạy [`CDO04-MANDATE-02-EXECUTION-CHECKLIST.md`](CDO04-MANDATE-02-EXECUTION-CHECKLIST.md).

> Không một trụ nào được đánh đổi: storefront public nhưng portal vận hành phải private; telemetry phải liên tục trong load test; CDO07 phải tái kiểm được raw evidence.

---

## CDO08 — Security, Reliability & Telemetry

Bàn giao **trước khi CDO04 chạy test**:

1. **Báo cáo hoàn tất chuyển đổi (Cutover completion)**
   - Xác nhận Ingress/Envoy được cập nhật thành công dạng zero-downtime (không gián đoạn storefront `/` và `/images/` - vẫn trả về HTTP 200).
   - Các route/aliases vận hành bắt buộc phải trả về lỗi `404` hoặc bị chặn từ mạng public: `/grafana`, `/jaeger`, `/jaeger/ui/`, `/loadgen`, `/feature`, `/flagservice`, `/otlp-http`, `/argocd`.
   - Đi kèm raw `curl` test từ internet công cộng để xác nhận.

2. **Kế hoạch dự phòng khôi phục (Rollback plan)**
   - Định nghĩa rõ quy trình rollback nhanh (lệnh kubectl hoặc helm) để khôi phục cấu hình Ingress/Envoy công khai ban đầu trong trường hợp việc chuyển đổi gây lỗi hoặc gián đoạn luồng storefront chính của khách hàng.

3. **Private access guide & Cost impact**
   - Tài liệu hướng dẫn truy cập riêng tư (VPN/tunnel/bastion) kèm thông tin tài khoản cho Mentor/CDO04.
   - **Đánh giá tác động chi phí truy cập riêng tư (Private-access cost impact):** Ước tính chi phí phát sinh nếu dùng VPN/Bastion Host ($/tháng) hoặc giải trình nếu dùng port-forward qua K8s API ($0).

4. **Telemetry continuity**
   - Đảm bảo các kết nối nội bộ OTLP `4317`/`4318` không bị ảnh hưởng bởi bộ lọc bảo mật.
   - Prometheus targets healthy, tiếp tục thu thập metric ổn định dưới tải.
   - Đảm bảo dữ liệu traces/metrics liên tục, không bị stale/gap trong suốt 15 phút test.

5. **Audit logs & flagd verification**
   - Cung cấp nguồn log (IP, identity, timestamp) để CDO07 đối soát việc truy cập các cổng vận hành.
   - Xác nhận không vô hiệu hóa cơ chế incident (`flagd`).

**Pass tối thiểu:** Cutover completion thành công không downtime; Rollback plan khả thi; Private-access cost impact tối ưu; Operational routes bị chặn hoàn toàn từ ngoài; Telemetry thông suốt.


---

## CDO07 — Auditability & Independent Verification

Bàn giao **trước và sau test**:

1. **Evidence index**
   - Nơi lưu trữ tập trung raw evidence: chốt metadata (UTC window, ALB DNS, Git SHA, Helm release tag, verifier).

2. **Xác minh giả định chi phí (Verify cost assumptions)**
   - Kiểm tra và xác thực tính chính xác của các báo cáo chi phí: đối chiếu giá trị thực tế so với các ước tính baseline của CDO04.
   - Đánh giá tính kinh tế của giải pháp truy cập riêng tư (Private-access cost impact) và chi phí thực tế phát sinh của Node Group khi scale-out dưới tải.

3. **Independent verification**
   - Tự kiểm tra độc lập các route bị chặn từ mạng ngoài và chạy thử tài liệu private access.
   - Đối chiếu timeline thực tế giữa Locust, Prometheus/Grafana, Jaeger để loại trừ trace/metric cũ.
   - Yêu cầu cung cấp raw outputs, queries, và source path, không phê duyệt nếu chỉ có ảnh chụp màn hình.

4. **Auditability checks**
   - Audit trail: Ghi nhận lịch sử truy cập (identity + timestamp) của các lần vào private portal.
   - Kiểm tra việc ẩn thông tin nhạy cảm (PII/payment/prompt -> `***`) trong logs/traces nhưng vẫn giữ correlation ID.
   - Kết luận trạng thái cổng nghiệm thu (`PASS` / `FAIL` / `BLOCKED`).

**Pass tối thiểu:** Evidence có thể tái kiểm chứng; Xác minh chi phí và log truy cập thành công; Kết quả CDO08/CDO04 được ký duyệt rõ ràng.


---

## Run timeline chung & Quy trình Co giãn (Scale-down)

| Thời điểm | CDO08 | CDO04 | CDO07 |
|---|---|---|---|
| **Trước T0** | Verify chặn public + bàn giao HD truy cập riêng tư + kiểm tra telemetry | Ghi nhận baseline tài nguyên ban đầu (T0), cấu hình kịch bản test 200 users | Khởi tạo bảng kiểm chứng, chốt metadata |
| **T0 → T+15m** | Giám sát trạng thái chặn truy cập vận hành và tính liên tục của telemetry | Thực thi load test, thu thập SLO, giám sát trạng thái scale-up của pods/nodes | Theo dõi tính đồng bộ của log/metric timestamps |
| **T+15m → T+30m (Cooldown)** | Verify dữ liệu trace hoàn chỉnh trên Jaeger | Kết thúc test, **kiểm chứng quy trình tự động Scale-down** để tối ưu chi phí | Thu thập log truy cập private portal để đối soát |
| **Nghiệm thu** | Sign-off phần an toàn cổng | Đối chiếu chi phí/đơn hàng thành công, lập báo cáo | Xác minh chi phí, audit trail, ký duyệt |

### Quy trình tự động thu hồi tài nguyên (Scale-down)
Để tối ưu hóa chi phí hạ tầng và đảm bảo không vượt trần ngân sách `$300/tuần`:
*   **Thực thi:** Ngay sau khi kết thúc đợt tải cao (T+15m), hệ thống phải tự động co giảm tài nguyên (Scale-down) thông qua Horizontal Pod Autoscaler (HPA) và Cluster Autoscaler/Karpenter.
*   **Thời gian hoàn tất:** Toàn bộ số lượng pod phụ trợ (frontend, checkout...) và số lượng worker nodes phải trở về mức baseline ban đầu (ví dụ: 1 replica/service, tối thiểu node group) trong vòng **tối đa 10 đến 15 phút** kể từ lúc tắt Locust.
*   **Bằng chứng:** Chụp metrics/logs chứng minh biểu đồ tài nguyên và số lượng máy ảo EC2 co giảm thực tế sau đỉnh tải.

---

## Final gate

```text
Storefront public AND operational portals private
AND Rollback plan verified AND Cutover completion signed
AND Telemetry continuous during the same 15-minute window
AND CDO04 SLO met AND successful Scale-down within 10-15m
AND CDO07 verifies cost assumptions & private-access cost impact
AND CDO07 independently verifies audit access trails
```

Bất kỳ tiêu chí nào `FAIL` hoặc `BLOCKED` => **chưa đủ điều kiện pass challenge**.

