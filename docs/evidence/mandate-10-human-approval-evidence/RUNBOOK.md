# MANDATE-10 — Runbook thu thập bằng chứng phê duyệt con người

**Người phụ trách:** Nguyễn Phú Triệu (CDO-07 Auditability)
**Repository:** `TF4-Phase3-TechX/tf4-phase3-repo`
**Sub-task:** Human Approval Evidence

## 1. Mục tiêu

Từ commit SHA trong Provenance, truy ngược đến đúng Pull Request, xác nhận PR
đã merge vào `main`, xác định người đã bấm `Approve`, sau đó kiểm tra ruleset
branch protection của `main`.

Audit chỉ đọc dữ liệu. Không dùng runbook này để thay đổi approval rule hoặc
required status checks.

## 2. Chuẩn bị

```powershell
$repo = "TF4-Phase3-TechX/tf4-phase3-repo"
$prNumber = 443
$provenanceSha = "a93093665767a27c40b71e6597b10c1ce20dd702"

gh auth status
```

Tài khoản cần có quyền đọc repository, pull request reviews và rulesets. Không
đưa token hoặc secret vào ảnh chụp màn hình.

## 3. Đối chiếu commit với Pull Request

Chạy trực tiếp trên GitHub API:

```powershell
$pr = gh api "repos/$repo/pulls/$prNumber" | ConvertFrom-Json

[PSCustomObject]@{
  PRNumber       = $pr.number
  Title          = $pr.title
  State          = $pr.state
  Merged         = $pr.merged
  BaseBranch     = $pr.base.ref
  HeadSHA        = $pr.head.sha
  MergeCommitSHA = $pr.merge_commit_sha
  ProvenanceSHA  = $provenanceSha
  CommitMatch    = ($pr.merge_commit_sha -eq $provenanceSha)
  MergedAt       = $pr.merged_at
  MergedBy       = $pr.merged_by.login
  URL            = $pr.html_url
} | Format-List
```

Kết quả đạt yêu cầu khi `Merged` là `True`, `BaseBranch` là `main` và
`CommitMatch` là `True`.

## 4. Lấy lịch sử approval

Không dùng jq inline nếu PowerShell làm hỏng dấu ngoặc kép. Dùng vòng lặp
PowerShell để lọc dữ liệu thật từ GitHub:

```powershell
$reviews = gh api "repos/$repo/pulls/$prNumber/reviews" | ConvertFrom-Json

$approvedRows = @(
  foreach ($review in $reviews) {
    if ($review.state -eq "APPROVED") {
      [PSCustomObject]@{
        Reviewer    = $review.user.login
        State       = $review.state
        SubmittedAt = $review.submitted_at
        CommitID    = $review.commit_id
        URL         = $review.html_url
      }
    }
  }
)

$approvedRows | Format-Table -AutoSize
```

Đối chiếu thêm `SubmittedAt` với `MergedAt`. Approval hợp lệ cho bằng chứng
human approval phải xuất hiện trước thời điểm merge.

## 5. Kiểm tra branch protection của main

```powershell
$rulesets = gh api "repos/$repo/rulesets" | ConvertFrom-Json
$mainRule = $rulesets | Where-Object { $_.name -eq "main" } | Select-Object -First 1
$mainDetail = gh api "repos/$repo/rulesets/$($mainRule.id)" | ConvertFrom-Json

$pullRule = $mainDetail.rules |
  Where-Object { $_.type -eq "pull_request" } |
  Select-Object -First 1

$statusRule = $mainDetail.rules |
  Where-Object { $_.type -eq "required_status_checks" } |
  Select-Object -First 1

[PSCustomObject]@{
  Ruleset              = $mainDetail.name
  Enforcement          = $mainDetail.enforcement
  Branch               = "main"
  RequiredApprovals    = $pullRule.parameters.required_approving_review_count
  CodeOwnerReview      = $pullRule.parameters.require_code_owner_review
  StatusChecks         = if ($null -ne $statusRule) { "CONFIGURED" } else { "NOT CONFIGURED - FINDING" }
} | Format-List
```

Kết quả đã thu thập: ruleset `main` active, yêu cầu 2 approvals, code-owner
review bật, nhưng required status checks chưa cấu hình.

## 6. Quy trình chụp evidence

1. Chạy mục 3 và chụp toàn bộ output có `PRNumber`, `MergeCommitSHA`,
   `ProvenanceSHA`, `CommitMatch : True` và URL. Lưu thành
   `H2-01-commit-to-pr.png`.
2. Chạy mục 4 và chụp các dòng reviewer, `APPROVED`, thời gian và commit ID.
   Lưu thành `H2-02-pr-approval-reviewers.png`.
3. Chạy mục 5 và chụp `Ruleset`, `Enforcement`, `RequiredApprovals`,
   `CodeOwnerReview` và `StatusChecks`. Lưu thành
   `H2-03-main-branch-protection.png`.
4. Lưu các kết quả có cấu trúc vào `HUMAN-APPROVAL-RECORD.json` để Jira có
   bản đọc máy bên cạnh ảnh.

## 7. Kết luận và finding

- PR #443 là PR đã merge vào `main` và merge commit khớp Provenance SHA.
- Hai reviewer `NamHoang4268` và `Remmusss` có review `APPROVED` trước merge.
- Approval rule đang được bật với ngưỡng 2 approvals.
- Required status checks chưa cấu hình. Đây là finding cần Security/DevOps
  xử lý; team Audit chỉ ghi nhận, không tự cấu hình.
