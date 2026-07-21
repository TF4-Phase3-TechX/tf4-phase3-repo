# MANDATE-10 — Bằng chứng kiểm toán phê duyệt con người

**Người phụ trách:** Nguyễn Phú Triệu (CDO-07 Auditability)
**Phạm vi:** Human Approval Evidence và kiểm tra branch protection
**Thời điểm thu thập bằng chứng:** 2026-07-21
**Nhánh nguồn:** `main`

## 1. Phạm vi kiểm toán

Tài liệu này ghi nhận việc kiểm tra độc lập, chỉ đọc đối với bằng chứng phê
duyệt con người của MANDATE-10. Mục tiêu là chứng minh chuỗi:

```text
Commit SHA từ Provenance
  -> Pull Request #443
  -> PR merge vào main
  -> reviewer APPROVED trước khi merge
  -> ruleset branch protection của main
```

PR #443 được dùng làm mẫu kiểm tra vì đã merge vào `main` và có dữ liệu review
đầy đủ trên GitHub.

## 2. Đối chiếu Commit với Pull Request

| Trường | Giá trị | Kết quả |
|---|---|---|
| Repository | `TF4-Phase3-TechX/tf4-phase3-repo` | PASS |
| Pull Request | `#443` — `fix(currency): pass otel batch processor runtime options` | PASS |
| Trạng thái | `closed`, `merged: true` | PASS |
| Nhánh đích | `main` | PASS |
| Head SHA | `acbd4ac48d977bd13e801d7ca9708aa911f001f7` | INFO |
| Merge commit SHA | `a93093665767a27c40b71e6597b10c1ce20dd702` | PASS |
| Provenance SHA | `a93093665767a27c40b71e6597b10c1ce20dd702` | PASS |
| So khớp commit | `True` | PASS |
| Người merge | `NamHoang4268` | INFO |
| Thời điểm merge | `2026-07-21T07:44:41Z` | INFO |
| URL | `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/443` | PASS |

## 3. Bằng chứng người phê duyệt

Hai review có trạng thái `APPROVED` được ghi nhận trước thời điểm merge:

| Reviewer | Trạng thái | Thời điểm | Commit được review |
|---|---|---|---|
| `NamHoang4268` | `APPROVED` | `2026-07-21T07:40:58Z` | `acbd4ac48d977bd13e801d7ca9708aa911f001f7` |
| `Remmusss` | `APPROVED` | `2026-07-21T07:42:24Z` | `acbd4ac48d977bd13e801d7ca9708aa911f001f7` |

Thời điểm merge là `2026-07-21T07:44:41Z`, sau cả hai approval. Kết quả này
đáp ứng bằng chứng rằng PR đã có human approval trước khi merge.

## 4. Kiểm tra branch protection của main

| Kiểm tra | Kết quả | Đánh giá |
|---|---|---|
| Ruleset `main` | `active` | PASS |
| Required PR approvals | `2` | PASS |
| Require code-owner review | `True` | PASS |
| Require status checks | `NOT CONFIGURED` | FINDING |

Finding về status checks được chuyển cho Security/DevOps. Team Audit không cấu
hình hoặc thay đổi branch protection trong phạm vi task này.

## 5. Kết luận kiểm toán

Với mẫu PR #443, Audit có thể truy vết từ Provenance commit SHA đến đúng PR,
xác định PR đã merge vào `main`, xác định hai reviewer đã bấm `APPROVED` trước
khi merge và xác minh ruleset approval của `main` đang active.

Tuy nhiên, repository hiện chưa có required status checks trong ruleset `main`.
Đây là finding cần được khắc phục bởi team phụ trách pipeline/branch protection
trước khi kết luận kiểm soát đầy đủ.

## 6. Phạm vi không thay đổi

PR này chỉ bổ sung tài liệu và bằng chứng kiểm toán. Không thay đổi GitHub
Actions, ECR, Kubernetes, Terraform, workload production hoặc cấu hình branch
protection.
