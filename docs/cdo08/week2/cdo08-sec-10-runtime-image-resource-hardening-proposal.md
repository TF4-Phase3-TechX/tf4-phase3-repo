# Đề xuất SEC-10 runtime image pinning và resource baseline

| Thông tin     | Giá trị                                                                                             |
| ------------- | --------------------------------------------------------------------------------------------------- |
| Backlog ID    | `CDO08-SEC-10`                                                                                      |
| Owner         | Hoàng Nam                                                                                           |
| Pillar        | Security                                                                                            |
| Priority      | P0                                                                                                  |
| Loại tài liệu | Technical review proposal                                                                           |
| Review gate   | Nguyên review technical/security risk; CDO04 chỉ review nếu resource request/limit thay đổi đáng kể |
| Phạm vi       | Mandate 5 - pin image và hoàn thiện resources trước admission enforce                               |

## 1. Mục tiêu

Tài liệu này đề xuất hướng xử lý task `CDO08-SEC-10` trước khi implementation. Mục tiêu là làm sạch workload manifests để task `SEC-11` có thể bật admission policy mà không chặn nhầm deploy hợp lệ.

Phạm vi của SEC-10:

- Không còn container image tag trôi như `latest` trong rendered manifests.
- Không còn image không tag rõ, vì registry thường hiểu như `latest`.
- Mọi `containers` và `initContainers` có đủ CPU/memory `requests` và `limits`.
- Resource bổ sung phải conservative, không làm tăng scheduler pressure đột biến.
- Runtime namespace `techx-tf4` và `techx-observability` được scan trước khi chuyển sang enforce ở `SEC-11`.

SEC-10 không bật admission policy. SEC-10 chỉ chuẩn bị workload để khi admission policy được bật ở task sau, manifest nguy hiểm sẽ bị từ chối còn manifest hợp lệ vẫn deploy được.

## 2. Hiện trạng và evidence

### 2.1. Code baseline cần cập nhật trước implementation

Repo local tại thời điểm scan đang lệch `main`:

```text
main...origin/main [behind 9]
```

Do đó trước khi implement cần pull/rebase latest rồi scan lại. Các finding bên dưới là baseline sơ bộ từ code hiện tại, dùng để review hướng xử lý.

### 2.2. Image tag trôi trong chart

Scan `techx-corp-chart/values.yaml` cho thấy các initContainer đang dùng `busybox:latest`:

| Component         | Init container         | Image hiện tại   | Kết luận              |
| ----------------- | ---------------------- | ---------------- | --------------------- |
| `accounting`      | `wait-for-kafka`       | `busybox:latest` | Floating tag, cần pin |
| `cart`            | `wait-for-valkey-cart` | `busybox:latest` | Floating tag, cần pin |
| `checkout`        | `wait-for-kafka`       | `busybox:latest` | Floating tag, cần pin |
| `fraud-detection` | `wait-for-kafka`       | `busybox:latest` | Floating tag, cần pin |
| `frontend-proxy`  | `wait-for-kafka`       | `busybox:latest` | Floating tag, cần pin |

Ngoài ra, `flagd` có initContainer dùng `busybox` không tag rõ:

| Component | Init container | Image hiện tại | Kết luận                                      |
| --------- | -------------- | -------------- | --------------------------------------------- |
| `flagd`   | `init-config`  | `busybox`      | Untagged image, cần pin vì tương đương latest |

Kết luận: blocker rõ nhất của SEC-10 là pin các initContainer `busybox`.

### 2.3. Resource baseline của các initContainer bị ảnh hưởng

Các initContainer `busybox` trên đã có resource nhỏ và ổn định:

```yaml
resources:
    requests: { cpu: 5m, memory: 8Mi }
    limits: { cpu: 25m, memory: 32Mi }
```

Kết luận: phần image cần fix ngay. Phần resources của nhóm initContainer này chưa phải blocker vì đã có cả request và limit.

### 2.4. False positive cần tách khỏi scope

Có `al2023@latest` trong Karpenter `EC2NodeClass`:

```yaml
amiSelectorTerms:
    - alias: al2023@latest
```

Đây là Karpenter AMI alias, không phải container image của workload. SEC-10 tập trung vào workload container images. Nếu security yêu cầu pin AMI alias, nên tạo một infra hardening item riêng để tránh làm loãng scope.

## 3. SEC-10 giải quyết vấn đề gì

Mandate 5 yêu cầu runtime hardening ở tầng workload. Nếu các image/resource hiện tại không được dọn trước, admission policy ở `SEC-11` có thể chặn deploy thật.

SEC-10 giải quyết ba vấn đề vận hành:

- Image tag trôi làm runtime không xác định được chính xác version đang chạy.
- Image không tag rõ có thể bị registry hiểu là `latest`.
- Container/initContainer thiếu requests/limits có thể bị ResourceQuota hoặc admission policy reject, hoặc gây overcommit khó kiểm soát.

