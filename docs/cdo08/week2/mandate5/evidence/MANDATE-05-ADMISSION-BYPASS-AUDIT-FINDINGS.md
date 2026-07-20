# AUDIT FINDINGS — Mandate 5 Admission Control Bypass

## PoC Test 2026-07-19 | 17:24–17:42 UTC

| Field | Value |
|---|---|
| Test Window | 2026-07-19T17:24:18Z – 17:42:51Z (UTC) |
| Namespace | `techx-tf4` |
| Trigger | kubectl apply trực tiếp |
| Investigated by | Quân |
| Detected | 2026-07-20, qua rà soát thủ công — không có alert tự động nào phát hiện |
| Severity | CRITICAL (cả 3 finding) |

---

## 1. Tóm tắt

3 pod PoC (label `poc: mandate05-lab`) được tạo trực tiếp trong `techx-tf4`, đều **pass đủ 4 luật admission `[Deny]`** đang enforce (`require-run-as-nonroot`, `disallow-mutable-image-tag`, `require-resource-limits`, `require-drop-all-capabilities`), sau đó khai thác 3 vector nằm ngoài phạm vi 4 luật này. Không có dữ liệu khách hàng bị lộ trong bài test — nhưng phương thức tái tạo được bởi bất kỳ ai có cùng mức quyền truy cập.

## 2. Timeline

| Thời gian (UTC) | Sự kiện |
|---|---|
| 2026-07-19 17:24:18 | Pod `poc-privileged` tạo — admitted |
| 2026-07-19 17:24:21 | Pod `poc-hostesc` tạo — admitted |
| 2026-07-19 17:42:08 | Pod `poc-debug-target` tạo — admitted (compliant) |
| 2026-07-19 17:42:51 | Ephemeral container `debug-poc` inject vào `poc-debug-target` qua `kubectl debug` |

## 3. Findings

| # | Đối tượng | Đã pass (đúng cấu hình) | Vector không bị luật nào chặn | Kết quả xác nhận thật |
|---|---|---|---|---|
| F1 | Pod `poc-privileged` | non-root, UID≠0, drop ALL capabilities | `securityContext.privileged: true` | Container thấy được raw block device (`nvme`/`xvd`/`sd`) của worker node trong `/dev` — quyền tương đương root trên node |
| F2 | Pod `poc-hostesc` | non-root, UID≠0, drop ALL capabilities, `allowPrivilegeEscalation: false`, seccomp RuntimeDefault | `hostNetwork: true`, `hostPID: true`, `hostPath: /` mount vào `/host` | (a) Lấy được IAM credentials tạm thời của worker node qua IMDS; (b) đọc được `/host/etc/os-release`, `/host/etc/hostname`, liệt kê thư mục dữ liệu của pod khác trên cùng node qua `/host/var/lib/kubelet/pods` |
| F3 | Pod `poc-debug-target` + ephemeral container `debug-poc` | Pod gốc compliant 100% lúc CREATE | `pods/ephemeralcontainers` subresource — không nằm trong `matchConstraints.resourceRules` của bất kỳ policy nào | Ephemeral container chạy `uid=0/gid=0` (root), image `busybox:latest` (tag trôi) — inject được vào pod đã duyệt sạch, không qua bất kỳ bước kiểm duyệt nào |

## 4. Impact

| # | Impact |
|---|---|
| F1 | Toàn quyền đọc/ghi dữ liệu trên disk vật lý của worker node — bao gồm dữ liệu của mọi pod khác cùng chạy trên node đó, không chỉ pod bị khai thác. |
| F2 | Chiếm danh tính cloud (IAM role) của worker node — phạm vi quyền cụ thể phụ thuộc IAM policy gắn cho node, cần audit riêng để xác định chính xác. Đọc được token/secret của các pod khác dùng chung node → lan ngang (lateral movement) sang dịch vụ không liên quan. |
| F3 | Phá vỡ giả định nền tảng "admission duyệt một lần = an toàn suốt vòng đời" — áp dụng cho **mọi** pod đang chạy trong phạm vi enforce, không riêng pod bị khai thác trong test. Ai có quyền `pods/ephemeralcontainers` (thường cấp rộng cho mục đích debug/vận hành) đều khai thác được, bất kỳ lúc nào sau khi pod đã chạy. |

## 5. Phạm vi đã rà soát thêm

- Toàn bộ pod/deployment/job/cronjob/serviceaccount/rolebinding/role/secret/configmap tạo trong khung `2026-07-19T14:00:00Z` trở đi, toàn cluster — không có object bất thường nào khác ngoài 3 pod trên.
- Các thay đổi hạ tầng khác cùng thời điểm (Kyverno, policy digest SEC-17 giai đoạn thử nghiệm) đã đối chiếu riêng — xác nhận là công việc hợp lệ, có tài liệu, không liên quan sự việc này.

## 6. Trạng thái hiện tại

3 pod PoC vẫn tồn tại trên cluster, chưa xoá — giữ làm bằng chứng.

---

**Liên quan:** `CDO08-SEC-11-mentor-poc-incident-report.md`
**Last updated:** 2026-07-20
