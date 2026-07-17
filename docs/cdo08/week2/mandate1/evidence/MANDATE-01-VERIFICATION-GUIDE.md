# MANDATE-01 — Hướng dẫn Nghiệm thu & Kiểm thử dành cho Mentor (SSM Tunnel)

Tài liệu này hướng dẫn chi tiết các bước để **Mentor / BTC / CDO07** kiểm thử độc lập và nghiệm thu giải pháp bảo mật cổng vận hành (**MANDATE-01**) trên cụm EKS bằng cả máy tính **Windows** và **macOS (MacBook)**.

---

## 1. Chuẩn bị môi trường kiểm thử (Chỉ cần làm lần đầu)

Để chạy lệnh kết nối từ máy cá nhân (laptop), bạn cần cài đặt công cụ bổ trợ AWS Session Manager Plugin:

### 💻 Đối với Windows:
*   **Cài đặt:** Click tải [SessionManagerPluginSetup.exe (cho Windows 64-bit)](https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe) và chạy file cài đặt (chọn Next mặc định).
*   *Lưu ý:* Sau khi cài đặt xong, bạn bắt buộc phải **đóng cửa sổ terminal hiện tại và mở cửa sổ mới** để hệ thống nhận diện đường dẫn cài đặt.

### 🍎 Đối với macOS (MacBook):
*   **Cài đặt nhanh qua Homebrew:** Mở Terminal trên Mac và chạy lệnh:
    ```bash
    brew install --cask session-manager-plugin
    ```
*   **Cài đặt thủ công (nếu không dùng Homebrew):**
    ```bash
    curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac/sessionmanager-bundle.zip" -o "sessionmanager-bundle.zip"
    unzip sessionmanager-bundle.zip
    sudo ./sessionmanager-bundle/install -i /usr/local/sessionmanagerplugin -b /usr/local/bin/session-manager-plugin
    ```

---

## 2. Kiểm tra Ingress Public (Kỳ vọng: Bị chặn 404/405)

Truy cập trực tiếp các đường dẫn sau bằng trình duyệt (hoặc lệnh `curl`) từ internet công cộng để xác nhận Proxy đã chặn thành công:

*   **Storefront chính:** [http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/](http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/) $\rightarrow$ Kỳ vọng: **`200 OK`** (Vào mua hàng bình thường).
*   **Grafana:** [http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/grafana/](http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/grafana/) $\rightarrow$ Kỳ vọng: **`404 Not Found`** (Bị chặn).
*   **Jaeger UI:** [http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/jaeger/ui/](http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/jaeger/ui/) $\rightarrow$ Kỳ vọng: **`404 Not Found`** (Bị chặn).
*   **Load Generator (Locust):** [http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/loadgen/](http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/loadgen/) $\rightarrow$ Kỳ vọng: **`404 Not Found`** (Bị chặn).
*   **OTLP Endpoint:** [http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/otlp-http/v1/traces](http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/otlp-http/v1/traces) $\rightarrow$ Kỳ vọng: **`405 Method Not Allowed`** hoặc **`404`** (Bị chặn).

---

## 3. Kết nối riêng tư via SSM Tunnel (Kỳ vọng: Truy cập thành công)

Mở Terminal trên máy cá nhân và đăng nhập AWS SSO:
```bash
aws sso login --profile iam-tf4
```

Chọn câu lệnh tương ứng dưới đây tùy theo hệ điều hành máy tính của bạn:

### 💻 Dành cho hệ điều hành WINDOWS (Command Prompt / CMD):

*   **📊 A. Mở Tunnel Grafana (localhost:3000):**
    ```cmd
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters "{\"portNumber\":[\"13000\"],\"localPortNumber\":[\"3000\"]}" --profile iam-tf4 --region us-east-1
    ```
*   **🕵️‍♂️ B. Mở Tunnel Jaeger UI (localhost:16686/jaeger/ui/):**
    ```cmd
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters "{\"portNumber\":[\"16686\"],\"localPortNumber\":[\"16686\"]}" --profile iam-tf4 --region us-east-1
    ```
*   **📈 C. Mở Tunnel Load Generator (Locust) (localhost:8089):**
    ```cmd
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters "{\"portNumber\":[\"18089\"],\"localPortNumber\":[\"8089\"]}" --profile iam-tf4 --region us-east-1
    ```

---

### 🍎 Dành cho hệ điều hành macOS / LINUX (Bash / Zsh Terminal):

*   **📊 A. Mở Tunnel Grafana (localhost:3000):**
    ```bash
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["13000"],"localPortNumber":["3000"]}' --profile iam-tf4 --region us-east-1
    ```
*   **🕵️‍♂️ B. Mở Tunnel Jaeger UI (localhost:16686/jaeger/ui/):**
    ```bash
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["16686"],"localPortNumber":["16686"]}' --profile iam-tf4 --region us-east-1
    ```
*   **📈 C. Mở Tunnel Load Generator (Locust) (localhost:8089):**
    ```bash
    aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["18089"],"localPortNumber":["8089"]}' --profile iam-tf4 --region us-east-1
    ```

