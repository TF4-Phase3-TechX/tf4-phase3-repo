# Danh sách kiểm tra an toàn triển khai cho flagd Sync

Danh sách kiểm tra an toàn này nhằm đảm bảo thành phần `flagd` và quá trình đồng bộ hóa flag OpenFeature được triển khai, giám sát và bảo vệ đúng cách trên môi trường cluster TF4. Mọi cấu hình sai sót đều có thể làm gián đoạn luồng sự cố (incident path) do Ban Tổ Chức (BTC) giả lập hoặc dẫn đến việc bị loại theo các quy tắc của Phase 3.

## Review Gate & Phê duyệt

* **Người kiểm duyệt**: Nguyên
* **Trạng thái người kiểm duyệt**: Trì hoãn (Đang chờ đánh giá ban đầu)
* **Các tùy chọn trạng thái**: `Approved` (Phê duyệt) / `Needs Info` (Cần thêm thông tin) / `Defer` (Trì hoãn)
* **Ngày mục tiêu**: Cuối Tuần 1 trước buổi chạy thử pitch (pitch dry-run)

---

## Trạng thái xác thực Runtime / Các yếu tố gây nghẽn (Blocker)

* **Trạng thái**: `BLOCKED-BY: Sẵn sàng triển khai TF4`
* **Chi tiết**: Môi trường cluster EKS hiện chưa thể truy cập cục bộ. Quá trình phân tích tĩnh từ các tệp mã nguồn, chart và cấu hình triển khai đã hoàn tất đầy đủ. Việc xác thực runtime sẽ được thực hiện lại trong vòng 24 giờ sau khi môi trường sẵn sàng hoạt động.

---

## Tài liệu tham khảo

