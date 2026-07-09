# Báo cáo Quét Secrets/Config và flagd Safety - CDO08 Week 1

* **Người thực hiện**: Thuỷ (Security/Reliability)
* **Trạng thái**: Draft - Đang chờ đánh giá từ PM & Reviewer
* **Thời gian kiểm tra tĩnh**: 2026-07-08T21:38:00+07:00
* **Trạng thái kiểm tra Runtime**: 
  * **Trạng thái**: **SUCCESS** (Hoàn thành kiểm tra trên cụm EKS)
  * **Thời gian thử nghiệm**: 2026-07-09T11:30:00+07:00
  * **Kết quả**: Đã kết nối thành công tới EKS cluster `techx-tf4-cluster`. Các bằng chứng tĩnh đã được đối chiếu thực tế và xác nhận độ tin cậy cao.

---

## 1. Secrets/Config Baseline

Dưới đây là danh mục toàn bộ các cấu hình nhạy cảm, mật khẩu và khóa được phát hiện thông qua quá trình quét tĩnh trên thư mục `techx-corp-chart/`, `deploy/` và `techx-corp-platform/src/`.

| Đường dẫn tệp | Dòng/Ngữ cảnh | Tên cấu hình / Key | Dịch vụ liên quan | Phân loại | Mức độ rủi ro |
| :--- | :--- | :--- | :--- | :--- | :--- |
| [techx-corp-chart/values.yaml](../../../techx-corp-chart/values.yaml#L183) | L183 | `DB_CONNECTION_STRING` | `accounting` | Cấu hình nhạy cảm | Cao (P1) |
| [techx-corp-chart/values.yaml](../../../techx-corp-chart/values.yaml#L583) | L583 | `DB_CONNECTION_STRING` | `product-catalog` | Cấu hình nhạy cảm | Cao (P1) |
| [techx-corp-chart/values.yaml](../../../techx-corp-chart/values.yaml#L620) | L620 | `DB_CONNECTION_STRING` | `product-reviews` | Cấu hình nhạy cảm | Cao (P1) |
| [techx-corp-chart/values.yaml](../../../techx-corp-chart/values.yaml#L761) | L761 | `SECRET_KEY_BASE` | `flagd-ui` (Sidecar) | Cấu hình nhạy cảm (Đang bị comment) | Cao (P1) |
| [techx-corp-chart/values.yaml](../../../techx-corp-chart/values.yaml#L846) | L846 | `password` (Collector Scraper) | `postgresql` | Cấu hình nhạy cảm | Cao (P1) |
| [techx-corp-chart/values.yaml](../../../techx-corp-chart/values.yaml#L869) | L869 | `POSTGRES_PASSWORD` | `postgresql` | Cấu hình nhạy cảm | Cao (P1) |
| [techx-corp-chart/values.yaml](../../../techx-corp-chart/values.yaml#L1196) | L1196 | `adminPassword` | `grafana` | Cấu hình nhạy cảm | Cao (P1) |
| [techx-corp-chart/postgresql/init.sql](../../../techx-corp-chart/postgresql/init.sql#L4) | L4 | `PASSWORD` | `postgresql` | Cấu hình nhạy cảm | Cao (P1) |
| [techx-corp-platform/src/postgresql/init.sql](../../../techx-corp-platform/src/postgresql/init.sql#L4) | L4 | `PASSWORD` | `postgresql` | Cấu hình nhạy cảm | Cao (P1) |
| [techx-corp-platform/docker-compose.yml](../../../techx-corp-platform/docker-compose.yml#L707) | L707 | `SECRET_KEY_BASE` | `flagd-ui` (Dev Env) | Cấu hình nhạy cảm | Cao (P1) |
| [techx-corp-platform/src/flagd-ui/config/dev.exs](../../../techx-corp-platform/src/flagd-ui/config/dev.exs#L20) | L20 | `secret_key_base` | `flagd-ui` (Dev Code) | False Positive (Dev Key mặc định) | Thấp |
| [techx-corp-platform/src/flagd-ui/config/test.exs](../../../techx-corp-platform/src/flagd-ui/config/test.exs#L11) | L11 | `secret_key_base` | `flagd-ui` (Test Code) | False Positive (Test Key mặc định) | Thấp |
| [techx-corp-chart/values.yaml](../../../techx-corp-chart/values.yaml#L602) | L602 | `OPENAI_API_KEY` | `product-reviews` | False Positive (Dummy value `"dummy"`) | Không có |
| [techx-corp-platform/src/product-reviews/README.md](../../../techx-corp-platform/src/product-reviews/README.md#L30) | L30 | `OPENAI_API_KEY` | `product-reviews` | False Positive (Tài liệu hướng dẫn) | Không có |
| [deploy/values-flagd-sync.yaml](../../../deploy/values-flagd-sync.yaml#L17) | L17 | `Bearer <TOKEN>` | `flagd` | False Positive (Mẫu Token của BTC) | Thấp |
| [deploy/values-aio-llm.yaml](../../../deploy/values-aio-llm.yaml#L10) | L10-11 | `OPENAI_API_KEY` | `product-reviews` | Cấu hình tham chiếu Secret (Best Practice) | Không có |

> [!NOTE]
> Mặc dù các mật khẩu trên hệ thống hiện tại đều sử dụng giá trị mặc định dành cho môi trường phát triển (developer credentials như `otelp`, `otel`, `admin`), chúng vẫn đóng vai trò là mật khẩu thật để truy cập các dịch vụ PostgreSQL, Grafana và Phoenix Session của cụm chạy thử. Do đó, việc lưu trữ trực tiếp các khóa này dưới dạng plaintext trong Git là lỗ hổng bảo mật nghiêm trọng cần khắc phục.

---

## 2. Findings

### REL-001: Cấu hình flagd sync command lỗi & vô hiệu hóa central sync
* **Finding ID**: `REL-001`
* **Mô tả lỗi/gap**: 
  1. Trong tệp cấu hình triển khai `deploy/values-flagd-sync.yaml`, toàn bộ khối lệnh khởi chạy `command` và biến môi trường `FLAGD_SYNC_TOKEN` đang bị bình luận (comment) hóa. Điều này khiến pod `flagd` khi deploy sử dụng file này sẽ fallback về command mặc định trong `techx-corp-chart/values.yaml` (đọc cấu hình từ file local `file:./etc/flagd/demo.flagd.json`), dẫn tới ngắt kết nối hoàn toàn khỏi máy chủ đồng bộ flag tập trung của BTC.
  2. Lệnh khởi chạy nguyên bản được comment có sử dụng shell wrapper `/bin/sh -c "exec /flagd-build start..."`. Tuy nhiên, image container chính thức `ghcr.io/open-feature/flagd:v0.12.9` được xây dựng dạng distroless/minimal, hoàn toàn không chứa shell (`/bin/sh` hoặc `/bin/bash`). Nếu bỏ comment lệnh này trực tiếp, container sidecar sẽ liên tục crash với lỗi thiếu file thực thi (`CrashLoopBackOff`).
* **Pillar liên quan**: Reliability & Security (Compliance)
* **Service/Component ảnh hưởng**: Dịch vụ `flagd` sidecar trên tất cả các Pod.
* **Evidence**:
  * **Static Evidence** - [deploy/values-flagd-sync.yaml#L10-23](../../../deploy/values-flagd-sync.yaml#L10-23):
    ```yaml
    # command:
    #   - "/bin/sh"
    #   - "-c"
    #   - |-
    #     exec /flagd-build start \
    #       --port 8013 \
    #       --ofrep-port 8016 \
    #       --sources '[{"uri":"https://122.248.223.194.sslip.io/flags.json","provider":"http","authHeader":"Bearer '"${FLAGD_SYNC_TOKEN}"'"}]'
    ```
    ![REL-001 Static Evidence - values-flagd-sync.yaml bị comment](screenshort/REL-001.png)
  * **Runtime Evidence** (Kiểm tra ngày 2026-07-09T11:30:00+07:00):
    Log của container `flagd` xác nhận sidecar đang đọc cấu hình offline từ tệp cục bộ thay vì đồng bộ từ BTC:
    ```text
    2026-07-09T03:00:44.701Z    info    file/filepath_sync.go:99    watching filepath: ./etc/flagd/demo.flagd.json
    ```
    ![flagd đang chạy offline - đọc file local thay vì đồng bộ BTC](screenshort/flagd%20chạy%20offline.png)
    Đồng thời, Secret `flagd-sync` trong namespace `techx-tf4` chỉ chứa token giả lập (placeholder):
    ```yaml
    apiVersion: v1
    data:
      token: cGxhY2Vob2xkZXI= # Giải mã Base64: "placeholder"
    kind: Secret
    metadata:
      name: flagd-sync
    ```
    ![token đồng bộ flagd-sync chứa giá trị placeholder](screenshort/token%20đồng%20bộ.png)
    ![Cấu hình flagd-sync.yaml trên EKS runtime](screenshort/flagd-sync.png)
* **Impact**:
  * Hệ thống hoàn toàn không đồng bộ được các flag chỉ đạo sự cố từ BTC, dẫn đến vi phạm trực tiếp quy tắc Phase 3 (Hạ tầng flagd phải được bảo vệ và kết nối).
  * Nếu cố gắng kích hoạt lại mà không sửa lệnh, toàn bộ hệ thống microservices sẽ bị sập sidecar flagd, gây lỗi gọi API hoặc làm cạn kiệt ngân sách lỗi (error budget) của SLO.
* **Đề xuất xử lý**:
  Bỏ comment và cấu trúc lại lệnh khởi chạy thành định dạng mảng (exec form) không qua shell bao:
  ```yaml
  command:
    - "/flagd-build"
    - "start"
    - "--port"
    - "8013"
    - "--ofrep-port"
    - "8016"
    - "--sources"
    - '[{"uri":"https://122.248.223.194.sslip.io/flags.json","provider":"http","authHeader":"Bearer $(FLAGD_SYNC_TOKEN)"}]'
  env:
    - name: FLAGD_SYNC_TOKEN
      valueFrom:
        secretKeyRef:
          name: flagd-sync
          key: token
  ```
* **Priority đề xuất**: **P0** (Đạt 30 điểm Rubric và trực tiếp vi phạm quy tắc trò chơi nếu không sửa).
  * *Likelihood*: 5 (Chắc chắn xảy ra lỗi hoặc mất kết nối)
  * *Severity*: 5 (Sidecar crash hoặc mất kết nối điều khiển)
  * *Business Impact*: 5 (Nguy cơ bị loại khỏi Phase 3)
  * *SLO Impact*: 5 (Ảnh hưởng trực tiếp khả năng chịu lỗi và incident response)
  * *Security Impact*: 5 (Vi phạm protected path rules)
  * *Evidence Confidence*: 5 (Xác nhận khớp 100% bằng chứng tĩnh và log thực tế sidecar flagd)
  * *Điểm quy đổi*: 30/30
* **Owner phối hợp**: Hải (PM) / Nguyên (Reviewer)

---

### SEC-001: DB_CONNECTION_STRING in Accounting Service
* **Finding ID**: `SEC-001`
* **Mô tả lỗi/gap**: Chuỗi kết nối Database chứa thông tin đăng nhập dạng plaintext (Username/Password) được hardcode trực tiếp trong Helm `values.yaml` và lưu trữ trong Git.
* **Pillar liên quan**: Security
* **Service/Component ảnh hưởng**: Dịch vụ `accounting`
* **Evidence**:
  * [techx-corp-chart/values.yaml#L183](../../../techx-corp-chart/values.yaml#L183):
    ```yaml
    - name: DB_CONNECTION_STRING
      value: Host=postgresql;Username=otelu;Password=*****;Database=otel  # Đã che mật khẩu thật
    ```
* **Impact**: Kẻ tấn công có quyền đọc mã nguồn sẽ chiếm quyền truy cập trái phép vào cơ sở dữ liệu nghiệp vụ kế toán (accounting), dẫn đến rò rỉ dữ liệu tài chính hoặc thay đổi phi pháp dữ liệu.
* **Đề xuất xử lý**:
  1. Tạo Kubernetes Secret `accounting-db-secrets` chứa key `db-connection-string`.
  2. Trong `values.yaml`, override biến môi trường như sau:
     ```yaml
     - name: DB_CONNECTION_STRING
       valueFrom:
         secretKeyRef:
           name: accounting-db-secrets
           key: db-connection-string
     ```
* **Priority đề xuất**: **P1**
  * *Likelihood*: 3 | *Severity*: 4 | *Business*: 4 | *SLO*: 1 | *Security*: 5 | *Confidence*: 5
  * *Điểm quy đổi*: 22/30
* **Owner phối hợp**: Hải (PM)

---

### SEC-002: DB_CONNECTION_STRING in Product-Catalog Service
* **Finding ID**: `SEC-002`
* **Mô tả lỗi/gap**: Mật khẩu database PostgreSQL bị hardcode dạng plaintext bên trong URL kết nối của Product-Catalog.
* **Pillar liên quan**: Security
* **Service/Component ảnh hưởng**: Dịch vụ `product-catalog`
* **Evidence**:
  * [techx-corp-chart/values.yaml#L583](../../../techx-corp-chart/values.yaml#L583):
    ```yaml
    - name: DB_CONNECTION_STRING
      value: postgres://otelu:*****@postgresql/otel?sslmode=disable  # Đã che mật khẩu thật
    ```
* **Impact**: Lộ mật khẩu truy cập cơ sở dữ liệu product-catalog, cho phép đọc/sửa đổi thông tin danh mục sản phẩm trái phép.
* **Đề xuất xử lý**: Di chuyển chuỗi kết nối sang Kubernetes Secret tương tự dịch vụ Accounting.
* **Priority đề xuất**: **P1**
  * *Likelihood*: 3 | *Severity*: 4 | *Business*: 3 | *SLO*: 1 | *Security*: 5 | *Confidence*: 5
  * *Điểm quy đổi*: 21/30
* **Owner phối hợp**: Hải (PM)

---

### SEC-003: DB_CONNECTION_STRING in Product-Reviews Service
* **Finding ID**: `SEC-003`
* **Mô tả lỗi/gap**: Mật khẩu database PostgreSQL bị hardcode dạng plaintext trong chuỗi cấu hình kết nối của dịch vụ Product-Reviews.
* **Pillar liên quan**: Security
* **Service/Component ảnh hưởng**: Dịch vụ `product-reviews`
* **Evidence**:
  * [techx-corp-chart/values.yaml#L620](../../../techx-corp-chart/values.yaml#L620):
    ```yaml
    - name: DB_CONNECTION_STRING
      value: host=postgresql user=otelu password=***** dbname=otel  # Đã che mật khẩu thật
    ```
* **Impact**: Lộ mật khẩu database của reviews, kẻ tấn công có thể giả mạo hoặc xóa các phản hồi/review của khách hàng.
* **Đề xuất xử lý**: Sử dụng Kubernetes Secret để lưu cấu hình nhạy cảm này.
* **Priority đề xuất**: **P1**
  * *Likelihood*: 3 | *Severity*: 4 | *Business*: 3 | *SLO*: 1 | *Security*: 5 | *Confidence*: 5
  * *Điểm quy đổi*: 21/30
* **Owner phối hợp**: Hải (PM)

---

### SEC-004: SECRET_KEY_BASE in Flagd-UI (Dev and Chart config)
* **Finding ID**: `SEC-004`
* **Mô tả lỗi/gap**: Khóa ký session của framework Phoenix (Elixir) bị hardcode dưới dạng plaintext trong cả file docker-compose chạy dev và tệp Helm `values.yaml` (dòng bị comment).
* **Pillar liên quan**: Security
* **Service/Component ảnh hưởng**: Dịch vụ `flagd-ui`
* **Evidence**:
  * [techx-corp-platform/docker-compose.yml#L707](../../../techx-corp-platform/docker-compose.yml#L707):
    ```yaml
    - SECRET_KEY_BASE=yYrECL4qbNwleYInGJYvVnSkwJuSQJ4ijPTx5tirGUXrbznFIBFVJdPl5t6O9ASw
    ```
  * [techx-corp-chart/values.yaml#L761](../../../techx-corp-chart/values.yaml#L761) (Dưới khối comment sidecarContainers):
    ```yaml
    # - name: SECRET_KEY_BASE
    #   value: yYrECL4qbNwleYInGJYvVnSkwJuSQJ4ijPTx5tirGUXrbznFIBFVJdPl5t6O9ASw
    ```
* **Impact**: Cho phép kẻ tấn công giả mạo cookie session, thực hiện chiếm quyền điều khiển phiên làm việc (Session Hijacking) hoặc thực thi mã từ xa (RCE) trên ứng dụng flagd-ui.
* **Đề xuất xử lý**: Khởi tạo biến môi trường `SECRET_KEY_BASE` thông qua biến được tạo động ngẫu nhiên khi khởi chạy docker-compose, hoặc lưu trữ trong một Kubernetes Secret dành riêng cho flagd-ui khi chạy trên K8s.
* **Priority đề xuất**: **P1**
  * *Likelihood*: 4 | *Severity*: 4 | *Business*: 3 | *SLO*: 1 | *Security*: 5 | *Confidence*: 5
  * *Điểm quy đổi*: 22/30
* **Owner phối hợp**: Hải (PM)

---

### SEC-005: POSTGRES_PASSWORD in PostgreSQL Component
* **Finding ID**: `SEC-005`
* **Mô tả lỗi/gap**: Mật khẩu tài khoản quản trị tối cao (`POSTGRES_PASSWORD`) của PostgreSQL bị hardcode dưới dạng plaintext trong file values.yaml.
* **Pillar liên quan**: Security
* **Service/Component ảnh hưởng**: Thành phần `postgresql`
* **Evidence**:
  * [techx-corp-chart/values.yaml#L869](../../../techx-corp-chart/values.yaml#L869):
    ```yaml
    - name: POSTGRES_PASSWORD
      value: *****  # Đã che mật khẩu thật
    ```
* **Impact**: Toàn bộ dữ liệu của hệ thống nằm trong DB dùng chung có thể bị xóa sạch hoặc mã hóa tống tiền nếu hacker có quyền truy cập cluster hoặc repo.
* **Đề xuất xử lý**: Lưu cấu hình này vào Kubernetes Secret và tham chiếu qua `secretKeyRef`.
* **Priority đề xuất**: **P1**
  * *Likelihood*: 3 | *Severity*: 4 | *Business*: 4 | *SLO*: 1 | *Security*: 5 | *Confidence*: 5
  * *Điểm quy đổi*: 22/30
* **Owner phối hợp**: Hải (PM)

---

### SEC-006: adminPassword in Grafana Component
* **Finding ID**: `SEC-006`
* **Mô tả lỗi/gap**: Mật khẩu tài khoản admin mặc định của dashboard Grafana bị hardcode trực tiếp dưới dạng plaintext.
* **Pillar liên quan**: Security
* **Service/Component ảnh hưởng**: Thành phần `grafana`
* **Evidence**:
  * [techx-corp-chart/values.yaml#L1196](../../../techx-corp-chart/values.yaml#L1196):
    ```yaml
    adminPassword: *****  # Đã che mật khẩu thật
    ```
* **Impact**: Hacker hoặc người dùng không có thẩm quyền có thể truy cập dashboard quản lý với quyền Admin, phá hoại cấu hình lưu trữ log/metric hoặc thay đổi cài đặt nguồn dữ liệu.
* **Đề xuất xử lý**: Cấu hình subchart Grafana đọc mật khẩu Admin từ Kubernetes Secret, hoặc tích hợp cơ chế xác thực SSO / tắt tính năng đăng nhập mật khẩu mặc định form login.
* **Priority đề xuất**: **P1**
  * *Likelihood*: 4 | *Severity*: 3 | *Business*: 2 | *SLO*: 1 | *Security*: 5 | *Confidence*: 5
  * *Điểm quy đổi*: 20/30
* **Owner phối hợp**: Hải (PM)

---

### SEC-007: Mật khẩu người dùng PostgreSQL tĩnh trong script init.sql
* **Finding ID**: `SEC-007`
* **Mô tả lỗi/gap**: Script SQL khởi tạo cơ sở dữ liệu ban đầu chứa mật khẩu tĩnh của tài khoản người dùng ứng dụng được commit trực tiếp lên VCS.
* **Pillar liên quan**: Security
* **Service/Component ảnh hưởng**: Thành phần `postgresql`
* **Evidence**:
  * [techx-corp-chart/postgresql/init.sql#L4](../../../techx-corp-chart/postgresql/init.sql#L4) & [techx-corp-platform/src/postgresql/init.sql#L4](../../../techx-corp-platform/src/postgresql/init.sql#L4):
    ```sql
    CREATE USER otelu WITH PASSWORD '*****';  -- Đã che mật khẩu thật
    ```
* **Impact**: Mật khẩu database được ghi dấu vết vĩnh viễn trong lịch sử Git commit, rất khó thu hồi/rotate một cách an sau.
* **Đề xuất xử lý**: Sử dụng các biến môi trường thay thế động tại thời điểm init database hoặc cấu hình PostgreSQL Docker Entrypoint để nạp mật khẩu thông qua Secret thay vì script khởi tạo tĩnh.
* **Priority đề xuất**: **P1**
  * *Likelihood*: 3 | *Severity*: 4 | *Business*: 3 | *SLO*: 1 | *Security*: 5 | *Confidence*: 5
  * *Điểm quy đổi*: 21/30
* **Owner phối hợp**: Hải (PM)

---

### SEC-008: PostgreSQL Scraper Password in Pod Annotations
* **Finding ID**: `SEC-008`
* **Mô tả lỗi/gap**: Mật khẩu của tài khoản thu thập chỉ số PostgreSQL (PostgreSQL metrics scraper credentials) được đặt dưới dạng plaintext trực tiếp trong pod metadata annotations.
* **Pillar liên quan**: Security
* **Service/Component ảnh hưởng**: Thành phần `postgresql`
* **Evidence**:
  * [techx-corp-chart/values.yaml#L846](../../../techx-corp-chart/values.yaml#L846):
    ```yaml
    # Nằm trong annotation io.opentelemetry.discovery.metrics/config:
    password: *****  # Đã che mật khẩu thật
    ```
    ![PostgreSQL scraper password được ghi plaintext trong Pod Annotation](screenshort/PostgreSQL%20qua%20Pod%20Annotation.png)
* **Impact**: Bất kỳ người dùng hoặc dịch vụ nào có quyền xem thông tin Pod metadata (lệnh `kubectl get pod -o yaml`) trong Kubernetes namespace đều có thể đọc được mật khẩu PostgreSQL này.
* **Đề xuất xử lý**: Thay vì ghi trực tiếp vào annotations của pod, hãy lưu thông tin credentials này vào secret của OpenTelemetry Collector và trỏ cấu hình scraping đến secret đó.
* **Priority đề xuất**: **P1**
  * *Likelihood*: 4 | *Severity*: 4 | *Business*: 2 | *SLO*: 1 | *Security*: 5 | *Confidence*: 5
  * *Điểm quy đổi*: 21/30
* **Owner phối hợp**: Hải (PM)

---

## 3. flagd Safety Evidence

### A. Tệp values bắt buộc khi deploy
Khi thực hiện bất kỳ lệnh Helm nào (`install`, `upgrade`, hoặc `rollback`), ta **BẮT BUỘC** phải chỉ định file ghi đè an toàn flagd:
```bash
-f deploy/values-flagd-sync.yaml
```
*Lưu ý*: Việc thiếu file cấu hình này sẽ làm `flagd` mất kết nối với nguồn flag của BTC và tự động rollback về cấu hình local, vi phạm thể lệ Phase 3.

Lệnh deploy đầy đủ khuyến nghị:
```bash
helm upgrade --install techx-corp ./techx-corp-chart -n techx-tf4 --create-namespace \
  --set default.image.repository=<ECR_REGISTRY_URL> \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml
```

### B. Kiểm tra cần chạy sau Upgrade/Rollback
1. **Kiểm tra trạng thái các Pod**:
   ```bash
   kubectl -n techx-tf4 get pods
   ```
   *Kết quả mong đợi*: Pod có sidecar flagd phải ở trạng thái `Running` và có `2/2` container ready, số lần restart là `0`.
2. **Kiểm tra Logs đồng bộ của container flagd**:
   ```bash
   kubectl -n techx-tf4 logs -l app.kubernetes.io/name=flagd -c flagd
   ```
   *Kết quả mong đợi*: Log phải ghi nhận kết nối thành công tới HTTP provider (`https://122.248.223.194.sslip.io/flags.json`) và lấy dữ liệu thành công, không có thông báo lỗi `CrashLoopBackOff` hay lỗi xác thực token.
3. **Xác minh các endpoint OpenFeature**:
   Kiểm tra logs của các service (`payment`, `recommendation`...) để đảm bảo việc phân tích flag không bị rớt về giá trị mặc định dự phòng (fallback):
   ```bash
   kubectl -n techx-tf4 logs deploy/payment -c payment --tail=50
   ```
   ```bash
   kubectl -n techx-tf4 logs deploy/recommendation -c recommendation --tail=50
   ```

### C. Các thay đổi bị cấm (Protected Paths)
* **KHÔNG** xóa hoặc vô hiệu hóa cấu hình sidecar container `flagd` trong Helm chart.
* **KHÔNG** thay đổi địa chỉ URI của central flag provider (`https://122.248.223.194.sslip.io/flags.json`).
* **KHÔNG** xóa hoặc bình luận (comment) các đoạn mã gọi SDK OpenFeature trong source code các microservices (ví dụ: gọi `OpenFeature.getClient().getNumberValue("paymentFailure", 0)` trong dịch vụ `payment`).
* **KHÔNG** bật tính năng ghi đè flag cục bộ (`flagd-ui` hoặc local flag overrides) trên môi trường production. Giá trị cấu hình `sidecarContainers: []` phải được giữ nguyên để tắt giao diện web bật/tắt flag trong cluster.

---

## 4. Backlog Candidates

Dưới đây là danh sách các issue đề xuất đưa vào backlog của CDO08 để Hải (PM) đánh giá dựa trên rubric ưu tiên:

1. **Issue 1: Sửa lệnh khởi chạy flagd sync trong Helm Values**
   * *Mô tả*: Cấu trúc lại mảng lệnh trong `deploy/values-flagd-sync.yaml` để chạy dạng exec trực tiếp (không dùng shell wrapper `/bin/sh -c`) và bỏ comment để kích hoạt đồng bộ hóa flag với BTC.
   * *Độ ưu tiên đề xuất*: **P0** (Do ảnh hưởng tuân thủ luật chơi Phase 3 và gây crash hệ thống).
2. **Issue 2: Di chuyển DB Connection String sang Kubernetes Secrets**
   * *Mô tả*: Tạo secret `db-secrets` và cập nhật cấu hình cho 3 dịch vụ `accounting`, `product-catalog`, `product-reviews` lấy thông tin từ secret thông qua cơ chế `secretKeyRef`.
   * *Độ ưu tiên đề xuất*: **P1**
3. **Issue 3: Bảo mật thông tin đăng nhập PostgreSQL và Grafana Admin**
   * *Mô tả*: Chuyển mật khẩu quản trị postgres (`POSTGRES_PASSWORD`) và Grafana `adminPassword` sang Kubernetes Secret, cấu hình subchart lấy giá trị từ secret.
   * *Độ ưu tiên đề xuất*: **P1**
4. **Issue 4: Khắc phục rò rỉ khóa SECRET_KEY_BASE của flagd-ui**
   * *Mô tả*: Tạo giá trị ngẫu nhiên cho `SECRET_KEY_BASE` trong docker-compose dev và cấu hình nạp từ secret cho môi trường K8s.
   * *Độ ưu tiên đề xuất*: **P1**
5. **Issue 5: Sửa đổi PostgreSQL Init Scripts và Metrics Scraper Credentials**
   * *Mô tả*: Thay thế mật khẩu plaintext trong script init database và pod annotations bằng cơ chế nạp credentials từ biến môi trường/secret của collector.
   * *Độ ưu tiên đề xuất*: **P1**
