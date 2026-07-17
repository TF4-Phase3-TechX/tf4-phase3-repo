# D5-04 — Resource Admission Policy Test

**Directive:** D5-04 — Resource remediation rollout
**Owner:** Ninh — Security / Platform Engineering
**Namespace:** `resource-policy-test`
**Scope:** Validate admission behavior for resource-related policy checks without targeting production namespaces.
**Thư mục evidence:** `./resources/`
**Trạng thái:** PARTIAL — manifest suite prepared, live cluster execution pending due authentication blocker.

---

## 0. Phạm vi & phương pháp

Bộ test này nhằm xác minh hành vi của admission policy đối với các trường hợp resource compliance:

- thiếu toàn bộ `resources`
- chỉ có `requests`, thiếu `limits`
- chỉ có `limits`, thiếu `requests`
- `initContainer` thiếu `resources`
- manifest compliant

Mục tiêu là kiểm tra policy có:

- từ chối manifest không compliant
- báo lỗi rõ field vi phạm
- phát hiện vi phạm ở `initContainer`
- chấp nhận manifest compliant
- không chạy trong namespace production, chỉ dùng namespace non-production `resource-policy-test`

Tất cả manifest được chuẩn bị ở thư mục này và chạy bằng `kubectl apply --dry-run=server` trong namespace non-production nhằm giảm blast radius.

### Phương pháp chạy

1. Tạo namespace `resource-policy-test` nếu chưa tồn tại.
2. Chạy từng manifest bằng lệnh:

```powershell
kubectl apply --dry-run=server -f <manifest> -n resource-policy-test
```

3. Ghi output thực tế vào thư mục `results/`.

---

## 1. Test manifest suite

| Case | File | Mục đích | Expected result | Status |
| --- | --- | --- | --- | --- |
| 01 | `01-missing-resources.yaml` | Manifest không có `resources` block | Reject | Prepared |
| 02 | `02-missing-limits.yaml` | Container có `requests` nhưng thiếu `limits` | Reject | Prepared |
| 03 | `03-missing-requests.yaml` | Container có `limits` nhưng thiếu `requests` | Reject | Prepared |
| 04 | `04-initcontainer-missing-resources.yaml` | `initContainer` thiếu `resources` | Reject | Prepared |
| 05 | `05-compliant.yaml` | Manifest có cả `requests` và `limits` | Accept | Prepared |

### Test case detail

#### Case 01 — Missing resources
- Target: container không có `resources` block.
- Expected violation: field `spec.containers[0].resources`.
- File: `01-missing-resources.yaml`

#### Case 02 — Missing limits
- Target: container có `requests` nhưng không có `limits`.
- Expected violation: field `spec.containers[0].resources.limits`.
- File: `02-missing-limits.yaml`

#### Case 03 — Missing requests
- Target: container có `limits` nhưng không có `requests`.
- Expected violation: field `spec.containers[0].resources.requests`.
- File: `03-missing-requests.yaml`

#### Case 04 — InitContainer missing resources
- Target: `initContainer` không có `resources` block.
- Expected violation: field `spec.initContainers[0].resources`.
- File: `04-initcontainer-missing-resources.yaml`

#### Case 05 — Compliant manifest
- Target: có đầy đủ `requests` và `limits` cho container.
- Expected result: accepted by admission policy.
- File: `05-compliant.yaml`

---

## 2. Execution notes

### Current execution status

Bộ test đã chuẩn bị đầy đủ và script runner sẵn sàng, nhưng lần chạy đầu tiên bị chặn do environment không có credential hợp lệ cho cluster.

#### Observed blocker

- `kubectl apply --dry-run=server` không thể validate vì cluster API yêu cầu credentials.
- `aws sts get-caller-identity` thất bại do AWS credential không hợp lệ / chưa đủ thông tin.

#### Runner

Script chạy test:

- `run-admission-tests.ps1`

Command:

```powershell
./docs/evidence/directive-05/admission-tests/resources/run-admission-tests.ps1
```

---

## 3. Acceptance Criteria assessment

| # | Tiêu chí | Kết quả | Giải trình ngắn gọn |
| --- | --- | --- | --- |
| 1 | Manifest thiếu resources bị từ chối | PENDING | Manifest đã sẵn sàng; cần chạy thật trên cluster để thu output admission chính thức. |
| 2 | Error message chỉ rõ field vi phạm | PENDING | Cần thực thi trên cluster để xác nhận message của policy. |
| 3 | InitContainer violation bị phát hiện | PENDING | Manifest test đã cấu hình đúng trường hợp này; cần kết quả chạy thực tế. |
| 4 | Compliant manifest được chấp nhận | PENDING | Manifest compliant đã chuẩn bị; cần xác nhận bằng admission output. |
| 5 | Workload production hiện tại đều compliant hoặc có exception rõ ràng | PENDING | Cần review runtime manifests / rendered manifests trước khi kết luận. |
| 6 | Test không chạy trong namespace production nếu có blast radius | PASS | Tất cả test target namespace là `resource-policy-test` non-production. |
| 7 | Có screenshot/CLI output mentor chứng kiến | PENDING | Chưa thực hiện được do blocker auth; cần chạy lại khi có access. |

**Tổng:** 1/7 PASS, 6/7 PENDING.

---

## 4. Evidence location

| Loại evidence | Đường dẫn |
| --- | --- |
| Hướng dẫn test | `README.md` |
| Manifest cases | `01-missing-resources.yaml` đến `05-compliant.yaml` |
| Script runner | `run-admission-tests.ps1` |
| Execution status | `execution-status.md` |
| Output thử nghiệm | `results/execution-attempt.log` |

---

## 5. Next actions

| Việc | Owner | Status |
| --- | --- | --- |
| Chạy test thực tế trên cluster | Ninh / mentor | Pending auth |
| Thu output admission policy cho từng case | Ninh | Pending |
| Đối chiếu kết quả với acceptance criteria | Security + Performance | Pending |
| Review production workloads cho compliance hoặc exception | Platform / App owners | Pending |

---

## 6. Raw evidence / notes

- Manifest suite and runner created successfully in this folder.
- Initial execution attempt failed due cluster credential issue.
- The test design intentionally uses `resource-policy-test` so no production namespace is involved.

---

## 7. Recommended final wording for mentor review

> Bộ test admission policy cho resource remediation đã được chuẩn bị đầy đủ với 5 manifest case, bao gồm các trường hợp reject và một case compliant. Các test target namespace non-production `resource-policy-test` để tránh blast radius. Hiện tại chạy thật trên cluster bị chặn do thiếu credential hợp lệ, nên output admission policy chính thức chưa thu được. Khi có kubeconfig / AWS auth hợp lệ, cần chạy script và lưu output để chứng minh các acceptance criteria đã được đáp ứng.
