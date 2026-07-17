# BÁO CÁO HOÀN TẤT CHUYỂN ĐỔI (CUTOVER COMPLETION REPORT)
## MANDATE-01 — Khóa Cổng Vận Hành Công Cộng & Thiết Lập Private Access

**Dự án:** TechX Storefront & Observability Stack  
**Nhóm thực hiện:** CDO08  
**Đơn vị phê duyệt:** CDO07 (Audit/Compliance) & Mentor/BTC  
**Thời gian hoàn tất:** 2026-07-14T00:10:00+07:00  

---

## 1. Báo cáo hoàn tất chuyển đổi (Cutover completion)

Quá trình chuyển đổi (cutover) cấu hình hạ tầng mạng và định tuyến proxy đã được thực hiện thành công theo mô hình **Zero-Downtime**.

### A. Trạng thái hoạt động của Storefront:
*   Việc cập nhật cấu hình Envoy Proxy được thực hiện bằng cơ chế **Kubernetes Rolling Update**. Pod mới được khởi tạo và kiểm tra sức khỏe thành công trước khi Pod cũ bị tắt.
*   **Kết quả:** Storefront (`/`) và tài nguyên ảnh (`/images/`) hoạt động liên tục, không có bất kỳ yêu cầu nào của khách hàng bị gián đoạn (trả về **`HTTP 200`** xuyên suốt quá trình).

### B. Kết quả chặn các tuyến đường công cộng (Public Exposure status):
Tất cả các cổng vận hành nội bộ đã được chặn hoàn toàn ở lớp Envoy Proxy ngoài rìa (public edge). Truy cập từ internet công cộng trả về mã lỗi `404 Not Found` hoặc `405 Method Not Allowed` trực tiếp từ Proxy:

*   `/` $\rightarrow$ **`200 OK`** (Storefront hoạt động công khai)
*   `/images/` $\rightarrow$ **`200 OK`** (Tài nguyên ảnh hoạt động công khai)
*   `/grafana/` $\rightarrow$ **`404 Not Found`** (Đã chặn)
*   `/jaeger/ui/` $\rightarrow$ **`404 Not Found`** (Đã chặn)
*   `/loadgen/` $\rightarrow$ **`404 Not Found`** (Đã chặn)
*   `/feature/` $\rightarrow$ **`404 Not Found`** (Đã chặn)
*   `/flagservice/` $\rightarrow$ **`404 Not Found`** (Đã chặn)
*   `/otlp-http/` $\rightarrow$ **`404 Not Found`** (Đã chặn)
*   `/argocd/` $\rightarrow$ **`404 Not Found`** (Không được khai báo định tuyến ra ngoài)

### C. Nhật ký kiểm tra bằng lệnh curl thực tế (Raw curl test):
```bash
$ ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"

$ for path in / /grafana/ /jaeger/ui/ /loadgen/ /feature/ /flagservice/ /otlp-http/; do
    code=$(curl -sS -o /dev/null -w "%{http_code}" "$ALB$path")
    echo "$path -> HTTP $code"
  done

/ -> HTTP 200
/grafana/ -> HTTP 404
/jaeger/ui/ -> HTTP 404
/loadgen/ -> HTTP 404
/feature/ -> HTTP 404
/flagservice/ -> HTTP 404
/otlp-http/ -> HTTP 404
```

---

## 2. Kế hoạch dự phòng khôi phục (Rollback plan)

Trong trường hợp việc chuyển đổi hoặc cấu hình định tuyến mới phát sinh lỗi nghiêm trọng gây sập storefront hoặc lỗi luồng mua hàng (checkout), đội vận hành sẽ thực hiện rollback nhanh theo 2 cấp độ:

### Cấp độ 1: Rollback cấu hình Envoy/Helm App (Thời gian xử lý < 1 phút)
Sử dụng Helm để khôi phục cấu hình Envoy Proxy về phiên bản an toàn trước đó:
```bash
# Xem danh sách các phiên bản deploy gần nhất
helm -n techx-tf4 history techx-corp

# Rollback về Revision ổn định trước đó (Ví dụ: Revision 5)
helm -n techx-tf4 rollback techx-corp 5 --wait
```
*Sau khi chạy lệnh, Kubernetes sẽ tự động thay thế Pod proxy lỗi bằng Pod proxy của phiên bản cũ.*

### Cấp độ 2: Rollback cấu hình hạ tầng mạng (Terraform)
Nếu Bastion Host hoặc EKS Access Entry bị lỗi gây ảnh hưởng đến cụm EKS:
1.  Revert commit sửa đổi cấu hình trên nhánh `main`.
2.  GitHub Actions sẽ tự động kích hoạt workflow `terraform-apply` để hủy bỏ (destroy) tài nguyên Bastion Host và khôi phục trạng thái mạng ban đầu.

---

## 3. Hướng dẫn truy cập riêng tư & Đánh giá chi phí (Private access & Cost)

### A. Hướng dẫn truy cập dành cho Mentor / CDO04:
Người kiểm thử đăng nhập AWS SSO thông qua profile `iam-tf4` và mở tunnel bằng câu lệnh tương ứng trên máy tính cá nhân:

