# Hướng dẫn Xác thực & Nghiệm thu Bảo mật Ingress (MANDATE-01)

Tài liệu này hướng dẫn chi tiết các bước chạy lệnh kiểm thử và đối chiếu thực tế để xác nhận cụm hệ thống đã vượt qua các tiêu chí nghiệm thu của **[DIRECTIVE #1] (MANDATE-01-network-exposure)**: **Storefront tiếp tục công khai, mọi cổng vận hành phải riêng tư**.

Tài liệu này giúp **CDO07 (Kiểm toán bảo mật) và Mentor** chạy đối chiếu độc lập trên cụm EKS.

---

## 1. Bảng danh sách nghiệm thu (Acceptance Checklist)

| STT | Tài nguyên kiểm tra | Môi trường | Kết quả mong đợi | Trạng thái (Mentor/CDO07) |
| :--- | :--- | :--- | :--- | :---: |
| 1 | **Storefront (Trang chủ)** | Internet công cộng | Trả về mã **`200 OK`** và lướt web bình thường. | [ ] Đạt |
| 2 | **Grafana UI** | Internet công cộng | Trả về mã **`404 Not Found`** (Không cho phép vào). | [ ] Đạt |
| 3 | **Jaeger UI** | Internet công cộng | Trả về mã **`404 Not Found`** (Không cho phép vào). | [ ] Đạt |
| 4 | **Load Generator (Locust)** | Internet công cộng | Trả về mã **`404 Not Found`** (Không cho phép vào). | [ ] Đạt |
| 5 | **OTLP Ingestion Point** | Internet công cộng | Trả về mã **`404 Not Found`** (Tắt telemetry công cộng). | [ ] Đạt |
| 6 | **Private Access (Grafana)** | SSM Tunnel | Mở được Grafana qua địa chỉ `http://localhost:3000`. | [ ] Đạt |
| 7 | **Private Access (Jaeger)** | SSM Tunnel | Mở được Jaeger qua địa chỉ `http://localhost:16686`. | [ ] Đạt |
| 8 | **Private Access (Loadgen)** | SSM Tunnel | Mở được Locust qua địa chỉ `http://localhost:8089`. | [ ] Đạt |
| 9 | **Kiểm toán (Audit Trail)** | AWS CloudTrail | Ghi nhận được Log `StartSession` khi có người dùng tunnel. | [ ] Đạt |

---

## 2. Các bước chạy lệnh kiểm tra thực tế (Public Internet Checks)

Chạy các câu lệnh sau từ máy cá nhân của bạn (không kết nối VPN/Tunnel) để xác định trạng thái chặn của Proxy:

```bash
# Khai báo địa chỉ public ALB của bạn
export ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"

# 1. Kiểm tra Storefront (Kỳ vọng: 200 OK)
curl -I "$ALB/"

# 2. Kiểm tra Grafana (Kỳ vọng: 404 Not Found)
curl -I "$ALB/grafana"
curl -I "$ALB/grafana/"

# 3. Kiểm tra Jaeger (Kỳ vọng: 404 Not Found)
curl -I "$ALB/jaeger"
curl -I "$ALB/jaeger/ui/"

# 4. Kiểm tra Load Generator (Kỳ vọng: 404 Not Found)
curl -I "$ALB/loadgen"
curl -I "$ALB/loadgen/"

# 5. Kiểm tra OTLP Endpoint (Kỳ vọng: 404 Not Found)
curl -I "$ALB/otlp-http"
curl -I "$ALB/otlp-http/v1/traces"
```

---

## 3. Các bước kết nối riêng tư (SSM Tunnel Checks)

Dành cho Mentor/BTC chạy thử nghiệm kết nối an toàn từ xa:

### Bước 3.1: Đăng nhập AWS SSO
Mở terminal trên máy của bạn và chạy đăng nhập (sử dụng profile đã được cấp quyền SSM):
```bash
aws sso login --profile iam-tf4
```

### Bước 3.2: Lấy Instance ID của Bastion Host
Chạy lệnh để lấy ID của máy chủ Portal Bastion:
```bash
aws ec2 describe-instances `
  --filters "Name=tag:Name,Values=tf4-portal-bastion" "Name=instance-state-name,Values=running" `
  --query "Reservations[*].Instances[*].InstanceId" `
  --output text `
  --profile iam-tf4
```
*(Ghi lại Instance ID trả về, ví dụ: `i-0825abf366929a005`).*

### Bước 3.3: Khởi tạo SSM Tunnel để truy cập các Portals (Đã được Tự động hóa ngầm)

Các kết nối từ Bastion vào EKS đã được chạy tự động dưới dạng **systemd service** trên Bastion Host (tự động khôi phục kết nối và làm mới Token EKS mỗi 10 phút). 

Người kiểm thử (Mentor/BTC) chỉ cần mở duy nhất **1 cửa sổ Terminal** trên máy cá nhân và chạy lệnh tunnel tương ứng cho cổng mong muốn:

#### 📊 Truy cập Grafana:
```bash
aws ssm start-session `
  --target i-<Portal-Bastion-Instance-ID> `
  --document-name AWS-StartPortForwardingSession `
  --parameters '{"portNumber":["13000"],"localPortNumber":["3000"]}' `
  --profile iam-tf4
```
👉 Mở trình duyệt web của bạn và truy cập: **`http://localhost:3000`** để xem Dashboards.

#### 🕵️‍♂️ Truy cập Jaeger Traces:
```bash
aws ssm start-session `
  --target i-<Portal-Bastion-Instance-ID> `
  --document-name AWS-StartPortForwardingSession `
  --parameters '{"portNumber":["16686"],"localPortNumber":["16686"]}' `
  --profile iam-tf4
```
👉 Mở trình duyệt web của bạn và truy cập: **`http://localhost:16686`** để tìm kiếm Traces.

#### 📈 Truy cập Load Generator (Locust):
```bash
aws ssm start-session `
  --target i-<Portal-Bastion-Instance-ID> `
  --document-name AWS-StartPortForwardingSession `
  --parameters '{"portNumber":["18089"],"localPortNumber":["8089"]}' `
  --profile iam-tf4
```
👉 Mở trình duyệt web của bạn và truy cập: **`http://localhost:8089`** để điều khiển bài test tải.

---

## 4. Xác thực nhật ký kiểm toán (Audit Trail)

CDO07 chạy lệnh sau để chứng minh mọi hành động khởi tạo kết nối tunnel đều được AWS CloudTrail lưu trữ vĩnh viễn:

```bash
aws cloudtrail lookup-events `
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession `
  --profile iam-tf4
```
*(Kết quả ghi nhận phải có đầy đủ: User ARN, Thời gian truy cập, IP nguồn và ID của Bastion Host).*
