# Kịch bản vận hành Task-4 (Task-4 Runbook)

## Mục tiêu

Chạy thử nghiệm tải (load test) giả lập chiến dịch flash-sale ở mức **200 người dùng đồng thời (concurrent users)**, duy trì trạng thái ổn định trong **15 phút** và thu thập đầy đủ bằng chứng kiểm thử (evidence).

## Mốc thời gian (Timeline)

* **Ramp-up (Tăng tải):** 1 phút
* **Steady-state (Duy trì đỉnh tải):** 15 phút
* **Ramp-down (Giảm tải):** 20 giây
* ⏱️ **Tổng thời gian chạy (Total runtime):** 16 phút 20 giây

## Phân bổ Traffic (Traffic mix)

Bảng dưới đây tính trực tiếp từ trọng số `@task(weight)` của `WebsiteUser` trong `techx-corp-platform/src/load-generator/locustfile.py`:
 
| Nhóm flow | Locust tasks (weight) | Tổng weight | Tỷ lệ (trên tổng 101) |
|---|---|---:|---:|
| Browse/Search | `index`(10), `browse_product_list`(8), `browse_product`(12), `get_recommendations`(8), `get_product_reviews`(6) | 44 | ~43.6% |
| Cart | `view_cart`(12), `add_to_cart`(13) | 25 | ~24.8% |
| Checkout | `checkout`(8), `checkout_multi`(7) | 15 | ~14.9% |
| Navigation/AI | `ask_product_ai_assistant`(10), `get_ads`(6) | 16 | ~15.8% |
| Khác (feature-flag gated) | `flood_home`(1) — chỉ chạy khi flag `loadGeneratorFloodHomepage` bật, mặc định không tạo traffic | 1 | ~1.0% |
| **Tổng** | | **101** | **100%** |
 
> **Ghi chú quan trọng:** tổng weight thực tế là 101 (không phải 100) do có task `flood_home` (weight 1) nằm ngoài 4 nhóm flow chính — task này chỉ sinh traffic khi flag `loadGeneratorFloodHomepage` được bật qua flagd, mặc định là no-op. Vì vậy tỷ lệ 4 nhóm chính cộng lại là ~99% chứ không phải 100%.
>
> Mô tả trong PR ("40% Browse/Search, 25% Cart, 15% Checkout, 20% Navigation/AI") là số làm tròn gần đúng cho dễ đọc; số chính xác cần đối chiếu theo bảng trên. Nếu cần khớp chính xác 40/25/15/20, cần điều chỉnh lại các giá trị weight trong `locustfile.py` (ví dụ tăng weight nhóm Navigation/AI, giảm nhóm Browse/Search).
 
* **Luồng xem/tìm kiếm (Browse/discovery flow):** Xem danh sách sản phẩm, chi tiết sản phẩm, gợi ý (recommendations), đánh giá (reviews), trang chủ.
* **Luồng giỏ hàng (Cart flow):** Hành vi xem giỏ hàng và thêm sản phẩm vào giỏ (add-to-cart).
* **Luồng thanh toán (Checkout flow):** Thanh toán đơn hàng đơn lẻ (single-item) và thanh toán nhiều sản phẩm (multi-item).
* **Luồng Navigation/AI:** Quảng cáo (ads) và trợ lý AI sản phẩm (AI assistant).
## Test data và isolation
 
* Tất cả checkout/cart test dùng `UUID` synthetic user IDs:
  * `uuid.uuid1()` — sinh cho mỗi phiên `add_to_cart`, `checkout`, `checkout_multi` (định danh user test cho từng request giỏ hàng/thanh toán).
  * `uuid.uuid4()` — sinh cho `session_id` của mỗi user session trong `on_start`.
* `people.json` là fixture dữ liệu test dùng làm payload checkout (`checkout_person = random.choice(people)`); không phải dữ liệu khách hàng thực tế.
* Locust attach baggage `synthetic_request=true` lên context OpenTelemetry của mọi session (qua `on_start`), và cũng gắn vào header HTTP cho browser traffic (Playwright, qua `add_baggage_header`) — giúp phân biệt trace request synthetic với lưu lượng thật trên Jaeger/OpenSearch.
* Runbook này **không tự động cleanup** dữ liệu sau test; nếu cần xóa đơn/hàng thử nghiệm thì phải thực hiện riêng bằng công cụ cleanup hoặc script thứ cấp (hiện chưa có sẵn trong repo — cần bổ sung nếu required bởi acceptance criteria).
## Điều kiện tiên quyết (Prerequisites)
 
