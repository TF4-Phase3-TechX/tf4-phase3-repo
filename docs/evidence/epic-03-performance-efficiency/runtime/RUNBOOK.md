# Kịch bản vận hành Task-4 (Task-4 Runbook)

## Mục tiêu

Chạy thử nghiệm tải (load test) giả lập chiến dịch flash-sale ở mức **200 người dùng đồng thời (concurrent users)**, duy trì trạng thái ổn định trong **15 phút** và thu thập đầy đủ bằng chứng kiểm thử (evidence).

## Mốc thời gian (Timeline)

* **Ramp-up (Tăng tải):** 1 phút
* **Steady-state (Duy trì đỉnh tải):** 15 phút
* **Ramp-down (Giảm tải):** 20 giây
* ⏱️ **Tổng thời gian chạy (Total runtime):** 16 phút 20 giây

## Phân bổ Traffic (Traffic mix)

Kịch bản Locust được thiết kế để mô phỏng chính xác hành vi thực tế của người dùng trong ngày flash-sale, nghiêm cấm việc chỉ spam vào một endpoint nhẹ duy nhất.

| Nhóm flow | Locust tasks | Tổng weight | Tỷ lệ xấp xỉ |
|---|---|---:|---:|
| Browse/Search | `index`, `browse_product_list`, `browse_product`, `get_recommendations`, `get_product_reviews` | 44 | ~44% |
| Cart | `view_cart`, `add_to_cart` | 25 | 25% |
| Checkout | `checkout`, `checkout_multi` | 15 | 15% |
| Navigation/AI | `ask_product_ai_assistant`, `get_ads` | 16 | ~16% |

> Các tỷ lệ trên được tính từ các trọng số (`@task(weight)`) của `WebsiteUser` trong `techx-corp-platform/src/load-generator/locustfile.py`. Hiện implementation xấp xỉ cơ chế mix 40/25/15/20; nếu cần chính xác hơn thì các trọng số này có thể điều chỉnh để tăng thêm tỷ lệ Navigation/AI.

* **Luồng xem/tìm kiếm (Browse/discovery flow):** Xem danh sách sản phẩm, chi tiết sản phẩm, gợi ý (recommendations), đánh giá (reviews), quảng cáo (ads), trợ lý AI (AI assistant), và trang chủ.
* **Luồng giỏ hàng (Cart flow):** Hành vi xem giỏ hàng và thêm sản phẩm vào giỏ (add-to-cart).
* **Luồng thanh toán (Checkout flow):** Thanh toán đơn hàng đơn lẻ (single-item) và thanh toán nhiều sản phẩm (multi-item).

## Test data và isolation

* Tất cả checkout/cart test dùng `UUID` synthetic user IDs (`uuid.uuid1()` / `uuid.uuid4()`), tránh dùng dữ liệu khách hàng thật.
* `people.json` là fixture dữ liệu test dùng cho payload checkout; không phải dữ liệu thực tế.
* Locust attach baggage `synthetic_request=true` lên các request để dễ phân biệt trace request synthetic với lưu lượng thật.
* Runbook này không tự động cleanup dữ liệu sau test; nếu cần xóa đơn/hàng thử nghiệm thì phải thực hiện riêng bằng công cụ cleanup hoặc script thứ cấp.

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

> Ghi chú: các ngưỡng CPU/memory trong monitor hiện là mức tuyệt đối mà runbook dùng làm guardrail nhanh cho workload hiện tại. Chúng được lựa chọn làm ngưỡng bảo vệ chung cho các pod nặng vì các service có resource request/limit khác nhau. Nếu muốn đo chính xác “90% CPU/RAM”, cần bổ sung kiểm tra dựa trên request/limit theo từng pod.

> Quan trọng: selector load-generator cần khớp với label Helm deployment thực tế. Phần monitor hiện dùng selector `app.kubernetes.io/name=load-generator` để đảm bảo dữ liệu load-generator được giám sát đúng.

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
