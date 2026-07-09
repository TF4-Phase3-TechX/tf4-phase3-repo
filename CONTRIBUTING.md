# Contributing to TF4 Phase 3 — TechX Corp Service Takeover

**Repo:** [TF4-Phase3-TechX/tf4-phase3-repo](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo)
**Teams:** AIO-01, CDO-04, CDO-07, CDO-08

Mọi thay đổi vào repo này đều đi qua PR. File này quy định convention branch, commit, PR, merge strategy, và review process.

---

## 1. Branch Convention

### Format

```
<team>/<type>/<short-description>
```

### Team prefix


| Team   | Prefix   |
| ------ | -------- |
| AIO-01 | `aio01/` |
| CDO-04 | `cdo04/` |
| CDO-07 | `cdo07/` |
| CDO-08 | `cdo08/` |


### Type prefix

Dùng cùng type với commit convention:

```
feat/       # tính năng mới
fix/        # sửa bug
build/      # build system, Docker, dependency, image build
chore/      # việc phụ trợ, tooling, cleanup
docs/       # tài liệu
style/      # format, whitespace, không đổi logic
refactor/   # refactor không đổi behavior
perf/       # cải thiện performance
test/       # thêm/sửa test
hotfix/     # sửa gấp từ main
```

### Ví dụ

```text
# Tốt
aio01/feat/add-cart-hpa
cdo04/fix/payment-readiness-probe
cdo07/docs/week1-pitch-outline
cdo08/perf/checkout-loadtest-baseline

# Không tốt
fix
update
final
thanh-branch
wip
```

### Luồng tổng quát

```
main → team branch → PR → main
```

Chỉ có **một nhánh dài hạn** là `main`. Không dùng `develop`.

---

## 2. Commit Convention

### Format

```
<type>[optional scope]: <description>

[optional body]
```

### Allowed types


| Type       | Dùng khi                                                   |
| ---------- | ---------------------------------------------------------- |
| `feat`     | thêm/cập nhật tính năng mới                                |
| `fix`      | sửa lỗi                                                    |
| `build`    | build system, Docker, dependency, package manager          |
| `chore`    | việc phụ trợ, không đổi app behavior                       |
| `docs`     | thay đổi tài liệu                                          |
| `style`    | format code, whitespace, lint; không đổi logic             |
| `refactor` | refactor code; không thêm feature, không sửa bug trực tiếp |
| `perf`     | cải thiện performance                                      |
| `test`     | thêm/sửa test                                              |


### Description rules

- Viết ngắn, imperative mood nếu tiếng Anh
- Không viết hoa chữ đầu bắt buộc
- Không dấu chấm cuối dòng
- Nói rõ thay đổi chính

### Scope (optional, khuyến khích dùng)

```
frontend        checkout        cart
payment         product-catalog product-reviews
llm             kafka           db
helm            deploy          observability
ci              docs
```

### Ví dụ tốt

```text
feat: allow provided config object to extend other configs
fix(payment): add readiness probe before receiving traffic
perf(checkout): reduce database query latency
docs: add week 1 risk register
chore(ci): add helm template check
```

### Ví dụ không tốt

```text
update
fix bug
change code
final commit
```

### Body (optional)

Dùng khi cần giải thích "vì sao":

```text
fix(payment): add readiness probe before receiving traffic

Payment received traffic before the gRPC server was ready during deploy.
This adds a readiness gate so Kubernetes stops routing early requests.
```

---

## 3. Pull Request Convention

### PR title

Dùng cùng Conventional Commit format — vì repo dùng squash/rebase, **PR title sẽ thành commit message cuối cùng** trên `main`.

```
<type>(<scope>): <description>
```

Ví dụ:

```text
feat(checkout): add HPA baseline
fix(payment): add readiness probe
perf(checkout): add baseline load test result
docs: add week 1 pitch outline
```

### PR body template