Trước khi thực hiện bất kỳ hoạt động triển khai, nâng cấp hoặc rollback nào, hãy xem qua các tài liệu sau:
* [RULES.md](file:///d:/xbrain/tf4-phase3-repo/docs/requirements/RULES.md) - Mục 8: Quy tắc trò chơi (Hạ tầng flagd được bảo vệ).
* [GETTING_STARTED.md](file:///d:/xbrain/tf4-phase3-repo/docs/requirements/GETTING_STARTED.md) - Mục 3 & 5: Cấu hình deploy & flagd.
* [values-flagd-sync.yaml](file:///d:/xbrain/tf4-phase3-repo/deploy/values-flagd-sync.yaml) - Cấu hình Helm value đích.

---

## Các bước bắt buộc

Để triển khai nền tảng một cách an toàn và đảm bảo việc đồng bộ hóa flag trung tâm không bị gián đoạn, hãy làm theo các bước sau:

### 1. Cấu hình flagd Sync Token
Trước khi triển khai, hãy lấy mã đồng bộ trung tâm (`TOKEN`) do BTC cung cấp.
Thay vì commit trực tiếp token vào hệ thống quản lý phiên bản (Git), hãy đảm bảo token được truyền động thông qua một Kubernetes Secret hoặc được thiết lập trong câu lệnh Helm bằng cách sử dụng cơ chế thay thế placeholder (trình giữ chỗ).
* **Tùy chọn Secret (Khuyến nghị)**: Xác minh rằng secret `flagd-sync` có chứa key `token`.
* **Tùy chọn ghi đè giá trị (Value Override)**: Đảm bảo bạn đã thay thế `<TOKEN>` trong tệp ghi đè values bằng token thực tế.

### 2. Sửa lại Entrypoint của Container flagd
> [!IMPORTANT]
> Image container flagd chính thức (`ghcr.io/open-feature/flagd:v0.12.9`) không chứa shell (`/bin/sh` hoặc `/bin/bash`). Mọi nỗ lực sử dụng các lệnh bao shell (ví dụ: `/bin/sh -c "exec /flagd-build ..."`) sẽ khiến sidecar bị crash (`CrashLoopBackOff`).
* Sử dụng cấu trúc lệnh thực thi trực tiếp:
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

### 3. Áp dụng đúng các Helm Flag
Khi chạy bất kỳ lệnh Helm nào (chẳng hạn như `upgrade`, `install` hoặc `rollback`), you **BẮT BUỘC** phải chỉ định rõ tệp values của flagd sync.
```bash
helm upgrade --install techx-corp ./techx-corp-chart -n techx-tf4 --create-namespace \
  --set default.image.repository=<ECR_REGISTRY_URL> \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml
```
> [!WARNING]
> Nếu bạn bỏ sót `-f deploy/values-flagd-sync.yaml`, flagd sẽ quay về sử dụng cấu hình cục bộ và mất kết nối với hệ thống trung tâm, điều này vi phạm quy tắc cuộc thi.

---

## Các hành vi bị cấm

Để tránh việc bị loại tự động và đảm bảo hệ thống vận hành đáng tin cậy:

* **KHÔNG** xóa hoặc bỏ qua việc cấu hình chèn flagd sidecar trong các Helm chart hoặc template.
* **KHÔNG** thay đổi URI endpoint chứa flag trung tâm `https://122.248.223.194.sslip.io/flags.json` để trỏ đến một máy chủ tùy chỉnh hoặc máy chủ cục bộ khác.
* **KHÔNG** loại bỏ, biến thành comment, hoặc cấu trúc lại các hook/client đánh giá OpenFeature (OpenFeature evaluation hooks/clients) khỏi mã nguồn của các microservice.
* **KHÔNG** kích hoạt tính năng ghi đè flag cục bộ (local flag overrides) trên môi trường production trừ khi được phép rõ ràng. Giữ `sidecarContainers: []` để vô hiệu hóa giao diện web bật/tắt `flagd-ui` trong cluster.

---

## Xác minh sau khi triển khai

Khi quá trình triển khai hoặc rollback kết thúc, hãy chạy các bước xác minh sau:

1. **Kiểm tra trạng thái Pod flagd**:
   Đảm bảo tất cả các pod dịch vụ đang ở trạng thái `Running` và các sidecar flagd không ghi nhận số lần khởi động lại (restart):
   ```bash
   kubectl -n techx-tf4 get pods
   ```
2. **Kiểm tra Logs của Container flagd**:
   Xác nhận rằng flagd khởi động chính xác và đồng bộ hóa các flag từ HTTP provider:
   ```bash
   kubectl -n techx-tf4 logs -l app.kubernetes.io/name=flagd -c flagd
   ```
   *Kết quả mong đợi*: Phải chứa các log thể hiện việc lấy dữ liệu thành công từ HTTP provider và kết nối được tới máy chủ đồng bộ.
3. **Kiểm tra trạng thái hoạt động (Health) của OpenFeature Endpoint**:
   Kiểm tra xem các microservice có thể truy xuất thông tin đánh giá flag mà không phải sử dụng các giá trị mặc định dự phòng (fallback) hay không.

---

## Chi tiết các phát hiện P0/P1 & Đề xuất xử lý tiếp theo

| Đường dẫn tệp | Mức độ rủi ro | Tên cấu hình / Key | Dịch vụ bị ảnh hưởng | Bằng chứng | Đề xuất xử lý tiếp theo | Đường dẫn được bảo vệ? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [deploy/values-flagd-sync.yaml](file:///d:/xbrain/tf4-phase3-repo/deploy/values-flagd-sync.yaml#L10) | P0 | cấu hình `command` | `flagd` | Lệnh bao shell `/bin/sh -c` đã bị comment vì gây crash do thiếu shell trong image `ghcr.io/open-feature/flagd:v0.12.9`. | Bỏ comment và cấu trúc lại để sử dụng định dạng mảng thực thi trực tiếp không dùng shell bao `/bin/sh`. | **Có** |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L760) | P1 | `SECRET_KEY_BASE` | `flagd-ui` | `value: yYrECL4qbNwleYInGJYvVnSkwJuSQJ4ijPTx5tirGUXrbznFIBFVJdPl5t6O9ASw` (Đã bị comment) | Di chuyển sang Kubernetes Secret `flagd-ui-secrets` được nạp động thông qua `secretKeyRef`. | **Có** |
| [techx-corp-platform/docker-compose.yml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/docker-compose.yml#L707) | P1 | `SECRET_KEY_BASE` | `flagd-ui` (Dev) | `SECRET_KEY_BASE=yYrECL4qbNwleYInGJYvVnSkwJuSQJ4ijPTx5tirGUXrbznFIBFVJdPl5t6O9ASw` (Không bị comment) | Thay thế bằng biến môi trường hoặc tạo ngẫu nhiên một cách động trong docker-compose. | **Có** |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L183) | P1 | `DB_CONNECTION_STRING` | `accounting` | `value: Host=postgresql;Username=otelu;Password=otelp;Database=otel` | Lưu password vào Secret và tham chiếu qua cơ chế ghi đè biến môi trường. | Không |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L582) | P1 | `DB_CONNECTION_STRING` | `product-catalog` | `value: postgres://otelu:otelp@postgresql/otel?sslmode=disable` | Lưu password vào Secret và tham chiếu qua cơ chế ghi đè biến môi trường. | Không |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml#L619) | P1 | `DB_CONNECTION_STRING` | `product-reviews` | `value: host=postgresql user=otelu password=otelp dbname=otel` | Lưu password vào Secret và tham chiếu qua cơ chế ghi đè biến môi trường. | Không |
