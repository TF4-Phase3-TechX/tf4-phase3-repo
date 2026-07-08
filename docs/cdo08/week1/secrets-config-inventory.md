# Báo cáo Thống kê Secrets và Cấu hình Nhạy cảm

Tài liệu này thống kê tất cả các mật khẩu cứng (hardcoded), API keys, tokens, chuỗi kết nối cơ sở dữ liệu (connection strings), và cấu hình nhạy cảm được phát hiện thông qua phân tích tĩnh trong các thư mục `techx-corp-chart`, `deploy`, và `techx-corp-platform/src`.

## Review Gate & Sign-off

* **Reviewer**: Nguyên
* **Reviewer Status**: Defer (Đang chờ đánh giá ban đầu)
* **Status Options**: `Approved` / `Needs Info` / `Defer`
* **Target Date**: Cuối Tuần 1 trước buổi pitch dry-run

---

## Trạng thái Xác minh Runtime / Blocker Status

* **Trạng thái**: `BLOCKED-BY: TF4 deployment readiness`
* **Chi tiết**: Môi trường EKS cluster chưa thể truy cập được từ máy cục bộ (kết nối đến cluster bị từ chối). Quá trình phân tích tĩnh đối với các file mã nguồn, Helm chart, và cấu hình deploy đã hoàn tất 100%. Việc xác minh runtime sẽ được thực hiện lại trong vòng 24 giờ sau khi môi trường sẵn sàng.

---

## Các Lệnh & Mẫu Tìm Kiếm Đã Dùng (Bằng chứng)

Bảng thống kê này được tổng hợp bằng cách sử dụng công cụ ripgrep (`rg`) để tìm kiếm các mẫu cấu hình nhạy cảm chính:
```bash
# Tìm kiếm mẫu PASSWORD
rg -i "PASSWORD" techx-corp-chart/ deploy/ techx-corp-platform/src/

# Tìm kiếm mẫu SECRET
rg -i "SECRET" techx-corp-chart/ deploy/ techx-corp-platform/src/

# Tìm kiếm mẫu API_KEY
rg -i "API_KEY" techx-corp-chart/ deploy/ techx-corp-platform/src/

# Tìm kiếm mẫu TOKEN
rg -i "TOKEN" techx-corp-chart/ deploy/ techx-corp-platform/src/

# Tìm kiếm mẫu DB_CONNECTION_STRING
rg -i "DB_CONNECTION_STRING" techx-corp-chart/ deploy/ techx-corp-platform/src/

# Tìm kiếm mẫu OPENAI_API_KEY
rg -i "OPENAI_API_KEY" techx-corp-chart/ deploy/ techx-corp-platform/src/

# Tìm kiếm mẫu SECRET_KEY_BASE
rg -i "SECRET_KEY_BASE" techx-corp-chart/ deploy/ techx-corp-platform/src/
```

---

## Bảng Thống Kê Secrets (Inventory Table)