SEC-10 không thay thế admission policy. Nó là bước remediation trước khi enforce.

## 4. Điều kiện tiên quyết trước implementation

Không tạo PR implementation khi chưa scan lại latest code.

Điều kiện tối thiểu:

| Điều kiện       | Trạng thái yêu cầu                                         |
| --------------- | ---------------------------------------------------------- |
| Source code     | Branch mới từ `origin/main` mới nhất                       |
| Helm lint       | `helm lint ./techx-corp-chart` pass                        |
| Helm render     | Render với production values hiện tại pass                 |
| Image scan      | Rendered manifests không còn `latest` hoặc image untagged  |
| Resource scan   | Mọi container/initContainer có CPU/memory request và limit |
| Runtime scan    | Scan `techx-tf4` và `techx-observability`                  |
| Capacity review | Nếu phải tăng request đáng kể, cần CDO04 review trước      |

## 5. Image pinning candidate matrix

| Component         | Init container         | Image hiện tại   | Đề xuất          | Rủi ro rollout              | Ghi chú                            |
| ----------------- | ---------------------- | ---------------- | ---------------- | --------------------------- | ---------------------------------- |
| `accounting`      | `wait-for-kafka`       | `busybox:latest` | `busybox:1.36.1` | Thấp nếu `nc` hoạt động     | Chờ Kafka port `9092`              |
| `cart`            | `wait-for-valkey-cart` | `busybox:latest` | `busybox:1.36.1` | Thấp nếu `nc` hoạt động     | Chờ Valkey port `6379`             |
| `checkout`        | `wait-for-kafka`       | `busybox:latest` | `busybox:1.36.1` | Thấp nếu `nc` hoạt động     | Chờ Kafka port `9092`              |
| `fraud-detection` | `wait-for-kafka`       | `busybox:latest` | `busybox:1.36.1` | Thấp nếu `nc` hoạt động     | Chờ Kafka port `9092`              |
| `frontend-proxy`  | `wait-for-kafka`       | `busybox:latest` | `busybox:1.36.1` | Thấp nếu `nc` hoạt động     | Chờ Kafka port `9092`              |
| `flagd`           | `init-config`          | `busybox`        | `busybox:1.36.1` | Thấp nếu `cp/cat` hoạt động | Copy `demo.flagd.json` vào rw path |

Đề xuất dùng `busybox:1.36.1` vì đây là fixed tag phổ biến, đủ cho các command đang dùng: `sh`, `nc`, `cp`, `cat`, `sleep`.

Không bắt buộc chuyển tất cả image sang digest trong task này nếu CI/CD hiện tại chưa hỗ trợ rõ. Fixed immutable tag tạm chấp nhận nếu ADR ghi rõ trade-off.

## 6. Resource request/limit strategy

Nếu scan phát hiện thiếu resource, áp dụng giá trị conservative theo nhóm workload.

| Nhóm container          | Requests đề xuất  | Limits đề xuất | Ghi chú                                      |
| ----------------------- | ----------------- | -------------- | -------------------------------------------- |
| Init/wait container nhẹ | `5m / 8Mi`        | `25m / 32Mi`   | Đã dùng cho busybox hiện tại                 |
| Helper sidecar nhẹ      | `10m / 32Mi`      | `50m / 128Mi`  | Chỉ dùng nếu sidecar thực tế thiếu resources |
| App service đã có base  | Giữ hiện tại      | Giữ hiện tại   | Không tăng nếu không có evidence             |
| Observability component | Không tự tăng lớn | Review riêng   | Tránh gây node pressure                      |

Nguyên tắc:

- SEC-10 không phải task tuning performance.
- Không tăng request/limit lớn nếu chưa có evidence OOM/throttling.
- Nếu resource mới có thể ảnh hưởng capacity, tạo review request cho CDO04 trước khi merge.

## 7. Kế hoạch implementation

Thứ tự đề xuất:

1. Pull latest `origin/main` và tạo branch mới cho SEC-10.
2. Render Helm baseline với `values-app-stamp.yaml` và `values-flagd-sync.yaml`.
3. Scan rendered manifests để xác nhận danh sách image/resource vi phạm.
4. Pin toàn bộ `busybox:latest` và `busybox` không tag thành fixed tag đã review.
5. Bổ sung requests/limits nếu scan phát hiện thiếu.
6. Chạy Helm lint/render và scan lại.
7. Tạo PR nhỏ, chỉ chứa image/resource hardening.
8. Sau GitOps sync, verify runtime pods Ready và không có ImagePullBackOff/ResourceQuota/admission reject.

Không bật admission enforce trong PR này. SEC-11 sẽ xử lý policy-as-code sau khi SEC-10 sạch.

## 8. Verification

### 8.1. Verification trước PR

Render chart:

