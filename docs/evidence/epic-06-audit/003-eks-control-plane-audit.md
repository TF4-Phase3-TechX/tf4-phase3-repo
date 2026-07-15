# Evidence kiểm toán EKS Control Plane

## 1. Kiểm soát tài liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Evidence ID | `TF4-CDO07-EKS-AUDIT-20260715` |
| Trạng thái | **PASS - Ready for Review** |
| Người thực hiện | Bá Huân - CDO07 Auditability |
| Thời điểm kiểm tra | 15/07/2026 17:16, múi giờ `Asia/Saigon` |
| Account / Region | `511825856493` / `us-east-1` |
| EKS cluster | `techx-tf4-cluster` |
| Permission Set | `TF4-AuditReadOnlyAndAnalyze` |
| AWS profile | `cdo07-tf4-auditreadonly` |
| Checklist | [`AUDIT_CHECKLIST.md`](../../audit/AUDIT_CHECKLIST.md) |

## 2. Mục tiêu

Xác minh một hành động `kubectl` thực hiện bằng danh tính SSO cá nhân có được ghi vào CloudWatch EKS Audit Logs với đủ dữ liệu để trả lời:

- Ai thực hiện?
- Thực hiện hành động gì trên resource nào?
- Hành động xảy ra khi nào và từ IP nào?
- API và cơ chế phân quyền trả về kết quả gì?

## 3. Phạm vi

Evidence này kiểm tra khả năng truy vết một request read-only tới Kubernetes API Server. Evidence không kiểm tra hành động ghi, không thay đổi cluster và không kết luận toàn bộ MANDATE-04 đã hoàn thành.

## 4. Cấu hình logging quan sát được

| Thuộc tính | Giá trị | Đánh giá |
| --- | --- | --- |
| Cluster status | `ACTIVE` | **PASS** |
| Control plane logs đang bật | `api`, `audit`, `authenticator` | **PASS** |
| CloudWatch log group | `/aws/eks/techx-tf4-cluster/cluster` | **PASS** |
| Retention | 90 ngày | Ghi nhận |
| Customer-managed KMS key | Chưa cấu hình | Ngoài phạm vi control này |

## 5. Phương pháp kiểm tra

1. Xác nhận kubeconfig đang dùng context `techx-tf4-cdo07` cho cluster `techx-tf4-cluster`.
2. Thực hiện một lệnh chỉ đọc tới Kubernetes API Server.
3. Tìm CloudWatch event trong cửa sổ `2026-07-15T10:15:30Z` đến `2026-07-15T10:17:30Z`.
4. Chỉ chấp nhận event có `userAgent` là `kubectl`, stage `ResponseComplete`, đúng resource và đúng identity SSO.
5. Loại bỏ access key ID khỏi evidence lưu trong Git vì không cần thiết cho mục tiêu kiểm toán.

Lệnh kiểm tra:

```powershell
kubectl get namespace default -o json --request-timeout=30s
```

Kết quả lệnh: exit code `0`, Kubernetes trả về namespace `default`.

## 6. Audit event khớp

| Trường audit | Giá trị |
| --- | --- |
| Audit ID | `3dc75ebd-d27c-477b-9a30-007db785c867` |
| Request received | `2026-07-15T10:16:04.940063Z` |
| Stage timestamp | `2026-07-15T10:16:04.953908Z` |
| Stage | `ResponseComplete` |
| Verb | `get` |
| Request URI | `/api/v1/namespaces/default?timeout=30s` |
| Resource | `namespaces/default` |
| Username | `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/huan.huynh` |
| Kubernetes group | `audit-readonly-analyzers`, `system:authenticated` |
| Source IP | `14.236.16.56` |
| User agent | `kubectl.exe/v1.34.1 (windows/amd64) kubernetes/93248f9` |
| HTTP response | `200` |
| Authorization decision | `allow` |
| Access policy | `AmazonEKSViewPolicy` |
| Log stream | `kube-apiserver-audit-723a34970c59cd07043f7e0adc9ffdb9` |
| CloudWatch ingestion time | `2026-07-15T10:16:08.715Z` |

CloudWatch ingest event sau thời điểm audit nhận request khoảng 3,8 giây. Độ trễ này phù hợp với cơ chế giao log bất đồng bộ và không làm mất khả năng dựng lại timeline.

## 7. Đối chiếu who/what/when

| Câu hỏi | Dữ liệu trả lời | Kết quả |
| --- | --- | --- |
| Ai? | SSO session `huan.huynh`, Permission Set `TF4-AuditReadOnlyAndAnalyze` | **PASS** |
| Làm gì? | `get` namespace `default` bằng `kubectl` | **PASS** |
| Khi nào? | `2026-07-15T10:16:04.940063Z` | **PASS** |
| Từ đâu? | Source IP `14.236.16.56` | **PASS** |
| Được phép bởi đâu? | `AmazonEKSViewPolicy`, decision `allow` | **PASS** |
| Kết quả API? | HTTP `200`, stage `ResponseComplete` | **PASS** |

## 8. Kết luận

Control **PASS** với tỷ lệ quan sát `1/1`: hành động `kubectl` read-only được ghi nhận trong CloudWatch EKS Audit Logs và truy về được danh tính cá nhân, thời điểm, resource, IP nguồn, quyết định phân quyền và kết quả API.

Kết quả này chứng minh đường ghi vết EKS hoạt động cho mẫu đã kiểm tra. Đây không phải phép đo thống kê về xác suất mất log và không thay thế các control MANDATE-04 về chống sửa/xóa, separation of duties, identity mapping toàn bộ operator hoặc forensic drill đầu cuối.

## 9. Evidence index

| Evidence | Nội dung | Link |
| --- | --- | --- |
| `E-EKS-01` | Runtime evidence đã chuẩn hóa và loại bỏ dữ liệu không cần thiết | [`003-eks-control-plane-audit-runtime-evidence.json`](003-eks-control-plane-audit-runtime-evidence.json) |
| `E-EKS-02` | Terraform bật EKS control plane logs | [`eks.tf`](../../../infra/terraform/eks.tf) |
| `E-EKS-03` | Checklist và kết luận Pass/Fail | [`AUDIT_CHECKLIST.md`](../../audit/AUDIT_CHECKLIST.md) |

## 10. Lệnh tái kiểm tra

```powershell
aws eks describe-cluster `
  --name techx-tf4-cluster `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly

aws logs filter-log-events `
  --log-group-name /aws/eks/techx-tf4-cluster/cluster `
  --filter-pattern '{ $.userAgent = "kubectl*" }' `
  --region us-east-1 `
  --profile cdo07-tf4-auditreadonly
```

## 11. Giới hạn và tái kiểm tra

- Đây là point-in-time evidence của một request read-only.
- Nên chạy lại sau khi thay đổi EKS logging, access entry, RBAC hoặc CloudWatch retention.
- Không lưu trường access key ID từ raw audit event vào Git.
- Nếu cần chứng minh tamper-evident, phải kiểm tra riêng quyền `logs:DeleteLogGroup`, `logs:DeleteLogStream`, `logs:PutRetentionPolicy`, KMS và cơ chế archive/WORM.

## 12. Phê duyệt

| Vai trò | Người xác nhận | Trạng thái | Ngày |
| --- | --- | --- | --- |
| Người lập evidence - CDO07 | Bá Huân | Hoàn thành | 15/07/2026 |
| Reviewer control plane audit | Chờ reviewer trên Jira/PR | Pending | - |
