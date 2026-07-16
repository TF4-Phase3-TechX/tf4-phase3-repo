# Báo cáo Chi tiết Kỹ thuật Kết quả Công việc Tuần 2 — CDO-08 (Quyết)

*   **Owner cột trụ:** Security / SSO / IAM / EKS Access Control (CDO-08)
*   **Dự án:** TF4 Phase 3
*   **Thời gian lập báo cáo:** 16/07/2026

Báo cáo này cung cấp thuyết minh kỹ thuật chi tiết nhất về ba mảng công việc lớn: **Mandate 05 (Bảo mật Runtime)**, **Mandate 01 (Hạn chế Phơi nhiễm Mạng)**, và **Cấu hình Phân quyền Hạ tầng EKS/AWS (Cross-Team Enablement cho AI và Cost/Perf)**.

---

## 1. MANDATE 05 — RUNTIME HARDENING (BẢO MẬT THỜI GIAN CHẠY)

### 1.1. Bối cảnh và Ràng buộc
Mentor yêu cầu cluster EKS phải có cơ chế ngăn chặn việc triển khai các cấu hình vi phạm an ninh (chạy quyền root, không drop Linux capabilities, dùng tag `:latest` trôi nổi, hoặc thiếu giới hạn tài nguyên CPU/Memory). 
**Ràng buộc nghiêm ngặt:** Không được gây gián đoạn các pod đang chạy bình thường trên Production và không làm sập chỉ số SLO (Service Level Objective) của dự án khi siết chính sách.

### 1.2. Giải pháp Kỹ thuật: Kubernetes Native ValidatingAdmissionPolicy
Thay vì sử dụng các công cụ webhook bên thứ ba (như Kyverno hay Gatekeeper) vốn làm tăng độ trễ mạng và tăng điểm lỗi hệ thống (single point of failure), chúng tôi triển khai tính năng **ValidatingAdmissionPolicy** có sẵn từ Kubernetes 1.30+ (cluster hiện tại chạy EKS 1.34). Cơ chế này chạy trực tiếp trên API Server, sử dụng ngôn ngữ CEL (Common Expression Language) để đạt tốc độ xử lý tối ưu.

