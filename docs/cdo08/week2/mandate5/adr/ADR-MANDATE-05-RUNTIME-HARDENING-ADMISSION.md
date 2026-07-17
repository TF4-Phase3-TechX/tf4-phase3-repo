# ADR: Mandate 5 Runtime Hardening Admission Control

## Status
**ACCEPTED**

## Context
Mandate 5 yêu cầu triển khai các biện pháp bảo mật runtime cứng rắn (runtime hardening). Việc này không chỉ dừng lại ở danh sách kiểm tra thủ công (checklists), mà phải có một cơ chế kiểm soát truy cập (Admission Control) để tự động phát hiện, cảnh báo hoặc từ chối trực tiếp các manifest vi phạm trước khi chúng được đưa vào vận hành trên cluster.

## Decision
Team CDO-08 quyết định sử dụng cơ chế **Kubernetes ValidatingAdmissionPolicy (VAP)** để áp dụng chính sách bảo mật dạng Policy-as-Code.

### Vì sao chọn cách này?
1. **Kubernetes Native:** VAP là tính năng gốc được tích hợp sẵn từ Kubernetes v1.26+ (GA/Stable từ v1.30). Do cụm EKS hiện tại chạy phiên bản **v1.34**, tính năng này khả dụng ngay lập tức mà không cần chỉnh sửa cấu hình API Server.
2. **Không cần cài đặt thêm bên thứ ba:** Tránh việc phải cài đặt, quản trị và vận hành các Controller bổ sung như Kyverno hay Gatekeeper (OPA). Điều này giúp:
   - Giảm thiểu tài nguyên cluster tiêu thụ cho các webhook pods.
   - Loại bỏ rủi ro về mặt vận hành khi các webhook Controller này bị sập hoặc nghẽn (Single Point of Failure).
3. **Độ trễ thấp (Minimal Latency):** Nhờ cơ chế đánh giá ngôn ngữ CEL (Common Expression Language) trực tiếp trên API Server, VAP xử lý nhanh hơn nhiều so với việc gọi các Webhook HTTP bên ngoài.
4. **Đủ năng lực đáp ứng:** Các luật cơ bản của Mandate 5 hoàn toàn có thể biểu diễn tường minh qua cú pháp CEL.

## Scope
Chính sách được áp dụng theo phạm vi (Namespace-scoped):
* **Namespace trong scope:** `techx-tf4` và `techx-observability`.
* **Cơ chế kích hoạt:** Ràng buộc (Binding) chỉ áp dụng lên các Namespace có nhãn `techx.io/policy-scope=enforced`.
* **Lý do giới hạn:** Tránh áp dụng toàn cluster (Cluster-wide) khi chưa có sự thảo luận và đánh giá mức độ tương thích đối với workloads của các team khác, ngăn ngừa gián đoạn hệ thống không mong muốn.

## Rules Enforced (Deny Mode)
Tất cả 4 chính sách bảo mật sau đây đều được triển khai trực tiếp ở chế độ **Deny** (từ chối manifest vi phạm):

1. **Cấm chạy root / Yêu cầu runAsNonRoot (`require-run-as-nonroot`):**
   - Ràng buộc mọi container và init container phải cấu hình `runAsNonRoot: true` (hoặc kế thừa từ pod-level securityContext).
2. **Yêu cầu loại bỏ toàn bộ Linux kernel capabilities (`require-drop-all-capabilities`):**
   - Bắt buộc các container và init container phải khai báo `capabilities.drop: ["ALL"]`. Chỉ cho phép thêm lại các capability cụ thể thực sự cần thiết.
3. **Cấm sử dụng image latest hoặc untagged (`disallow-mutable-image-tag`):**
   - Loại bỏ hoàn toàn việc sử dụng tag `:latest`, các image không có tag, hoặc image sử dụng tag thay đổi liên tục. Bắt buộc ghim phiên bản cụ thể hoặc digest (`sha256`).
4. **Bắt buộc cấu hình Resource requests và limits (`require-resource-limits`):**
   - Yêu cầu tất cả container và init container phải xác định rõ ràng CPU/Memory requests & limits nhằm tránh tình trạng cạn kiệt tài nguyên node (Resource Starvation).

> [!NOTE]
> Hiện tại, không có rule nào chạy ở chế độ chỉ giám sát (Audit mode). Toàn bộ 4 quy tắc nêu trên đều được áp dụng cứng rắn ở chế độ chặn (`Deny`).

## Rollback & Safety Plan

### Cơ chế Rollback nhanh
Nếu một chính sách bảo mật Admission chặn nhầm (False Positive) các deploy khẩn cấp của hệ thống, chúng tôi áp dụng quy trình xử lý khẩn cấp sau:
1. Sửa tệp cấu hình GitOps `techx-corp-chart/templates/admission-hardening.yaml` (hoặc override Helm values) để chuyển đổi `validationActions` từ `[Deny]` sang `[Warn]` đối với Binding tương ứng.
2. Thực hiện commit và đẩy lên repo Git để Argo CD tự động đồng bộ hóa cấu hình mới xuống cluster.
3. Trong trường hợp khẩn cấp cấp độ P0 mà hệ thống GitOps bị nghẽn, Operator có quyền truy cập quản trị được phép chỉnh sửa trực tiếp tài nguyên `ValidatingAdmissionPolicyBinding` trên cluster bằng lệnh `kubectl patch`.

### Phê duyệt Rollback
* Mọi hành động chuyển đổi chế độ của chính sách Admission phải được xem xét và đồng ý bởi **Lead Security/Reliability (CDO-08)** và **Lead Platform/Ops (CDO-04)**.

### Kiểm tra sau Rollback (Verification)
1. Thực hiện lệnh `kubectl apply --server-side --dry-run=server` trên manifest bị lỗi trước đó để xác nhận API Server chỉ trả về cảnh báo (Warning) thay vì lỗi từ chối (Forbidden).
2. Tiến hành deploy workloads bình thường và giám sát trạng thái Pod qua Prometheus/Grafana.
