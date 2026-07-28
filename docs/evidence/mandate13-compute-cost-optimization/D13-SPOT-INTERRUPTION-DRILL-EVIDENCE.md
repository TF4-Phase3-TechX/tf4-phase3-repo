# D13-SPOT-INTERRUPTION-DRILL-EVIDENCE — Bằng chứng Kiểm thử Thu hồi Spot Node (Spot Interruption Drill)

## 1. Tổng quan và Thông số Kiểm thử

| Thông số | Giá trị | Tuân thủ Hợp đồng Audit |
|---|---|:---:|
| Target Spot Node | `ip-10-0-10-115.ec2.internal` | Đã xác minh |
| Target NodeClaim | `techx-arm64-spot-jr4cd` | Đã xác minh |
| EC2 Instance ID | `i-0f6b28fa988d70036` | Đã xác minh |
| Instance Type | `r7g.large` | Đã xác minh |
| Kiến trúc (Architecture) | `arm64` / Graviton | Đã xác minh |
| Mốc thời gian ngắt (UTC) | `2026-07-28T16:10:48Z` | Đã xác minh |
| Mốc thời gian Node thay thế Ready (UTC) | `2026-07-28T16:14:02Z` | Đã xác minh |
| Mốc thời gian Reschedule hoàn tất (UTC) | `2026-07-28T16:14:02Z` | Đã xác minh |
| Mốc thời gian kết thúc kiểm thử (UTC) | `2026-07-28T16:14:13Z` | Đã xác minh |

---

## 2. Kiểm tra Tải liên tục Locust & Xác minh Zero-Error (0 Lỗi Khách hàng)

| Chỉ số | Trước Drill (`16:10:48Z`) | Sau Drill (`16:14:13Z`) | Chênh lệch trong Khung Drill | Quy tắc Pass | Kết quả |
|---|---:|---:|---:|---|:---:|
| **Tổng Request Locust** | 0 | 60,349 | **+60,349** | Delta > 0 | PASS |
| **Tổng Lỗi Khách hàng (Total Errors)** | 0 | 0 | **0** | Delta == 0 | PASS |
| **Lỗi Browse (Browse Failures)** | 0 | 0 | **0** | Delta == 0 | PASS |
| **Lỗi Cart (Cart Failures)** | 0 | 0 | **0** | Delta == 0 | PASS |
| **Lỗi Checkout (Checkout Failures)** | 0 | 0 | **0** | Delta == 0 | PASS |

---

## 3. Phân tích Kiến trúc Chi tiết: Tại sao Hệ thống Sống sót qua Spot Interruption với 0 Lỗi

Hệ thống đã chịu đựng và vượt qua sự cố thu hồi bất ngờ Spot node `ip-10-0-10-115.ec2.internal` (`i-0f6b28fa988d70036`) dưới tải thực tế liên tục mà **không xảy ra bất kỳ lỗi request nào phía khách hàng (0 error)** nhờ 5 cơ chế kiến trúc bổ trợ lẫn nhau:

### 1. Bảo vệ bằng PodDisruptionBudget (PDB) (`minAvailable: 1`)
- Mọi dịch vụ stateless trong namespace `techx-tf4` (`checkout`, `cart`, `frontend`, `frontend-proxy`, `product-catalog`, `product-reviews`, `payment`, `shipping`, `currency`, `email`, `ad`, `quote`, `recommendation`, `image-provider`, `llm`) đều có PDB hoạt động với `minAvailable: 1`.
- Khi tín hiệu eviction được gửi tới Spot node, Kubernetes Eviction API bắt buộc tuân thủ quy tắc PDB. Hệ thống nghiêm cấm evict bất kỳ pod nào nếu việc đó làm số pod replica đang phục vụ hạ xuống dưới 1. Điều này bảo đảm luôn có ít nhất 1 pod replica healthy duy trì serving traffic liên tục trong suốt quá trình drain node.

### 2. Phân bổ Multi-AZ Topology Spread & Dự phòng Replica (`topologySpreadConstraints`)
- Toàn bộ các dịch vụ stateless quan trọng đều duy trì `replicas >= 2` (ví dụ: `frontend: 2-6`, `cart: 2-4`, `checkout: 2-3`, `product-catalog: 2-4`).
- Các Deployment cấu hình `topologySpreadConstraints` trải rộng theo `topologyKey: topology.kubernetes.io/zone` và `topologyKey: kubernetes.io/hostname`.
- Điều này ép các pod replicas phải phân bổ trên các Availability Zone khác nhau (`us-east-1a` và `us-east-1b`) và trên các worker nodes khác nhau.
- Khi Spot node `ip-10-0-10-115.ec2.internal` (AZ `us-east-1a`) bị hạ, các pod replicas dự phòng đang chạy trên node `ip-10-0-11-17.ec2.internal` (AZ `us-east-1b`) ngay lập tức gánh 100% lượng request đến mà không gây ra bất kỳ điểm sụp đổ duy nhất nào (SPOF).

### 3. Chu trình Drain Êm đẹp (Graceful Drain) & Gỡ IP khỏi Endpoints
- Pods được cấu hình thời gian rút êm `terminationGracePeriodSeconds: 30` và Readiness Probes.
- Ngay khi có sự kiện eviction, Kubernetes ngay lập tức gỡ IP của pod bị huỷ ra khỏi danh sách Service Endpoints trước khi gửi lệnh `SIGTERM`.
- Các Ingress proxy (`frontend-proxy`) và `kube-proxy` ngừng điều hướng HTTP request mới tới pod đang hủy trong vòng vài miligiây.
- Các HTTP/gRPC request đang xử lý dở được dành đủ thời gian hoàn tất xử lý trước khi container đóng hoàn toàn, ngăn chặn triệt để lỗi HTTP 5xx hoặc ngắt socket đột ngột.

### 4. Provisioning Nhanh chóng qua Karpenter & Reschedule Pod
- Karpenter Controller phát hiện sự kiện ngắt Spot NodeClaim ngay lập tức.
- Karpenter tính toán dung lượng pod bị thiếu và tự động provision NodeClaim thay thế mà không gây kẹt kịch bản `Pending` kéo dài.
- Các pod bị evict được reschedule và vượt qua Readiness Probe trong vòng **3 phút 14 giây**, khôi phục lại mức dự phòng redundancy ban đầu.

### 5. Cơ chế Retries Phía Ứng dụng & Resiliency của Proxy
- Các luồng gọi microservice (như `frontend-proxy` -> `frontend` -> `checkout`) có cấu hình gRPC/HTTP retry logic với chính sách backoff.
- Các nhiễu kết nối mạng tạm thời trong quá trình dịch chuyển IP của pod được proxy tự động thử lại mượt mà, giữ cho chỉ số lỗi khách hàng bằng đúng **0**.

---

## 4. Kết luận Nghiệm thu Drill

- **Spot Node bị ngắt**: Node `techx-arm64-spot-jr4cd` (`ip-10-0-10-115.ec2.internal`) bị hạ under live traffic.
- **Tái phân bổ Pod**: Mọi microservices (`checkout`, `cart`, `frontend-proxy`, `product-catalog`, `product-reviews`) dịch chuyển mượt mà.
- **Lỗi phía Khách hàng**: Đúng **0 lỗi** trên tất cả các luồng Browse, Cart, và Checkout.
- **Kết luận Drill**: **PASS**