* Có quyền truy cập vào cụm Kubernetes mục tiêu.
* Công cụ `kubectl` đã được cấu hình chính xác cho namespace `techx-tf4`.
* Deployment `load-generator` đã sẵn sàng hoạt động.
* **Lưu ý quan trọng:** Hệ thống `flagd` phải được giữ nguyên; nghiêm cấm vô hiệu hóa trong suốt quá trình test.
## Chạy thử nghiệm tải thấp (Dry-run)
 
```bash
bash scripts/run-load-test-task4.sh dry-run
```
 
Sau đó, mở giao diện Locust UI tại địa chỉ `http://localhost:8089` để kiểm tra cấu hình traffic mix và trạng thái sức khỏe cơ bản của hệ thống.
 
## Chạy chính thức (Full run)
 
```bash
bash scripts/run-load-test-task4.sh full
```
 
> The full run validates the Task-4 load shape by requiring the live deployment to have `LOCUST_LOAD_SHAPE=task4` and by overriding the shape directly in the Locust command.
 
## Điều kiện dừng khẩn cấp (Stop conditions)
 
Hệ thống sẽ lập tức dừng đợt test nếu vượt quá bất kỳ ngưỡng giới hạn nào sau đây:
 
* Lỗi liên quan đến luồng thanh toán (checkout) vượt quá ngưỡng cấu hình (5 lỗi trên mỗi 100 dòng log).
* Mức sử dụng CPU vượt quá 90% đối với các pod đang được giám sát.
* Mức sử dụng bộ nhớ (Memory) vượt quá 850Mi đối với các pod đang được giám sát.
* Pod `load-generator` có CPU vượt quá 80% hoặc bộ nhớ vượt quá 1200Mi.
* Số lượng Node của cụm tăng trưởng vượt mức baseline một cách bất thường.
> Ghi chú: các ngưỡng CPU/memory trong monitor hiện là mức tuyệt đối mà runbook dùng làm guardrail nhanh cho workload hiện tại. Chúng được lựa chọn làm ngưỡng bảo vệ chung cho các pod nặng vì các service có resource request/limit khác nhau. Nếu muốn đo chính xác "90% CPU/RAM", cần bổ sung kiểm tra dựa trên request/limit theo từng pod.
>
> **[CẦN XÁC NHẬN — chưa có monitor script trong scope review này]** Việc đổi logic so sánh sang theo `resources.requests/limits` từng container, và xác nhận selector `app.kubernetes.io/name=load-generator` khớp với Helm chart label thực tế, cần review trực tiếp trên monitor script — chưa thực hiện được trong bản cập nhật này do chưa có file đó.

## Chỉ mục Giám sát (Dashboard mapping)

| Tiêu chí nghiệm thu | Chỉ số | Panel Grafana | Artifact |
|---|---|---|---|
| Checkout ≥99% | Tỷ lệ thành công | Checkout Success | `grafana/checkout-success.png` |
| Storefront p95 < 1s | HTTP p95 | Storefront Latency | `grafana/storefront-latency.png` |
| Error rate thấp | 5xx rate | Error Rate | `grafana/error-rate.png` |
| Không OOM | Số lần container restart | Pod Health | `grafana/pod-health.png` |
| Không Memory Pressure | Memory working set | Container Memory | `grafana/container-memory.png` |
| Node còn headroom | CPU/memory utilization | Node Overview | `grafana/node-overview.png` |
| Observability hoạt động | Số trace / span | Jaeger/OpenSearch | `jaeger/trace-sample.png` |

## Danh mục bằng chứng cần thu thập (Evidence checklist)

Thu thập và rà soát đầy đủ các tệp sau trước khi đóng task:

* Kết quả log chạy kèm mốc thời gian cụ thể từ file `task4-full-T0.txt` và `task4-full-T1.txt`.
* File dữ liệu thô thống kê CSV và file báo cáo HTML report xuất ra từ Locust.
* Nhật ký giám sát từ file log `load-test-monitor-*.log`.
* Ảnh chụp màn hình Grafana hiển thị các biểu đồ độ trễ (latency), tỷ lệ lỗi (error rate), và tần suất request (request rate).
* Các vết trace trên Jaeger mô tả cho các request tiêu biểu của luồng thanh toán (checkout) và giỏ hàng (cart).

## Thư mục lưu trữ bằng chứng (Evidence artifacts)

Toàn bộ tài liệu bằng chứng trên sẽ được lưu tại đường dẫn:

* `docs/evidence/epic-03-performance-efficiency/runtime/`
