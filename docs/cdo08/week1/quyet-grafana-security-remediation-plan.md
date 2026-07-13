# Kế hoạch khắc phục lỗ hổng Grafana Anonymous Admin (CDO08-SEC-02)

- **Owner chính:** Quyết
- **Pillar:** Security
- **Priority:** P1
- **Mã Backlog:** `CDO08-SEC-02`

---

## 1. Lý do thực hiện (Why this task?)
Grafana anonymous user hiện có quyền Admin nếu Grafana được expose lại. Nếu public reachable, người ngoài có thể có quyền admin dashboard/datasource. Mật khẩu mặc định của tài khoản `admin` vẫn là `admin` và đang bị hardcode.

### Evidence Week 1:
* `techx-corp-chart/values.yaml:1190-1193`: anonymous enabled, `org_role: Admin`.
* `techx-corp-chart/values.yaml:1197`: admin password `admin`.
* `techx-corp-platform/src/grafana/grafana.ini` (Config chạy local): `disable_login_form = true`, `org_role = Admin`.

---

## 2. So sánh các phương án Access Control cho Grafana

| Phương án | Setup & Vận hành | Mức độ thuận tiện cho team | Rủi ro bảo mật | Đánh giá chung |
|---|---|---|---|---|
| **Anonymous Admin (Hiện tại)** | Mặc định, không cần làm gì | Rất cao (truy cập thẳng có full quyền) | Cực kỳ cao (bị kiểm soát toàn bộ từ ngoài) | Không chấp nhận được |
| **Anonymous Viewer + Login Form + Mật khẩu mạnh (Đề xuất)** | Dễ (chỉnh sửa values/ini và sử dụng K8s secret/env) | Cao (team vẫn xem được dashboard nhanh, admin cần login để cấu hình) | Thấp (chặn hoàn toàn việc chỉnh sửa trái phép) | Khuyến nghị cho TF4 |
| **Tắt Anonymous hoàn toàn** | Dễ | Thấp (mọi người đều phải login mới xem được dashboard) | Rất thấp | An toàn nhất nhưng giảm tiện ích |
| **Tích hợp SSO / OIDC** | Phức tạp (cần IdP, cấu hình client/scopes) | Rất cao sau khi setup | Rất thấp | Tốt nhất về lâu dài, quá phạm vi hiện tại |

---

## 3. Phương án đề xuất cho TF4

1. **Hạ quyền Anonymous từ Admin về Viewer**: Cho phép bất kỳ ai truy cập chỉ có quyền xem (Viewer).
2. **Kích hoạt màn hình Login**: Cho phép admin đăng nhập khi cần cấu hình/chỉnh sửa.
3. **Mật khẩu admin mạnh và không hardcode**: 
   - **Trên EKS**: Tránh rủi ro sinh lại mật khẩu ngẫu nhiên mới mỗi lần chạy `helm upgrade`. Ta sẽ tạo trước một Kubernetes Secret tĩnh (`grafana-admin-creds`) chứa mật khẩu mạnh, sau đó trỏ Grafana Helm Chart đọc từ Secret này qua thuộc tính `admin.existingSecret`.
   - **Local**: Khai báo rõ ràng file `.env` (nằm trong `.gitignore`) và nạp mật khẩu qua biến môi trường để tránh phụ thuộc ngầm định vào thư mục chạy lệnh docker-compose.

---

## 4. Hướng dẫn truy cập và quản lý mật khẩu (Runbook)

### Bước 1: Tạo Kubernetes Secret tĩnh trên EKS
*(Thực hiện trước khi deploy Helm)*
```bash
# Tạo secret chứa mật khẩu admin mạnh
kubectl create secret generic grafana-admin-creds \
  --from-literal=admin-password='<your-strong-password-here>' \
  -n techx-observability
```

### Bước 2: Đăng nhập và lấy mật khẩu (Khi cần thiết)
> [!WARNING]
> Profile AWS SSO mặc định `TF4-SecReliabilityReadOnlyAudit-511825856493` có quyền ReadOnlyAudit nên có thể bị EKS RBAC chặn truy cập đọc K8s Secret (báo lỗi `AccessDenied`). 
> Để chạy lệnh lấy mật khẩu dưới đây, người thực hiện cần đăng nhập bằng tài khoản có quyền Admin EKS (ví dụ: `tf4-cdo08-admin` hoặc tương đương).

```bash
# 1. Đăng nhập AWS SSO bằng tài khoản có quyền EKS Admin/Secret Reader
aws sso login --profile <eks-admin-profile>

# 2. Lấy mật khẩu admin tĩnh từ Kubernetes Secret
kubectl get secret -n techx-observability grafana-admin-creds -o jsonpath="{.data.admin-password}" | base64 --decode ; echo
```
*Dưới local: Mật khẩu admin được lưu trực tiếp trong file `.env` với biến `GRAFANA_ADMIN_PASSWORD`.*

---

## 5. Cổng phê duyệt (Approval Gate)
Trước khi sửa và deploy, phải có sự phê duyệt từ các bên liên quan:
- [ ] **Nhân** (Security Reviewer) duyệt phương án cấu hình `existingSecret` và phân quyền Viewer.
- [ ] **Quyết** (Owner) xác nhận Grafana hoạt động bình thường ở chế độ Viewer nặc danh.
- [ ] **Deploy Operator** xác nhận đã tạo secret `grafana-admin-creds` tĩnh trên EKS trước khi chạy deploy.

