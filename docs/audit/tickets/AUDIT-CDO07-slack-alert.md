---
title: "Tự động hóa việc phân phối Slack Webhook URLs cho hệ thống K8s Alertmanager và AWS Security Alerts"
type: Enhancement / Security
priority: High
requester: CDO07 (Bùi Thành Nghĩa)
status: Done
---

# 🎟️ Ticket: Automate Slack Webhooks Injection via GitHub Actions and External Secrets

## 1. Yêu cầu từ người dùng (User Request)
Theo yêu cầu trực tiếp từ tôi (người dùng / kỹ sư vận hành), quy trình thiết lập Webhook URL cho hệ thống cảnh báo hiện tại đang phụ thuộc vào thao tác thủ công (manual CLI commands). Yêu cầu đặt ra là phải **tự động hóa hoàn toàn quy trình này**:
- Chỉ cần khai báo `ALERTMANAGER_SLACK_WEBHOOK` và `SECURITY_SLACK_WEBHOOK` trên giao diện **GitHub Secrets**.
- Hệ thống CI/CD phải tự động đọc và phân phối các secret này xuống cả hạ tầng AWS và cụm Kubernetes mà **không được phép làm lộ Webhook trong Terraform State**.

## 2. Bối cảnh (Background)
Hệ thống giám sát chia làm 2 kênh cảnh báo trên Slack:
1. **Kênh Ops/SLO Alerts:** Dùng Kubernetes Alertmanager để cảnh báo về trạng thái của các dịch vụ (ví dụ: Checkout/Cart/Browse Success Rate).
2. **Kênh Security Alerts:** Dùng AWS EventBridge + Lambda để phát hiện và cảnh báo các hành vi can thiệp hạ tầng trái phép.

Các Webhook URL của Slack là thông tin nhạy cảm. Việc bắt buộc người vận hành phải chạy lệnh khởi tạo `kubectl create secret...` hay `aws ssm put-parameter...` bằng tay mỗi khi dựng môi trường mới đi ngược lại triết lý GitOps và CI/CD hoàn toàn tự động.

## 3. Chi tiết thực hiện (Implementation Details)

Dựa trên yêu cầu, 2 thay đổi kiến trúc sau đã được áp dụng:

### Thay đổi 1: Bổ sung luồng đồng bộ Secret trong CI/CD (`.github/workflows/terraform-apply.yaml`)
- **Vấn đề:** Không thể truyền Secret thẳng vào biến của Terraform vì sẽ làm lộ giá trị Webhook trong file State.
- **Giải pháp:** Đã cấu hình thêm một bước chạy script AWS CLI ngay sau bước chứng thực IAM trong GitHub Actions. Hệ thống sẽ tự động cập nhật Webhook vào AWS.

**Mã nguồn đề xuất (Code Changes):**
```yaml
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_GITHUB_ACTIONS_TERRAFORM_APPLY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

+     - name: Sync Slack Webhooks to AWS
+       env:
+         ALERTMANAGER_SLACK_WEBHOOK: ${{ secrets.ALERTMANAGER_SLACK_WEBHOOK }}
+         SECURITY_SLACK_WEBHOOK: ${{ secrets.SECURITY_SLACK_WEBHOOK }}
+       run: |
+         set -euo pipefail
+         if [[ -n "${ALERTMANAGER_SLACK_WEBHOOK:-}" ]]; then
+           echo "Updating Alertmanager Webhook in Secrets Manager..."
+           aws secretsmanager put-secret-value --secret-id techx/tf4/alertmanager-slack-webhook --secret-string "$ALERTMANAGER_SLACK_WEBHOOK" || \
+           aws secretsmanager create-secret --name techx/tf4/alertmanager-slack-webhook --secret-string "$ALERTMANAGER_SLACK_WEBHOOK"
+         fi
+         if [[ -n "${SECURITY_SLACK_WEBHOOK:-}" ]]; then
+           echo "Updating Security Alerts Webhook in SSM..."
+           aws ssm put-parameter --name "/security-alerts/slack-webhook-url" --type "SecureString" --value "$SECURITY_SLACK_WEBHOOK" --overwrite
+         fi
```

### Thay đổi 2: Khai báo External Secret cho Alertmanager (`techx-corp-chart/templates/external-secrets.yaml`)
- **Vấn đề:** Alertmanager nằm trong Kubernetes không thể tự nhiên đọc được Secret nằm trên AWS Secrets Manager.
- **Giải pháp:** Đã tạo tài nguyên `ExternalSecret`. Thành phần External Secrets Operator (ESO) của cụm sẽ giám sát file này, tự động kết nối với AWS để kéo Webhook URL về và sinh ra một `Secret` chuẩn của K8s. Cuối cùng, `values.yaml` của Alertmanager được cấu hình dùng tính năng `extraSecretMounts` trỏ file `api_url_file` vào đúng Secret đó.

**Mã nguồn đề xuất (Code Changes):**
```yaml
{{- if .Values.prometheus.enabled -}}
{{- if .Values.prometheus.alertmanager.enabled -}}
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: alertmanager-slack-webhook
  namespace: {{ .Release.Namespace }}
  labels:
    app.kubernetes.io/component: alertmanager
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: aws-secretsmanager
    kind: ClusterSecretStore
  target:
    name: alertmanager-slack-webhook
    creationPolicy: Owner
  data:
    - secretKey: webhook-url
      remoteRef:
        key: techx/tf4/alertmanager-slack-webhook
{{- end }}
{{- end }}
```

## 4. Kết quả nghiệm thu (Acceptance Criteria)
- [x] Không còn thao tác thủ công khi thiết lập môi trường mới.
- [x] Webhook của Slack không bị lộ trong Terraform State.
- [x] Chỉ cần khai báo biến trong GitHub Secrets, sau khi merge/push, hệ thống tự động hoàn tất luồng kết nối cho cả K8s và AWS.