| Đường dẫn File | Dòng/Ngữ cảnh | Tên Key/Cấu hình | Dịch vụ | Có phải Secret? | Mức độ rủi ro | Đề xuất xử lý | Đường dẫn được bảo vệ? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L183) | L183 | `DB_CONNECTION_STRING` | `accounting` | Có | P1 | Di chuyển vào Secret | Không |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L582) | L582 | `DB_CONNECTION_STRING` | `product-catalog` | Có | P1 | Di chuyển vào Secret | Không |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L619) | L619 | `DB_CONNECTION_STRING` | `product-reviews` | Có | P1 | Di chuyển vào Secret | Không |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L761) | L761 | `SECRET_KEY_BASE` | `flagd` / `flagd-ui` | Có | P1 | Di chuyển vào Secret / Cấu hình flagd được bảo vệ | Có |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L847) | L847 | `password` (OTEL metrics) | `postgresql` | Có | P1 | Cần thảo luận / Di chuyển vào Secret | Không |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L870) | L870 | `POSTGRES_PASSWORD` | `postgresql` | Có | P1 | Di chuyển vào Secret | Không |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L1197) | L1197 | `adminPassword` | `grafana` | Có | P1 | Di chuyển vào Secret | Không |
| [techx-corp-chart/postgresql/init.sql](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/postgresql/init.sql#L4) | L4 | `PASSWORD` | `postgresql` | Có | P1 | Cần thảo luận / Di chuyển vào Secret | Không |
| [techx-corp-platform/src/postgresql/init.sql](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/postgresql/init.sql#L4) | L4 | `PASSWORD` | `postgresql` | Có | P1 | Cần thảo luận / Di chuyển vào Secret | Không |
| [techx-corp-platform/src/flagd-ui/config/dev.exs](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/flagd-ui/config/dev.exs#L20) | L20 | `secret_key_base` | `flagd-ui` | Phát hiện giả (Dev Key) | Thấp | Giữ nguyên | Có |
| [techx-corp-platform/src/flagd-ui/config/test.exs](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/flagd-ui/config/test.exs#L11) | L11 | `secret_key_base` | `flagd-ui` | Phát hiện giả (Test Key) | Thấp | Giữ nguyên | Có |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L601) | L601 | `OPENAI_API_KEY` | `product-reviews` | Phát hiện giả (Dummy Key) | Không có | Giữ nguyên | Không |
| [techx-corp-platform/src/product-reviews/README.md](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/product-reviews/README.md#L30) | L30 | `OPENAI_API_KEY` | `product-reviews` | Phát hiện giả (Tài liệu) | Không có | Giữ nguyên | Không |
| [deploy/values-flagd-sync.yaml](file:///d:/xbrain/tf4-phase3-repo/deploy/values-flagd-sync.yaml#L17) | L17 | `Bearer <TOKEN>` | `flagd` | Phát hiện giả (Chỗ trống) | Thấp | Giữ nguyên / Cần thảo luận | Có |
| [deploy/values-aio-llm.yaml](file:///d:/xbrain/tf4-phase3-repo/deploy/values-aio-llm.yaml#L11) | L11 | `OPENAI_API_KEY` | `product-reviews` | Không (Tham chiếu Secret) | Không có | Giữ nguyên (Thực hành tốt) | Không |

---

## Chi tiết các Phát Hiện P0/P1 & Đề Xuất Hành Động Tiếp Theo

### 1. DB_CONNECTION_STRING trong Dịch vụ Accounting
* **Mức độ rủi ro**: P1
* **Mô tả rủi ro**: Thông tin đăng nhập cơ sở dữ liệu (Username/Password) bị ghi cứng trong Helm `values.yaml` và đẩy lên hệ thống quản lý mã nguồn (VCS). Nếu kẻ tấn công có quyền truy cập kho lưu trữ mã nguồn, họ sẽ ngay lập tức có quyền truy cập vào schema cơ sở dữ liệu accounting.
* **Dịch vụ/File ảnh hưởng**: `accounting` / [techx-corp-chart/values.yaml:L183](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L183)
* **Bằng chứng**: `value: Host=postgresql;Username=otelu;Password=otelp;Database=otel`
* **Đề xuất xử lý (Tuần 2-3)**: Di chuyển thông tin đăng nhập cơ sở dữ liệu vào một Kubernetes Secret (ví dụ: `accounting-db-secrets`). Trong file `values.yaml`, ghi đè biến môi trường để tham chiếu giá trị từ secret này.
* **Dự thảo ưu tiên**: P1

### 2. DB_CONNECTION_STRING trong Dịch vụ Product-Catalog
* **Mức độ rủi ro**: P1
* **Mô tả rủi ro**: Mật khẩu cơ sở dữ liệu bị ghi cứng trực tiếp bên trong URL kết nối trong file `values.yaml`.
* **Dịch vụ/File ảnh hưởng**: `product-catalog` / [techx-corp-chart/values.yaml:L582](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L582)
* **Bằng chứng**: `value: postgres://otelu:otelp@postgresql/otel?sslmode=disable`
* **Đề xuất xử lý (Tuần 2-3)**: Lưu trữ toàn bộ chuỗi kết nối vào một Kubernetes Secret, hoặc cấu hình ứng dụng để đọc các biến môi trường user/password từ secret qua `secretKeyRef` và dựng chuỗi kết nối động tại runtime.
* **Dự thảo ưu tiên**: P1

### 3. DB_CONNECTION_STRING trong Dịch vụ Product-Reviews
* **Mức độ rủi ro**: P1
* **Mô tả rủi ro**: Mật khẩu kết nối cơ sở dữ liệu (`password=otelp`) bị ghi cứng trực tiếp và commit lên hệ thống kiểm soát phiên bản.
* **Dịch vụ/File ảnh hưởng**: `product-reviews` / [techx-corp-chart/values.yaml:L619](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L619)
* **Bằng chứng**: `value: host=postgresql user=otelu password=otelp dbname=otel`
* **Đề xuất xử lý (Tuần 2-3)**: Tách cấu hình kết nối cơ sở dữ liệu ra một Kubernetes Secret và tham chiếu bằng `valueFrom.secretKeyRef`.
* **Dự thảo ưu tiên**: P1

### 4. SECRET_KEY_BASE trong Flagd-UI (Flagd Sidecar)
* **Mức độ rủi ro**: P1
* **Mô tả rủi ro**: Khóa ký phiên (Phoenix session signing base key) bị ghi cứng. Các khóa ghi cứng này có thể dẫn đến rủi ro giả mạo cookie, chiếm đoạt phiên làm việc (session hijacking), hoặc giải mã dữ liệu trạng thái nhạy cảm của ứng dụng Elixir flagd-ui.
* **Dịch vụ/File ảnh hưởng**: `flagd` / `flagd-ui` / [techx-corp-chart/values.yaml:L761](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L761)
* **Bằng chứng**: `value: yYrECL4qbNwleYInGJYvVnSkwJuSQJ4ijPTx5tirGUXrbznFIBFVJdPl5t6O9ASw`
* **Đề xuất xử lý (Tuần 2-3)**: Di chuyển `SECRET_KEY_BASE` vào một Kubernetes Secret (ví dụ: `flagd-ui-secrets`) và tham chiếu trong `values.yaml` sử dụng `secretKeyRef`.
* **Dự thảo ưu tiên**: P1

### 5. POSTGRES_PASSWORD trong Thành phần PostgreSQL
* **Mức độ rủi ro**: P1
* **Mô tả rủi ro**: Mật khẩu quản trị cơ sở dữ liệu admin `otel` bị ghi cứng trực tiếp trong cấu hình `values.yaml`.
* **Dịch vụ/File ảnh hưởng**: `postgresql` / [techx-corp-chart/values.yaml:L870](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L870)
* **Bằng chứng**: `value: otel`
* **Đề xuất xử lý (Tuần 2-3)**: Chuyển mật khẩu vào một Kubernetes Secret và tiêm vào deployment cơ sở dữ liệu bằng `valueFrom.secretKeyRef`.
* **Dự thảo ưu tiên**: P1

### 6. Mật khẩu Scraper trong Thành phần PostgreSQL
* **Mức độ rủi ro**: P1
* **Mô tả rủi ro**: Thông tin xác thực của bộ thu thập số liệu metrics collector scraper bị ghi cứng trực tiếp trong metadata annotations của Pod trong `values.yaml`.
* **Dịch vụ/File ảnh hưởng**: `postgresql` / [techx-corp-chart/values.yaml:L847](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L847)
* **Bằng chứng**: `password: otel` nằm dưới annotation `io.opentelemetry.discovery.metrics/config`.
* **Đề xuất xử lý (Tuần 2-3)**: Đánh giá lại việc xử lý thông tin xác thực scraper; thông tin đăng nhập nên được lưu trong các secret cấu hình của OpenTelemetry Collector hoặc lấy động thay vì hiển thị trực tiếp trong pod annotations (nơi bất kỳ ai truy vấn tài nguyên trong cụm đều có thể thấy).
* **Dự thảo ưu tiên**: P1

### 7. adminPassword trong Thành phần Grafana
* **Mức độ rủi ro**: P1
* **Mô tả rủi ro**: Thông tin đăng nhập mặc định của quản trị viên Grafana (`admin`) bị ghi cứng.
* **Dịch vụ/File ảnh hưởng**: `grafana` / [techx-corp-chart/values.yaml:L1197](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L1197)
* **Bằng chứng**: `adminPassword: admin`
* **Đề xuất xử lý (Tuần 2-3)**: Cấu hình subchart Grafana để đọc mật khẩu quản trị viên từ một Kubernetes Secret, hoặc vô hiệu hóa cấu hình đăng nhập mặc định vì quyền truy cập admin vô danh (anonymous admin) đã được bật trong môi trường này.
* **Dự thảo ưu tiên**: P1

### 8. Mật khẩu Khởi Tạo Cơ Sở Dữ Liệu trong file init.sql
* **Mức độ rủi ro**: P1
* **Mô tả rủi ro**: File kịch bản khởi tạo thông tin đăng nhập tĩnh `CREATE USER otelu WITH PASSWORD 'otelp';` được lưu trữ trực tiếp trong VCS.
* **Dịch vụ/File ảnh hưởng**: `postgresql` / [techx-corp-chart/postgresql/init.sql:L4](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/postgresql/init.sql#L4) & [techx-corp-platform/src/postgresql/init.sql:L4](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/postgresql/init.sql#L4)
* **Bằng chứng**: `CREATE USER otelu WITH PASSWORD 'otelp';`
* **Đề xuất xử lý (Tuần 2-3)**: Tối ưu hóa quá trình khởi tạo cơ sở dữ liệu PostgreSQL để thiết lập mật khẩu động từ các biến môi trường tiêm qua secrets khi deploy, hoặc mount template kịch bản khởi tạo đã được render mật khẩu tự động.
* **Dự thảo ưu tiên**: P1