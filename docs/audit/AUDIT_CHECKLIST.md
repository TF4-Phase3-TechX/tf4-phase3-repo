# Audit & Evidence Checklist

Danh sách kiểm toán định kỳ dành riêng cho team Audit (CD007).

## 1. IAM & Access Analyzer (Audit)
- [ ] Truy xuất Access Analyzer: Có role nào đang over-privileged so với thực tế sử dụng không?
- [ ] Kiểm tra lịch sử truy cập: Root account có được sử dụng trong 30 ngày qua không?
- [ ] Liệt kê các quyền Temporary Bootstrap Access đang active.

## 2. CloudTrail & Immutability
- [ ] CloudTrail có đang hoạt động ở tất cả các region không?
- [ ] Bucket S3 lưu trữ CloudTrail có đang bật tính năng Versioning không?
- [ ] Quyền truy cập vào bucket CloudTrail có giới hạn chặt chẽ (chỉ Read-only cho Audit) không?

## 3. AWS Config & Change Trace
- [ ] AWS Config có đang ghi nhận thay đổi trên các resource quan trọng (VPC, IAM, EKS) không?
- [ ] Các thay đổi (Change) phát hiện trong AWS Config có map với bất kỳ Architecture Decision Record (ADR) nào đã được duyệt không?

## 4. Control Plane Audit (EKS)
- [ ] Kiểm tra xác suất 1 hành động `kubectl` có được ghi vết trong CloudWatch (EKS Audit Logs) hay k hông.