Chúng tôi cấu hình 3 bộ chính sách chính trong tệp [policies.yaml](file:///d:/xbrain/tf4-phase3-repo/deploy/admission/policies.yaml):

#### 1) Chính sách Non-Root & Capabilities (`harden-non-root-and-capabilities`)
Ép buộc tất cả các container (kể cả container chính, initContainers và ephemeralContainers) phải chạy ở chế độ non-root và drop toàn bộ đặc quyền hệ điều hành.
*   **Biến số gom nhóm (Variables):**
    ```yaml
    - name: allContainers
      expression: "object.spec.containers + object.spec.?initContainers.orValue([]) + object.spec.?ephemeralContainers.orValue([])"
    ```
*   **Biểu thức CEL kiểm tra Non-Root:**
    ```cel
    variables.allContainers.all(c,
      (has(c.securityContext) && has(c.securityContext.runAsNonRoot) && c.securityContext.runAsNonRoot == true) ||
      (!(has(c.securityContext) && has(c.securityContext.runAsNonRoot)) && has(object.spec.securityContext) && has(object.spec.securityContext.runAsNonRoot) && object.spec.securityContext.runAsNonRoot == true)
    )
    ```
    *Ý nghĩa:* Mọi container phải định nghĩa `runAsNonRoot: true` trong `securityContext` riêng của nó, hoặc nếu không định nghĩa thì pod-level `securityContext` phải có `runAsNonRoot: true` để kế thừa.
*   **Biểu thức CEL kiểm tra Capabilities Drop:**
    ```cel
    variables.allContainers.all(c,
      has(c.securityContext) &&
      has(c.securityContext.capabilities) &&
      has(c.securityContext.capabilities.drop) &&
      c.securityContext.capabilities.drop.exists(d, d.upperAscii() == 'ALL')
    )
    ```
    *Ý nghĩa:* Mọi container bắt buộc phải định nghĩa rõ ràng việc drop toàn bộ đặc quyền (`ALL`) để tránh việc tin tặc khai thác lỗ hổng thoát container (container escape) chiếm quyền node.

#### 2) Chính sách Khóa cứng Image Tag (`harden-image-tags`)
Chặn đứng việc sử dụng tag `:latest` hoặc không chỉ định tag nhằm đảm bảo tính bất biến (immutability) của ảnh deploy.
*   **Biểu thức CEL kiểm tra:**
    ```cel
    variables.allContainers.all(c,
      c.image.contains('@sha256:') ||
      (c.image.matches(r'^([^/]+/)*[^/:@]+:[^/:@]+$') && !c.image.endsWith(':latest'))
    )
    ```
    *Ý nghĩa:* Chỉ chấp nhận các image được ghim rõ tag cụ thể (không chứa đuôi `:latest`) hoặc sử dụng định danh băm SHA256 chính xác (`@sha256:`).

#### 3) Chính sách Ép buộc Khai báo Tài nguyên (`harden-resource-constraints`)
Ngăn chặn hiện tượng "noisy neighbor" (một container chiếm dụng hết tài nguyên node làm sập các container khác).
*   **Biểu thức CEL kiểm tra:**
    ```cel
    variables.allContainers.all(c,
      has(c.resources) &&
      has(c.resources.requests) &&
      has(c.resources.requests.cpu) &&
      has(c.resources.requests.memory) &&
      has(c.resources.limits) &&
      has(c.resources.limits.cpu) &&
      has(c.resources.limits.memory)
    )
    ```
    *Ý nghĩa:* Buộc nhà phát triển phải khai báo đầy đủ cả `requests` và `limits` đối với cả CPU và Memory.

---

### 1.3. Cơ chế Triển khai An toàn (Warn vs Deny)
Để bảo vệ SLO dịch vụ trên Production, trong tệp [bindings.yaml](file:///d:/xbrain/tf4-phase3-repo/deploy/admission/bindings.yaml), chúng tôi thiết lập phân tách:

*   **Namespace Test (`techx-admission-test`):** Gắn các chính sách với `validationActions: ["Deny"]`. Mọi deploy vi phạm sẽ bị API Server từ chối ngay lập tức kèm mã lỗi Forbidden.
*   **Namespace Production (`techx-tf4`):** Gắn các chính sách với `validationActions: ["Warn"]`. Các deploy vi phạm vẫn được chấp nhận để đảm bảo ứng dụng chạy bình thường, nhưng Kubernetes sẽ gửi lại cảnh báo Warning trên terminal cho operator và ghi nhận vào audit log để team có kế hoạch sửa đổi.

---

### 1.4. Bằng chứng thực nghiệm Chặn lỗi trên EKS (Evidence)
Khi thực hiện chạy thử (dry-run server-side) các manifest vi phạm quy chuẩn lên namespace test, EKS API Server đã trả về mã lỗi chặn chính xác theo CEL thiết kế:

#### 1) Bằng chứng chặn lỗi chạy Root
*   **Lệnh test:** `kubectl apply --server-side --dry-run=server -n techx-admission-test -f deploy/admission/violation-root.yaml`
*   **Kết quả chặn thực tế:**
    ```text
    Error from server (Forbidden): error when creating "deploy/admission/violation-root.yaml": pods "root-violation" is forbidden: ValidatingAdmissionPolicy 'harden-non-root-and-capabilities' with binding 'harden-non-root-binding-test' denied request: All containers (and initContainers) must set securityContext.runAsNonRoot to true (or inherit it from pod-level securityContext).
    ```

#### 2) Bằng chứng chặn lỗi tag Latest
*   **Lệnh test:** `kubectl apply --server-side --dry-run=server -n techx-admission-test -f deploy/admission/violation-latest.yaml`
*   **Kết quả chặn thực tế:**
    ```text
    Error from server (Forbidden): error when creating "deploy/admission/violation-latest.yaml": pods "latest-violation" is forbidden: ValidatingAdmissionPolicy 'harden-image-tags' with binding 'harden-image-tags-binding-test' denied request: Container images must be pinned to a specific tag (not 'latest') or a digest (@sha256:...).
    ```

#### 3) Bằng chứng chặn lỗi thiếu Limit tài nguyên
*   **Lệnh test:** `kubectl apply --server-side --dry-run=server -n techx-admission-test -f deploy/admission/violation-resources.yaml`
*   **Kết quả chặn thực tế:**
    ```text
    Error from server (Forbidden): error when creating "deploy/admission/violation-resources.yaml": pods "resources-violation" is forbidden: ValidatingAdmissionPolicy 'harden-resource-constraints' with binding 'harden-resources-binding-test' denied request: All containers must define CPU and Memory resource requests and limits.
    ```

---
---

## 2. MANDATE 01 — NETWORK EXPOSURE (HẠN CHẾ PHƠI NHIỄM MẠNG)

### 2.1. Bối cảnh và Rủi ro an ninh
Việc phơi bày các trang quản trị (Grafana, Jaeger, Prometheus) và portal kiểm thử tải (Locust) ra ngoài Internet qua các Ingress public sẽ mở rộng bề mặt tấn công. Tin tặc có thể quét cổng để dò tìm mật khẩu yếu, tấn công DDoS hoặc khai thác lỗ hổng zero-day trực tiếp để kiểm soát cluster.

### 2.2. Giải pháp Kỹ thuật: Hệ thống Operational Portals Cô lập (Private Only)
Chúng tôi thực hiện đóng hoàn toàn các Route Ingress công cộng. Người vận hành chỉ có thể truy cập thông qua mô hình kết nối private an toàn:

```text
[Máy Operator Local]
        │ (HTTPS - AWS SSO authenticated session)
        ▼
[AWS Systems Manager (SSM) Session Manager]
        │ (Mã hóa SSL qua AWS Backbone)
        ▼
[EC2 Bastion Host] (Nằm trong Private Subnet, không mở cổng SSH inbound, không IP public)
        │ (kubectl port-forward nội bộ)
        ▼
[EKS Cluster Services] (Grafana: 3000 / Jaeger: 16686 / Locust: 8089)
```

### 2.3. Quy trình thiết lập kết nối SSM Tunnel
Khi cần truy cập, người vận hành thực hiện các bước sau trên máy local:

1.  **Xác thực danh tính AWS SSO:**
    ```powershell
    aws sts get-caller-identity --profile TF4-SecurityIAMSSOManager-511825856493
    ```
2.  **Kiểm tra trạng thái EC2 Bastion Host:**
    ```powershell
    aws ssm get-connection-status --target <BASTION_INSTANCE_ID> --region us-east-1 --profile TF4-SecurityIAMSSOManager-511825856493
    ```
3.  **Khởi tạo Session Port-Forwarding thông qua SSM Document:**
    ```powershell
    aws ssm start-session `
      --target <BASTION_INSTANCE_ID> `
      --document-name AWS-StartPortForwardingSession `
      --parameters '{"portNumber":["8089"],"localPortNumber":["18089"]}' `
      --region us-east-1 `
      --profile TF4-SecurityIAMSSOManager-511825856493
    ```
    *Ý nghĩa:* Lệnh này ánh xạ cổng `8089` (Locust) của Bastion Host về cổng `18089` trên máy local của người dùng một cách an toàn thông qua đường truyền mã hóa của AWS.
4.  **Chạy port-forward dịch vụ trên Bastion:**
    Sau khi đã ssh-tunnel vào Bastion, người dùng chạy lệnh chuyển tiếp dịch vụ Kubernetes:
    ```bash
    kubectl port-forward service/load-generator -n techx-tf4 8089:8089
    ```
    Lúc này, operator có thể truy cập an toàn qua trình duyệt local tại địa chỉ `http://localhost:18089`.

*Tài liệu runbook chi tiết:* [docs/cdo08/week2/CDO08-SEC-05-INGRESS-HARDENING-RUNBOOK.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/CDO08-SEC-05-INGRESS-HARDENING-RUNBOOK.md)

---
---

## 3. CƠ CHẾ PHÂN QUYỀN HẠ TẦNG (CROSS-TEAM ENABLEMENT)

Nhằm tháo gỡ blocker kỹ thuật cho các đội bạn nhưng vẫn đảm bảo tính an ninh, tối thiểu quyền hạn (least-privilege).

### 3.1. Hỗ trợ Đội AI (Mandate 06 — Bedrock Cross-Account Role Chaining)
*   **Vấn đề:** Tài khoản sản xuất chính `511825856493` bị khóa quota Bedrock Nova 2 Lite (TPM/RPM = 0), đội AI cần chuyển luồng gọi API Bedrock khẩn cấp sang tài khoản phụ `589077667575` đang có quota hoạt động.
*   **Giải pháp phân quyền an toàn:** Thiết lập STS Role Chaining thông qua EKS Pod Identity mà không sử dụng Access Key tĩnh.

#### 1) Cấu hình EKS Pod Identity Association
Chúng tôi cập nhật trường `targetRoleArn` của Pod Identity Association `a-iuw7np6l5niq1k2zt` để EKS tự động cấu hình STS token cho Pod:
*   *Lệnh thực hiện:*
    ```bash
    aws eks update-pod-identity-association `
      --cluster-name techx-tf4-cluster `
      --association-id a-iuw7np6l5niq1k2zt `
      --target-role-arn arn:aws:iam::589077667575:role/tf4-product-reviews-bedrock-emergency-target `
      --region us-east-1 `
      --profile TF4-SecurityIAMSSOManager-511825856493
    ```

#### 2) Cập nhật IAM Policy nguồn (Account 511)
Nâng cấp chính sách `tf4-product-reviews-bedrock-policy` lên phiên bản **`v3`**, bổ sung quyền `AssumeRole` và `TagSession` để cho phép Pod chuyển tiếp token định danh:
```json
{
  "Sid": "AllowCrossAccountAssumeRoleEmergency",
  "Effect": "Allow",
  "Action": [
    "sts:AssumeRole",
    "sts:TagSession"
  ],
  "Resource": "arn:aws:iam::589077667575:role/tf4-product-reviews-bedrock-emergency-target"
}
```

#### 3) Ràng buộc Trust Policy tại Target Role (Account 589)
Để đảm bảo an toàn, Trust Policy trên Target Role ở account phụ chỉ tin tưởng duy nhất Source Role từ account EKS và khóa cứng các session tags đặc trưng của EKS Pod Identity:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::511825856493:role/tf4-product-reviews-bedrock"
      },
      "Action": [
        "sts:AssumeRole",
        "sts:TagSession"
      ],
      "Condition": {
        "StringEquals": {
          "aws:PrincipalTag/kubernetes.io/namespace": "techx-tf4",
          "aws:PrincipalTag/kubernetes.io/serviceaccount": "product-reviews-bedrock",
          "aws:PrincipalTag/eks-pod-identity/cluster-arn": "arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster"
        }
      }
    }
  ]
}
```

#### 4) Kết quả chạy Preflight Job (PASS)
Đã chạy thử Job kiểm tra kết nối Bedrock khẩn cấp. Sử dụng lệnh thực thi chính xác thông qua virtualenv của Container (`/venv/bin/python`) để nạp thư viện `boto3`. 
*   *Kết quả logs trả về:*
    ```json
    {"result": "PASS", "account": "589077667575", "role": "tf4-product-reviews-bedrock-emergency-target", "model_id": "us.amazon.nova-2-lite-v1:0", "guardrail_id": "e2svpiawj1v5", "guardrail_version": "3", "latency_ms": 1203.4, "input_tokens": 51, "output_tokens": 3}
    ```
    *Ý nghĩa:* Xác nhận luồng kết nối cross-account an toàn tuyệt đối và hoạt động hoàn hảo.
*   *Tài liệu liên quan:* [docs/cdo08/week2/CDO08-AIO-cross-account-bedrock-approval.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/CDO08-AIO-cross-account-bedrock-approval.md)

#### 5) Quy trình thu hồi quyền (Rollback - Đã hoàn tất)
*   **Thu hồi EKS Pod Identity:** Xóa association cũ và tạo lại association mới (`a-ytlbepsjqae4uvmr7`) trỏ trực tiếp về local role (không có `targetRoleArn` của tài khoản phụ 589).
*   **Merge Rollback PR #16:** Revert cấu hình Guardrail trong GitOps về `wckqh9dms6qa:1` đồng bộ với identity của account 511.

---

### 3.2. Hỗ trợ Đội Tối ưu Hiệu năng (Mandate 04 / D5-PERF-06)
*   **Vấn đề:** Đội hiệu năng (CDO-04) bị kẹt lỗi Helm không đọc được Role `loadgen-portforward` để đối chiếu, đồng thời họ thiếu quyền mở tunnel test và restart frontend.
*   **Hành động đã triển khai:**
    Chúng tôi đã bổ sung cấu hình quyền hạn chế cho group `cost-perf-readonly-alerting-users` trong file template gốc [team-rbac.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/templates/team-rbac.yaml) và đã apply trực tiếp lên EKS cluster:

#### 1) Giải quyết lỗi Helm:
Cấp quyền đọc (`get`, `list`, `watch`) đối với `roles` và `rolebindings` tại namespace `techx-tf4`:
```yaml
- apiGroups: ["rbac.authorization.k8s.io"]
  resources: ["roles", "rolebindings"]
  verbs: ["get", "list", "watch"]
```

#### 2) Cấp quyền mở port-forward private:
Cho phép ghim cổng dịch vụ để mở Locust/Grafana mà không công khai ra Internet:
```yaml
- apiGroups: [""]
  resources: ["services/proxy"]
  verbs: ["get"]
- apiGroups: [""]
  resources: ["pods/portforward"]
  verbs: ["create"]
```

#### 3) Cấp quyền dry-run chính sách bảo mật:
Cấp quyền tạo pod tạm thời để chạy apply dry-run trên namespace test:
```yaml
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["create"] # Duy nhất trên namespace techx-admission-test
```

#### 4) Cấp quyền kiểm thử tải (Frontend restart):
Cấp quyền `patch` duy nhất cho Deployment mang tên `frontend` tại namespace `techx-tf4`:
```yaml
- apiGroups: ["apps"]
  resources: ["deployments"]
  resourceNames: ["frontend"]
  verbs: ["get", "patch"]
```
*Ý nghĩa:* Operator chỉ có thể khởi động lại frontend bằng lệnh `kubectl rollout restart deployment/frontend`, API Server sẽ từ chối ngay lập tức nếu họ cố tình can thiệp vào các dịch vụ lõi như `checkout` hay `payment`.

---

### 3.3. Tắt Anonymous Admin và Khóa mật khẩu Grafana (CDO08-SEC-02)
*   **Vấn đề:** Mặc định Grafana bật truy cập anonymous với quyền `Admin` và sử dụng mật khẩu admin mặc định `admin` bị hardcode, dẫn đến nguy cơ lỗ hổng kiểm soát Dashboard/Datasource khi observability portal được mở.
*   **Hành động đã triển khai:**
    1.  **Hạ quyền Anonymous:** Cấu hình hạ quyền anonymous user từ `Admin` xuống `Viewer` và cho phép hiển thị màn hình Login form (`disable_login_form: false`) trong [values.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/values.yaml) và [grafana.ini](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/grafana/grafana.ini).
    2.  **Khóa mật khẩu tĩnh trên EKS:** Tạo trước Kubernetes Secret tĩnh `grafana-admin-creds` trên namespace `techx-observability` chứa mật khẩu admin mạnh (`techx-grafana-secure-2026!`). Cấu hình Helm Chart sử dụng Secret này qua thuộc tính `admin.existingSecret` thay vì hardcode password.
    3.  **Harden môi trường Local:** Tích hợp file `.env` chứa biến `GRAFANA_ADMIN_PASSWORD` vào các file docker-compose để chạy an toàn dưới local mà không bị commit mật khẩu lên Git.
    4.  **Tài liệu kế hoạch khắc phục:** Bổ sung file tài liệu kế hoạch chi tiết tại [cdo08-sec-02-grafana-security-remediation-plan.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/cdo08-sec-02-grafana-security-remediation-plan.md).
*   **Trạng thái:** Đã hoàn tất đẩy đủ mã nguồn và cấu hình lên nhánh `feat/cdo08-runtime-hardening`.

*Tài liệu liên quan:* [docs/cdo08/week2/CDO08-CDO04-controlled-rollout-access-approval.md](file:///d:/xbrain/tf4-phase3-repo/docs/cdo08/week2/CDO08-CDO04-controlled-rollout-access-approval.md)