```bash
helm lint ./techx-corp-chart
helm template techx-corp ./techx-corp-chart \
  --namespace techx-tf4 \
  --set default.image.repository=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp \
  --set default.image.tag=<current-image-tag> \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml \
  > /tmp/techx-sec10-render.yaml
```

Scan image floating/untagged:

```bash
grep -nE 'image: .*(latest|:stable|:main|:master)$|image: [^:@[:space:]]+$' /tmp/techx-sec10-render.yaml || true
```

Expected sau fix:

```text
No workload image result.
```

Scan runtime image theo task:

```bash
kubectl get deploy,sts -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.image}{" "}{end}{range .spec.template.spec.initContainers[*]}{.image}{" "}{end}{"\n"}{end}'
```

Scan runtime resources theo task:

```bash
kubectl get deploy,sts -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":req="}{.resources.requests}{",lim="}{.resources.limits}{" | "}{end}{range .spec.template.spec.initContainers[*]}{.name}{":req="}{.resources.requests}{",lim="}{.resources.limits}{" | "}{end}{"\n"}{end}'
```

### 8.2. Verification sau deploy

```bash
kubectl -n techx-tf4 get pods | grep -E 'Pending|CrashLoopBackOff|ImagePullBackOff|ErrImagePull|OOMKilled|Error|Init' || true
kubectl -n techx-observability get pods | grep -E 'Pending|CrashLoopBackOff|ImagePullBackOff|ErrImagePull|OOMKilled|Error|Init' || true
```

Kỳ vọng:

- Không có `ImagePullBackOff` do tag pin sai.
- Không có `ResourceQuota` hoặc admission reject.
- Workloads trở lại Ready.
- Rendered manifests không còn `latest` hoặc untagged image trong workload scope.

## 9. Rollback và safety

Nếu rollout bị lỗi:

1. Kiểm tra pod event để xác định lỗi là `ImagePullBackOff`, `ResourceQuota`, hay admission reject.
2. Nếu lỗi do image tag mới, rollback image về tag đã biết chạy được và báo PM/CDO04.
3. Nếu lỗi do resource mới, rollback resource value của workload đó.
4. Không tăng resource request lớn trong lúc sự cố nếu chưa có CDO04/Tech Lead approval.
5. Ghi evidence vào Jira trước khi retry.

Rollback bằng GitOps/Helm source là hướng ưu tiên. Không sửa tay runtime trừ khi có emergency approval.

## 10. Các quyết định cần review

Nguyên cần xác nhận technical/security scope trước implementation. CDO04 chỉ cần review nếu resource request/limit thay đổi đáng kể:

- Đồng ý dùng `busybox:1.36.1` cho các initContainer hiện đang dùng `busybox:latest` hoặc `busybox` không tag.
- Đồng ý giữ resource hiện tại của các initContainer busybox: `requests 5m/8Mi`, `limits 25m/32Mi`.
- Đồng ý chưa chuyển toàn bộ workload image sang digest trong task này; fixed tag tạm chấp nhận và sẽ ghi rõ trong ADR.
- Đồng ý loại `al2023@latest` của Karpenter AMI alias khỏi scope SEC-10 container image pinning; nếu cần pin AMI thì tạo infra hardening task riêng.
- Đồng ý verification gồm Helm render scan và runtime scan cho `techx-tf4`, `techx-observability` trước khi SEC-11 enforce.

## 11. Quan hệ với Mandate 5

Mandate 5 yêu cầu hệ thống từ chối manifest nguy hiểm ngay khi apply. SEC-10 là bước remediation trước khi admission enforce.

Thứ tự đúng:

1. SEC-10 dọn image/resources trong workload hiện tại.
2. SEC-11 triển khai admission policy ở audit/enforce mode có kiểm soát.
3. Mentor apply thử manifest vi phạm để thấy bị reject.
4. ADR ghi rõ rule nào enforce, rule nào audit và kế hoạch chuyển đổi.

Nếu bỏ qua SEC-10 và bật enforce ngay, deploy hợp lệ hiện tại có thể bị chặn bởi chính các initContainer `busybox:latest` hoặc container thiếu resources.

## 12. Kết luận

SEC-10 nên bắt đầu bằng PR nhỏ để pin initContainer `busybox` và xác nhận resource requests/limits toàn bộ workload.

Finding rõ nhất hiện tại:

- Có 5 initContainer dùng `busybox:latest`.
- Có 1 initContainer dùng `busybox` không tag rõ.
- Các initContainer này đã có requests/limits conservative.

Đề xuất baseline:

- Pin toàn bộ `busybox` initContainer về `busybox:1.36.1`.
- Giữ resources hiện tại nếu scan không phát hiện thiếu.
- Scan rendered manifests và runtime namespace trước khi SEC-11 bật admission enforce.

Cách tiếp cận này giữ đúng tinh thần Mandate 5: dọn hiện trạng trước, rồi mới bật guardrail tự động để manifest nguy hiểm không lọt vào cluster.
