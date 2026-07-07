# Cẩm nang Kiểm tra Sức khỏe Hệ thống (Health Evidence Checks)

Tài liệu này cung cấp các câu lệnh tiêu chuẩn để kiểm tra và lấy bằng chứng trạng thái sức khỏe của lớp Runtime và lớp Data Stores trong cụm Kubernetes.

## 1. Kiểm tra lớp Runtime (Kubernetes Pods)
*(Dành cho các service chạy trên cụm như Checkout, Payment, Cart...)*

* **Lệnh kiểm tra trạng thái tổng thể:** 
  ```bash
  kubectl get pods -n <namespace>
  ```
  * **Kỳ vọng:** Cột `READY` phải đạt chỉ số tối đa (ví dụ: `1/1` hoặc `3/3`), cột `STATUS` là `Running`.
* **Lệnh kiểm tra pod bị restart liên tục (CrashLoopBackOff):**
  ```bash
  kubectl get pods -n <namespace> | awk '$4 > 0'
  ```
  * **Kỳ vọng:** Không có pod nào bị khởi động lại (cột `RESTARTS` bằng 0).
* **Lệnh lấy sự kiện (Events) cảnh báo của một Pod:**
  ```bash
  kubectl describe pod <tên-pod> -n <namespace>
  ```
  * Để lọc nhanh các sự kiện cảnh báo/lỗi ở cuối trang:
    ```bash
    kubectl describe pod <tên-pod> -n <namespace> | grep -A 10 Events:
    ```
  * **Kỳ vọng:** Không chứa các sự kiện lỗi nghiêm trọng như `FailedScheduling`, `OOMKilled`, `Liveness probe failed`, `BackOff`.

---

## 2. Kiểm tra lớp Dữ liệu (Data Stores)
*(Các lệnh chẩn đoán kết nối và sức khỏe cơ sở dữ liệu dựa trên cấu hình thực tế của dự án)*

### A. PostgreSQL
* **Nhãn Selector tương ứng:** `opentelemetry.io/name=postgresql` (Cấu hình khởi tạo tại [init.sql](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/postgresql/init.sql))
* **Lệnh kiểm tra pod DB:**
  ```bash
  kubectl get pods -l opentelemetry.io/name=postgresql -n <namespace>
  ```
* **Lệnh test ping trực tiếp trong Container:**
  ```bash
  kubectl exec -it deploy/postgresql -n <namespace> -- pg_isready -h localhost -U otelu -d otel
  ```
  * **Kỳ vọng:** Trả về `/tmp:5432 - accepting connections`.

### B. Valkey (Giải pháp thay thế Redis cho Cart Service)
* **Nhãn Selector tương ứng:** `opentelemetry.io/name=valkey-cart`
* **Lệnh kiểm tra pod DB:**
  ```bash
  kubectl get pods -l opentelemetry.io/name=valkey-cart -n <namespace>
  ```
* **Lệnh test ping trực tiếp trong Container:**
  ```bash
  kubectl exec -it deploy/valkey-cart -n <namespace> -- valkey-cli PING
  ```
  * *Lưu ý: Nếu container sử dụng lệnh redis client cũ, có thể chạy:*
    ```bash
    kubectl exec -it deploy/valkey-cart -n <namespace> -- redis-cli PING
    ```
  * **Kỳ vọng:** Trả về `PONG`.

### C. Kafka
* **Nhãn Selector tương ứng:** `opentelemetry.io/name=kafka`
* **Topic của luồng đặt hàng:** Topic `"orders"` (Được định nghĩa tại [producer.go:L14](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/checkout/kafka/producer.go#L14))
* **Lệnh kiểm tra Broker:**
  ```bash
  kubectl get pods -l opentelemetry.io/name=kafka -n <namespace>
  ```
* **Lệnh liệt kê topics trực tiếp trong Kafka Container:**
  ```bash
  kubectl exec -it deploy/kafka -n <namespace> -- kafka-topics.sh --list --bootstrap-server localhost:9092
  ```
  * **Kỳ vọng:** Trả về danh sách topic, trong đó bắt buộc có topic `"orders"`.
