# scaling-right-sizing-recommendation

Tài liệu này đưa ra các đề xuất điều chỉnh tài nguyên cấu hình (Right-sizing) và tự động mở rộng (Autoscaling) cho các dịch vụ cốt lõi của hệ thống TechX trong namespace `techx-tf4`, dựa trên dữ liệu phân tích cấu hình từ file `values.yaml` và dữ liệu đo đạc baseline.

---

## 1. Phân Tích Hiện Trạng Cấu Hình (values.yaml)

Qua rà soát file [values.yaml](file:///D:/tf4-phase3-repo/techx-corp-chart/values.yaml), nhóm phát hiện một số điểm bất hợp lý trong việc cấu hình tài nguyên (resources):

1. **Thiếu CPU Requests và CPU Limits**: 
   * Hầu như toàn bộ các microservices (ví dụ: `checkout`, `frontend`, `product-reviews`) đều **không khai báo** `resources.requests.cpu` và `resources.limits.cpu`.
   * **Rủi ro**: Pods có thể tranh chấp tài nguyên CPU không kiểm soát trên Node, dẫn đến hiện tượng throttle CPU của các dịch vụ quan trọng hoặc làm sập Node khi có tải lớn.
2. **Thiếu Memory Requests**:
   * Các dịch vụ chỉ khai báo `limits.memory` mà không khai báo `requests.memory`.
   * **Rủi ro**: Kubernetes scheduler không thể tính toán tải thực tế của Node để xếp lịch (scheduling) một cách tối ưu, tăng nguy cơ Node bị quá tải RAM dẫn đến OOM (Out Of Memory) kill.
3. **Dịch vụ `llm` không có cấu hình tài nguyên**:
   * Dịch vụ `llm` hoàn toàn trống rỗng phần `resources` block.
4. **Cấu hình `checkout` quá sát giới hạn**:
   * Giới hạn RAM của `checkout` được cấu hình là `20Mi` (trong khi biến môi trường `GOMEMLIMIT` là `16MiB`). Khoảng đệm 4MB là quá nhỏ cho runtime Go khi xử lý tải cao, rất dễ gây ra OOM kill.

---

## 2. Bảng Đề Xuất Điều Chỉnh Cấu Hình (Right-sizing) cho Week 2

Dựa trên phân tích baseline và tải trọng hệ thống, nhóm đề xuất điều chỉnh cấu hình `resources` trong file `values.yaml` như sau:

| Dịch vụ (Service) | Cấu hình cũ (Limits) | Đề xuất Requests (CPU / Memory) | Đề xuất Limits (CPU / Memory) | Rationale (Lý do đề xuất) |
| :--- | :--- | :--- | :--- | :--- |
| **`checkout`** | `memory: 20Mi` | `50m` / `30Mi` | `200m` / `60Mi` | Tăng giới hạn RAM lên `60Mi` để tránh lỗi OOM khi chạy GC của Go ở tải cao; set CPU để đảm bảo xử lý thanh toán ổn định. |
| **`frontend`** | `memory: 250Mi` | `100m` / `150Mi` | `300m` / `300Mi` | Frontend chạy Next.js/Node.js cần lượng RAM khởi động và xử lý SSR tương đối lớn. |
| **`product-reviews`** | `memory: 100Mi` | `50m` / `80Mi` | `200m` / `150Mi` | Dịch vụ Python gRPC cần thêm RAM khi gọi API LLM và phân tích dữ liệu text review. |
| **`llm`** (Mock) | Không có | `100m` / `128Mi` | `200m` / `256Mi` | Khai báo tài nguyên cho mock backend để đảm bảo không tranh chấp với các dịch vụ khác. |
| **`payment`** | `memory: 60Mi` | `50m` / `40Mi` | `100m` / `80Mi` | Dịch vụ thanh toán cốt lõi cần tài nguyên đảm bảo. |
| **12 services còn lại** | Chỉ có `memory.limits` | `50m` / `64Mi` | `100m` / `128Mi` | Thiết lập baseline tài nguyên cho các service còn lại (như `cart`, `shipping`, `product-catalog`, `kafka`,...) để ngăn chặn việc chiếm dụng CPU không kiểm soát trên Node và cho phép Kubernetes scheduler lập lịch tối ưu. |

---

## 3. Đề Xuất Cơ Chế Tự Động Mở Rộng (Autoscaling / HPA)

Để hệ thống TechX tự động thích ứng khi load-generator sinh tải lớn ở Week 2, chúng tôi đề xuất triển khai Horizontal Pod Autoscaler (HPA) cho 2 dịch vụ ở cửa ngõ (Critical Path):

### 3.1. HPA cho `frontend`
* **Mục tiêu**: Đảm bảo tốc độ phản hồi trang chủ và trang chi tiết sản phẩm cho người dùng.
* **Cấu hình đề xuất**:
  * `minReplicas`: 2 (đảm bảo tính sẵn sàng cao - High Availability)
  * `maxReplicas`: 5
  * `targetCPUUtilizationPercentage`: 70%

### 3.2. HPA cho `checkout`
* **Mục tiêu**: Bảo vệ luồng thanh toán (revenue-critical flow) không bị nghẽn hay từ chối yêu cầu.
* **Cấu hình đề xuất**:
  * `minReplicas`: 2
  * `maxReplicas`: 4
  * `targetCPUUtilizationPercentage`: 75%
