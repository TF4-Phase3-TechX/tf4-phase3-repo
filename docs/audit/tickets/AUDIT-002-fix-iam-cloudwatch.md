# [AUDIT-002] [Bug] Thiếu quyền Read-Only (CloudWatch, NetworkFlowMonitor) cho nhóm Audit CDO07

**Trạng thái**: TO DO
**Người yêu cầu (Reporter)**: Nhóm CDO07 (Audit)
**Người thực hiện (Assignee)**: Nhóm CDO08 (Admin SSO)
**Độ ưu tiên (Priority)**: P0 (Blocker thao tác nghiệm thu của Audit)

## 1. Mô tả lỗi
Thành viên team CDO07 (ví dụ: user `ty.dinh`) báo cáo gặp lỗi "Access Denied" (không có quyền) khi cố gắng truy cập các giao diện giám sát để nghiệm thu log và cảnh báo.
Cụ thể hệ thống AWS báo thiếu các quyền sau:
- `cloudwatch:DescribeAlarms`
- `cloudwatch:ListDashboards`
- `cloudwatch:ListMetrics`
- `networkflowmonitor:ListScopes`

## 2. Nguyên nhân
Theo bản thiết kế "TF4 AWS Identity Center Groups & Permission Sets" (phần `4.1 Shared Permission Set: TF4-BaseReadOnly`), nhóm Audit được hứa hẹn cung cấp tầm nhìn toàn diện nền tảng thông qua các quyền `cloudwatch:Describe*`, `cloudwatch:List*`, v.v.
Tuy nhiên, cấu hình thực tế trên AWS IAM Identity Center (SSO) đang bị sót hoặc chưa gán đúng policy `TF4-BaseReadOnly` cho nhóm CDO07. Đồng thời, công cụ Network Flow Monitor trên console cũng yêu cầu quyền `ListScopes` để hiển thị dữ liệu lưu lượng mạng phục vụ audit.

## 3. Yêu cầu sửa lỗi
Team CDO04 (hoặc người nắm quyền quản trị AWS SSO) vui lòng cập nhật lại Permission Set của CDO07 trên AWS Identity Center.

**Các quyền cần bổ sung (Wildcard khuyên dùng cho Read-Only):**
```json
{
    "Effect": "Allow",
    "Action": [
        "cloudwatch:Describe*",
        "cloudwatch:List*",
        "cloudwatch:Get*",
        "networkflowmonitor:Get*",
        "networkflowmonitor:List*"
    ],
    "Resource": "*"
}
```

## 4. Tiêu chí nghiệm thu
- [ ] Admin đã cập nhật Permission Set trên AWS SSO.
- [ ] User team CDO07 truy cập được giao diện Dashboards, Alarms trên CloudWatch và giao diện Network Flow Monitor mà không bị vướng lỗi "is not authorized to perform".
