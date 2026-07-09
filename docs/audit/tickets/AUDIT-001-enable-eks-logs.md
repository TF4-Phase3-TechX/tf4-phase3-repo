# [AUDIT-001] Bật EKS Control-Plane Audit Logging (CloudWatch)

**Trạng thái**: DONE
**Người yêu cầu (Reporter)**: Nhóm CDO07 (Audit)
**Người thực hiện (Assignee)**: Nhóm CDO04 (Đại diện: Huy Hoàng - Owner của EKS module)
**Độ ưu tiên (Priority)**: P0 (Blocker cho công tác kiểm toán)
**Epic**: EPIC-05 (Security & Auditability)

---

## 1. Bối cảnh (Context)
Trong quá trình kiểm toán hạ tầng EKS hiện tại (file `infra/terraform/eks.tf` thuộc sở hữu của CDO04), team CDO07 (Audit) phát hiện cụm EKS `techx-general-ng` chưa được bật tính năng Control-Plane Logging. 
Việc thiếu log Audit của Kubernetes khiến team không thể truy vết được các hành động (API calls) từ user hoặc pod vào Control Plane (ví dụ: ai đã chạy lệnh `kubectl delete pod`, ai đã đọc Secret). Điều này vi phạm nghiêm trọng yêu cầu truy vết của Audit.

## 2. Yêu cầu cấu hình (The What)
Team CDO04 vui lòng cập nhật Terraform module của EKS để bật tính năng đẩy log lên Amazon CloudWatch. 
Các loại log bắt buộc phải bật bao gồm:
- `api`
- `audit`
- `authenticator`

*Tùy chọn (Nice to have): `controllerManager`, `scheduler` (nếu không tốn quá nhiều chi phí).*

## 3. Hướng dẫn triển khai (The How - Gợi ý cho CDO04)
Sửa file `infra/terraform/eks.tf`, thêm thuộc tính `cluster_enabled_log_types` vào block `module "eks"`:

```hcl
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  # ... các config cũ giữ nguyên ...

  # Bật Control Plane Logging
  cluster_enabled_log_types = ["api", "audit", "authenticator"]
  
  # ...
}
```

## 4. Tiêu chí nghiệm thu (Acceptance Criteria / Evidence)
- [x] Code Terraform (PR) đã merge có chứa cấu hình `cluster_enabled_log_types`.
- [x] Trên giao diện AWS CloudWatch Logs, xuất hiện Log Group có định dạng `/aws/eks/<cluster-name>/cluster`.
- [x] Log stream có dữ liệu thực tế đẩy về.

*(Sau khi hoàn thành, vui lòng tag @Member6-CloudWatchTracker của team CDO07 để vào CloudWatch nghiệm thu chéo).*

## 5. Ước tính chi phí (Cost Estimation)
Việc bật Control Plane Logging (gửi log về CloudWatch) sẽ phát sinh chi phí dựa trên dung lượng log (Data Ingestion & Storage) của AWS CloudWatch Logs:
- **Data Ingestion**: ~$0.50 / GB.
- **Storage**: ~$0.03 / GB / tháng.

**Ước tính (tham khảo cho cụm `techx-general-ng`)**:
- Với 3 loại log `api`, `audit`, `authenticator`: Dung lượng trung bình cho cụm nhỏ/vừa khoảng 2 GB - 5 GB / tháng.
- Chi phí dự kiến: **~$1.00 - $2.50 / tháng**.
- *(Lưu ý: Nếu bật thêm các tuỳ chọn `controllerManager` và `scheduler`, lượng log sẽ sinh ra nhiều hơn đáng kể, ước tính có thể tăng lên $5.00 - $10.00/tháng, do đó hiện tại chúng ta chỉ bật các loại bắt buộc).*