---

## 6. Hướng dẫn thực hiện (Implementation)

### File dự kiến thay đổi:
* [values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml)
* [grafana.ini](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/grafana/grafana.ini)
* [docker-compose.yml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/docker-compose.yml)
* [docker-compose.minimal.yml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/docker-compose.minimal.yml)
* [.env](file:///d:/xbrain/tf4-phase3-repo/.env) (Local - Gitignored)

### Chi tiết thay đổi:

#### 6.1. Helm Chart (`techx-corp-chart/values.yaml`)
Thay thế phần cấu hình Grafana (xóa `adminPassword: admin` và trỏ sang secret tĩnh):
```yaml
grafana:
  # ...
  grafana.ini:
    auth:
      disable_login_form: false  # Cho phép hiển thị login form
    auth.anonymous:
      enabled: true
      org_name: Main Org.
      org_role: Viewer           # Hạ quyền xuống Viewer
  
  # Cấu hình sử dụng Secret tĩnh thay vì sinh ngẫu nhiên hoặc hardcode
  admin:
    existingSecret: "grafana-admin-creds"
    passwordKey: "admin-password"
```

#### 6.2. Local Config (`techx-corp-platform/src/grafana/grafana.ini`)
```ini
[auth]
disable_login_form = false

[auth.anonymous]
enabled = true
org_role = Viewer
```

#### 6.3. Docker Compose (`docker-compose.yml` & `docker-compose.minimal.yml`)
Nạp file `.env` tường minh trong service `grafana`:
```yaml
  # Grafana
  grafana:
    # ...
    env_file:
      - .env
    environment:
      - "GF_INSTALL_PLUGINS=grafana-opensearch-datasource"
      - "GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}"
```

#### 6.4. File `.env` (Local - Gitignored)
```env
GRAFANA_ADMIN_PASSWORD=TechXSecurePass2026!
```

---

## 7. Xác minh bắt buộc (Verification)

```bash
# Trên EKS: Kiểm tra xem các pod Grafana đã chạy cấu hình mới chưa
kubectl -n techx-observability get pods -l app.kubernetes.io/name=grafana

# Kiểm tra quyền xem nặc danh thông qua API của home dashboard
curl -s -o /dev/null -w "%{http_code}" http://<alb-ingress-dns>/grafana/api/dashboards/home
```

### Điều kiện Pass:
- [ ] Lệnh curl API ẩn danh trả về mã code `401 Unauthorized` / `403 Forbidden` (bị từ chối xem do đổi quyền), hoặc trả về thành công `200 OK` nhưng khi parse JSON chứa `.meta.canEdit = false` (không có quyền chỉnh sửa).
- [ ] Truy cập trình duyệt ẩn danh: Giao diện hiển thị read-only (không có nút Save/Edit, không có biểu tượng Settings cấu hình ở menu bên trái).
- [ ] Nhấn nút **Log in**, đăng nhập bằng tài khoản `admin` và mật khẩu lấy từ Secret tĩnh -> Đăng nhập thành công và có đầy đủ quyền Admin.

---

## 8. Kế hoạch Rollback & An toàn (Rollback & Safety)
* **Quy trình chuẩn (GitOps compliant)**: Revert Git Commit chứa thay đổi cấu hình, push lên repository và để CI/CD pipeline tự động deploy trạng thái cũ lên EKS.
* **Trường hợp khẩn cấp (Emergency / Break-glass)**: Nếu pipeline bị lỗi hoặc cần khôi phục ngay lập tức:
  ```bash
  # Rollback nhanh bản release của observability về revision hoạt động ổn định trước đó
  helm rollback techx-observability <previous-revision> --namespace techx-observability --wait
  ```
  *Lưu ý: Sau khi rollback khẩn cấp bằng lệnh trên, bắt buộc phải sync và commit lại code trên Git để tránh việc deploy tiếp theo ghi đè cấu hình lỗi lên.*
  *Tuyệt đối không rollback về anonymous Admin trên các public route công khai.*

---

## 9. Definition of Done
- [ ] Anonymous user không còn quyền Admin (đã hạ về Viewer).
- [ ] Default admin password không còn là `admin` và không bị hardcode trong source code.
- [ ] Đã xác minh có thể đăng nhập bằng tài khoản admin với mật khẩu tự sinh từ Kubernetes Secret.
- [ ] Đính kèm bằng chứng xác minh (commands output/screenshots) vào Jira.
- [ ] Owner (Quyết) và PM xác nhận hoàn thành, chuyển trạng thái task sang **Done**.

---

## 10. Evidence cần đính kèm Jira
1. **Before:** Ảnh chụp màn hình khi truy cập `/grafana` nặc danh thấy có đầy đủ menu Admin/Settings.
2. **Change:** Link pull request chứa các file cấu hình đã xóa password hardcode và hạ quyền anonymous.
3. **After:** Ảnh chụp màn hình khi truy cập nặc danh (chỉ có Viewer) và sau khi đăng nhập admin (có đầy đủ quyền Admin).
4. **Secret check:** Command output tạo secret tĩnh thành công trên namespace `techx-observability`.