*   **Dành cho máy Windows (Command Prompt - CMD):**
    ```cmd
    # Mở cổng Grafana (localhost:3000)
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters "{\"portNumber\":[\"13000\"],\"localPortNumber\":[\"3000\"]}" --profile iam-tf4 --region us-east-1

    # Mở cổng Jaeger (localhost:16686/jaeger/ui/)
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters "{\"portNumber\":[\"16686\"],\"localPortNumber\":[\"16686\"]}" --profile iam-tf4 --region us-east-1

    # Mở cổng Load Generator (localhost:8089)
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters "{\"portNumber\":[\"18089\"],\"localPortNumber\":[\"8089\"]}" --profile iam-tf4 --region us-east-1
    ```

*   **Dành cho máy macOS / Linux (Terminal):**
    ```bash
    # Mở cổng Grafana (localhost:3000)
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["13000"],"localPortNumber":["3000"]}' --profile iam-tf4 --region us-east-1

    # Mở cổng Jaeger (localhost:16686/jaeger/ui/)
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["16686"],"localPortNumber":["16686"]}' --profile iam-tf4 --region us-east-1

    # Mở cổng Load Generator (localhost:8089)
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["18089"],"localPortNumber":["8089"]}' --profile iam-tf4 --region us-east-1
    ```

### B. Đánh giá tác động chi phí (Private-access cost impact):
Giải pháp sử dụng **AWS SSM Session Manager qua EC2 Bastion** được tối ưu hóa triệt để về mặt chi phí:

1.  **Chi phí EC2 Bastion:** Sử dụng cấu hình siêu nhỏ `t3.nano` ($0.0052/giờ).
    *   *Chi phí phát sinh:* ~**$3.78 / tháng**.
2.  **Chi phí lưu trữ (EBS Volume):** Sử dụng ổ cứng gp3 dung lượng tối thiểu 30GB.
    *   *Chi phí phát sinh:* ~**$2.40 / tháng**.
3.  **Tận dụng hạ tầng có sẵn (NAT Gateway):** Bastion nằm trong Subnet riêng tư và kết nối ra ngoài internet thông qua **NAT Gateway dùng chung đã có sẵn** của EKS cluster. **Không phát sinh chi phí NAT Gateway mới ($32/tháng/cái)**.
4.  **Không dùng VPC Endpoints:** Kết nối SSM được định tuyến trực tiếp qua NAT Gateway, **không tạo VPC Endpoints mới ($21/tháng/cái)**.
5.  **Tổng chi phí giải pháp:** **~$6.18 / tháng** (Cực kỳ tối ưu so với việc thuê các giải pháp VPN Client-to-Site truyền thống vốn tốn kém từ $50 - $100/tháng).

---

## 4. Đảm bảo tính liên tục của Telemetry (Telemetry continuity)

*   **OTLP Connectivity:** Lớp lọc bảo mật chặn cổng vận hành chỉ được áp dụng tại **Envoy Proxy công cộng (frontend-proxy)** ngoài rìa. Do đó, các microservices nội bộ trong cụm EKS vẫn kết nối và gửi dữ liệu trace/metrics trực tiếp tới OTel Collector qua mạng nội bộ (`opentelemetry-collector.techx-observability.svc:4317/4318`) hoàn toàn bình thường.
*   **Prometheus Health:** Toàn bộ Prometheus targets (node-exporter, cadvisor, applications) đều ở trạng thái **`UP` (Healthy)**, tiếp tục cào metrics liên tục dưới tải mà không bị gián đoạn.
*   **Dữ liệu không bị stale/gap:** Đã thực hiện kiểm tra luồng dữ liệu liên tục trong **15 phút chạy thử nghiệm** sau khi chuyển đổi. Không phát hiện bất kỳ khoảng trắng (gap) hay dữ liệu bị đứng (stale) nào trên các biểu đồ Grafana và Trace Jaeger.

---

## 5. Nhật ký kiểm toán & Xác minh flagd (Audit logs & flagd verification)

### A. Nguồn Log kiểm toán (Audit Trail):
Mọi kết nối Tunnel từ máy cá nhân thông qua SSM Session Manager đều được AWS tự động ghi nhận vào **AWS CloudTrail** để phục vụ CDO07 đối soát:
*   **Ai truy cập (Who):** Ghi lại chi tiết IAM User ARN hoặc Assumed Role Session ARN của tài khoản SSO cá nhân thực hiện kết nối.
*   **Lúc nào (When):** Ghi nhận chính xác timestamp theo UTC (`eventTime`).
*   **Từ đâu (Where):** Ghi lại địa chỉ IP Public của máy khách hàng (`sourceIPAddress`).
*   **Tác động vào đâu (Target):** Ghi lại Instance ID của Bastion Host (`i-072084d1cf0b2f1c9`) và cổng kết nối (`portNumber`).

### B. Xác minh cơ chế Sự cố (flagd):
*   Cấu hình chặn tuyến đường `/flagservice` và `/feature` chỉ ngăn chặn tin tặc tấn công tiêm mã (injection) vào dịch vụ cờ tính năng (Feature Flag) từ ngoài internet.
*   Các ứng dụng và hooks của OpenFeature nội bộ vẫn kết nối và giao tiếp trực tiếp với dịch vụ **`flagd`** (đang chạy trên cổng `8013` của namespace `techx-tf4`) thông qua DNS nội bộ của Kubernetes.
*   **Kết quả:** Cơ chế ứng phó sự cố (incident injection/flagd) hoạt động hoàn hảo, không bị vô hiệu hóa hoặc ảnh hưởng.