```md
## Summary
- 

## Why
- 

## Changes
- 

## Verification
- [ ] test/lint/build pass
- [ ] helm template pass nếu đụng chart/deploy
- [ ] deploy/smoke test nếu đụng runtime

## Risk & rollback
- Risk:
- Rollback:

## Scope
- Team: AIO01 / CDO04 / CDO07 / CDO08
- Area:
```

### PR size rule

- **1 PR = 1 mục tiêu rõ ràng**
- Lý tưởng dưới **300-500 dòng diff**
- Tách **docs-only** khỏi code/config changes
- Tách **refactor** khỏi behavior changes

Không nên:

- Gom 5 service + Helm + docs + refactor vào 1 PR
- Sửa format toàn repo chung với bugfix
- Đổi requirement docs chung với PR app code

---

## 4. Merge Strategy

### Strategies bật trong repo

```
Squash and merge     ← mặc định
Rebase and merge
```

Không bật `Merge commit` để tránh merge bubble, ưu tiên history tuyến tính.

### Khi nào dùng gì?


| Loại PR                                      | Strategy             | Lý do                                   |
| -------------------------------------------- | -------------------- | --------------------------------------- |
| Feature/fix thường                           | **Squash and merge** | Gọn history, dễ revert theo PR          |
| Docs/chore nhỏ                               | **Squash and merge** | Không cần giữ nhiều commit nhỏ          |
| PR có commit sạch, mỗi commit có nghĩa riêng | **Rebase and merge** | Giữ history tuyến tính và commit atomic |
| Hotfix                                       | **Squash and merge** | Rollback nhanh, main gọn                |


**Rule nhanh:** Không chắc dùng gì → **Squash and merge**.

---

## 5. Branch Protection (`main`)


| Setting                                         | Value   |
| ----------------------------------------------- | ------- |
| Require a pull request before merging           | **ON**  |
| Required approvals                              | **2**   |
| Dismiss stale approvals when new commits pushed | **ON**  |
| Require status checks to pass                   | **ON**  |
| Require branches up to date before merging      | **ON**  |
| Require conversation resolution                 | **ON**  |
| Allow force pushes                              | **OFF** |
| Allow deletions                                 | **OFF** |


### Reviewer rule

```
2 approvals:
- Ít nhất 1 người cùng TF hoặc hiểu context thay đổi
- Ít nhất 1 lead/reviewer phù hợp nếu đụng deploy/chart/requirements/flagd
```

### Required checks (tối thiểu)

```text
ci/lint
ci/test
ci/docker-build-smoke
ci/helm-template
```

---

## 6. Repository Permissions

Quyền cấp qua **GitHub Teams**, không cấp lẻ từng user.


| GitHub Team   | Permission | Vai trò                                            |
| ------------- | ---------- | -------------------------------------------------- |
| `tf4-admins`  | Admin      | Cấu hình repo settings, branch protection, secrets |
| `tf4-mentors` | Maintain   | Review rule/requirements, hỗ trợ unblock           |
| `tf4-leads`   | Maintain   | Quản lý issue/PR/labels, approve vùng chung        |
| `tf4-members` | Write      | Tạo branch, mở PR                                  |


### Phân quyền theo vùng nhạy cảm


| Vùng                               | Ai approve                           |
| ---------------------------------- | ------------------------------------ |
| PR thường                          | Member khác cùng TF hoặc area owner  |
| PR vào `main`                      | Lead/reviewer theo branch protection |
| `docs/requirements/`               | Mentor hoặc lead                     |
| `deploy/` hoặc `techx-corp-chart/` | Lead hoặc mentor                     |
| `flagd` hoặc incident mechanism    | Mentor + Admin                       |


---

## 7. Quick Reference

```text
Branch:   <team>/<type>/<topic>          vd: cdo08/fix/payment-readiness-probe
Commit:   <type>(<scope>): <description> vd: fix(payment): add readiness probe
PR title: <type>(<scope>): <description> vd: feat(checkout): add HPA baseline
Target:   main
Merge:    Squash and merge (default)
Reviews:  2 approvals required
```

