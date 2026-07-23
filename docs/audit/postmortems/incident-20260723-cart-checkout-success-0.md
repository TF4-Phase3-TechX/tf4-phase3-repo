# Báo cáo sự cố: Cart Success và Checkout Success về 0%

Ngày ghi nhận: 2026-07-23  
Namespace: `techx-tf4`  
Hệ thống bị ảnh hưởng: `cart`, `checkout`, `frontend`, business flow metrics  
Mức độ: High  
Trạng thái: Đã xác định root cause  
Người tạo báo cáo: Trần Minh Quang

## 1. Tóm tắt ngắn gọn

Grafana ghi nhận hai chỉ số `Cart Success` và `Checkout Success` cùng về `0%`.

Chốt nguyên nhân theo chuỗi:

1. PR GitOps `#63` do `2hm1901` / `haihm191` approve và merge đã làm production cart đổi sang tag `0f983db-cart` và thêm digest `sha256:4b6d...`.
2. Digest này không tồn tại trong ECR, nhưng lỗi chưa bùng ra ngay vì các pod cart cũ vẫn còn chạy.
3. Promotion cho source commit `36de18a` từ PR `#373`, author `DVQuyet`, làm Kubernetes tạo lại pod cart.
4. Khi Kubernetes tạo pod cart mới, Kyverno kiểm tra image digest.
5. ECR trả `MANIFEST_UNKNOWN`, Kyverno deny pod create.
6. Cart mất toàn bộ backend endpoint, nên `Cart Success` về `0%`.
7. Checkout phụ thuộc vào cart để đọc giỏ hàng, nên `Checkout Success` cũng về `0%`.

Nguyên nhân trực tiếp ở thời điểm dashboard tụt là service `cart` không còn pod backend nào để nhận request. Kubernetes service `cart` vẫn tồn tại, nhưng endpoint rỗng, nên `frontend` và `checkout` gọi đến `cart:8080` bị `connection refused`.

Cart không tạo được pod mới vì Kyverno admission policy chặn image:

```text
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:0f983db-cart@sha256:4b6d4958d2fdbeb4862b5d83965d754a3b4551b3c9fd44e58eda2f350374ce28
```

ECR trả về:

```text
MANIFEST_UNKNOWN: Requested image not found
```

Nói cách khác: production đã bị pin sẵn tới một image digest không tồn tại trong ECR. Lỗi này nằm im cho đến khi pod cart được tạo lại. Lúc đó Kyverno verify image và deny pod create.

## 2. Ảnh hưởng người dùng

- Người dùng không thêm/xem giỏ hàng thành công.
- Checkout thất bại vì checkout phụ thuộc vào cart để đọc giỏ hàng.
- Trên dashboard:
  - `Cart Success`: 0%
  - `Checkout Success`: 0%
- Các request đi qua frontend có lỗi kết nối tới cart.

## 3. Dấu hiệu trên cluster

Service `cart` còn tồn tại nhưng không có endpoint:

```text
service/cart -> ClusterIP 172.20.148.103:8080
endpoints/cart -> <none>
```

ReplicaSet của cart không tạo được pod:

```text
cart-54885469b4 desired=2 current=0 ready=0
cart-687f55867 desired=2 current=0 ready=0
```

Event Kubernetes báo Kyverno deny:

```text
admission webhook "ivpol.validate.kyverno.svc-fail-finegrained-require-signed-techx-images" denied the request
Policy require-signed-techx-images error
GET https://511825856493.dkr.ecr.us-east-1.amazonaws.com/v2/techx-corp/manifests/sha256:4b6d4958...
MANIFEST_UNKNOWN: Requested image not found
```

Frontend log:

```text
Error: 14 UNAVAILABLE: No connection established
connect ECONNREFUSED 172.20.148.103:8080
```

Checkout failure được lan truyền từ cart:

```text
cart failure: failed to get user cart during checkout
dial tcp 172.20.148.103:8080: connect: connection refused
```

## 4. Root cause

Root cause là GitOps production image pin sai cho `cart`.

Điểm quan trọng: lỗi không xảy ra chỉ vì "đổi tag". Lỗi xảy ra vì promotion cho source commit `0f983db` đổi tag và đồng thời thêm digest không tồn tại trong ECR. Với image dạng `tag@digest`, digest là phần quyết định image thật sự được kéo/verify.

File bị ảnh hưởng:

```text
environments/production/image-revisions.yaml
```

Dòng image cart hiện tại trỏ tới:

```text
tag: "0f983db-cart"
digest: "sha256:4b6d4958d2fdbeb4862b5d83965d754a3b4551b3c9fd44e58eda2f350374ce28"
```

Digest này không tồn tại trong ECR, nên bất kỳ pod cart mới nào được tạo sẽ bị admission policy chặn. Các pod cũ nếu đã chạy trước đó thì không bị kiểm tra lại, vì Kyverno admission chạy khi pod được `CREATE` hoặc `UPDATE`.

## 5. PR liên quan

```text
Vai trò: PR GitOps đưa digest cart lỗi vào production
PR: #63
Repo: tf4-phase3-gitops-manifests
GitOps commit: d4bf3de5797835c1c8b7e017b403cbbc11617a37
Time: 2026-07-21 09:18:39 +0700
Approved by: 2hm1901 / haihm191
Merged by: 2hm1901 / haihm191
Subject: chore(gitops): promote 0f983db (#63)
```

Ghi chú: PR `#63` được bot tạo từ promotion workflow, nhưng bằng chứng trên GitHub PR cho thấy người approve và merge thay đổi là `2hm1901` / `haihm191`. Source commit `0f983db` trong PR body chỉ là metadata được promotion dùng để đặt tag image; không phải người trực tiếp merge thay đổi GitOps production.

Thay đổi GitOps phát sinh từ promotion này:

```diff
 cart:
   imageOverride:
-    tag: "8340af1-cart"
+    tag: "0f983db-cart"
+    digest: "sha256:4b6d4958d2fdbeb4862b5d83965d754a3b4551b3c9fd44e58eda2f350374ce28"
```

```text
Vai trò: PR GitOps làm lỗi tiềm ẩn bùng ra
PR: #142
Repo: tf4-phase3-gitops-manifests
GitOps commit: 1322756e8ec58c7fca1892d1fd31cbad2778925f
Time: 2026-07-23 14:21:09 +0700
Subject: chore(gitops): promote 36de18a (#142)
```

Promotion sau commit `36de18a` làm pod cart được tạo lại. Khi pod mới được tạo, Kyverno kiểm tra image digest đã bị pin từ promotion của `0f983db`, rồi phát hiện digest không tồn tại trong ECR.

Kết luận về trách nhiệm kỹ thuật:

- PR GitOps `#63` là PR trực tiếp đưa digest cart không tồn tại vào production.
- Người approve và merge PR `#63`: `2hm1901` / `haihm191`.
- PR GitOps `#142` là PR làm lỗi tiềm ẩn bùng ra vì pod cart được tạo lại.
- Nếu cần xác định người trực tiếp bấm workflow/promotion trước khi PR được tạo, cần xem GitHub Actions run hoặc GitHub audit log của promotion tương ứng.

### Cách truy vết commit/PR chi tiết

Thông tin PR/commit GitOps nằm trong repo GitOps `tf4-phase3-gitops-manifests`.

Các lệnh kiểm tra lại khi đang đứng trong repo GitOps:

```powershell
git show --date=iso --stat --patch d4bf3de5797835c1c8b7e017b403cbbc11617a37 -- environments/production/image-revisions.yaml
git show --date=iso --stat --patch 1322756e8ec58c7fca1892d1fd31cbad2778925f -- argocd/root-resources/applications.yaml
```

Thông tin source commit được promotion nhắc tới nằm trong repo chính `tf4-phase3-repo`.

Các lệnh kiểm tra lại khi đang đứng trong repo chính:

```powershell
git show --name-status --date=iso 0f983db6357072ad33ffe652bb81af6b0e9c0abe
git show --name-status --date=iso 36de18aac39d185518aacdd81953de09c15486b3
```

PR GitOps liên quan:

```text
#63  - 2hm1901 / haihm191 - approved and merged digest change for cart
#142 - promotion for 36de18a - made cart pod get recreated
```

## 6. Timeline

| Thời gian ICT | Sự kiện |
| --- | --- |
| 2026-07-20 01:12 | Kyverno signed image admission policy được thêm vào GitOps với `validationActions: [Deny]`. |
| 2026-07-22 14:37 | Namespace `techx-tf4` bật label enforce signature/digest. |
| 2026-07-21 09:18 | PR GitOps `#63` được `2hm1901` / `haihm191` approve và merge, cập nhật cart sang `0f983db-cart` với digest `sha256:4b6d...`. Digest này không tồn tại trong ECR. Đây là lỗi gốc, nhưng có thể chưa gây outage ngay vì pod cart cũ vẫn còn chạy. |
| 2026-07-23 14:19 | PR/source commit `#373` của `DVQuyet` được merge. |
| 2026-07-23 14:21 | Promotion cho source commit `36de18a` làm pod cart được tạo lại. |
| 2026-07-23 14:21+ | Kubernetes tạo pod cart mới, Kyverno verify image `0f983db-cart@sha256:4b6d...`. |
| 2026-07-23 14:21+ | ECR không tìm thấy digest và trả `MANIFEST_UNKNOWN`; Kyverno deny pod cart mới. |
| 2026-07-23 14:21+ | `cart` không có endpoint, frontend/checkout gọi cart bị `connection refused`. |
| 2026-07-23 14:21+ | Grafana hiển thị `Cart Success = 0%`, `Checkout Success = 0%`. |

## 7. Vì sao Checkout Success cũng về 0%

Checkout phụ thuộc vào cart.

Luồng request checkout:

```text
frontend -> checkout -> cart
```

Khi checkout cần đọc giỏ hàng, nó gọi cart. Vì cart không có pod endpoint, call này bị lỗi. Checkout không thể hoàn tất order, nên `Checkout Success` về `0%`.

Đây là lỗi dây chuyền, không phải checkout service bị crash.

## 8. Không phải root cause

`flagd` đang CrashLoopBackOff do timeout khi tải:

```text
https://122.248.223.194.sslip.io/flags.json
```

Đây là vấn đề riêng về feature flag/config source. Nó cần sửa, nhưng không phải nguyên nhân trực tiếp làm `Cart Success` và `Checkout Success` về `0%`.

## 9. Cách khắc phục để khôi phục dịch vụ

Ưu tiên rollback/pin lại cart image về digest đã tồn tại và đã được sign.

Lựa chọn an toàn nhất:

1. Kiểm tra digest hợp lệ gần nhất của cart trong ECR, ví dụ tag cũ `8340af1-cart`.
2. Sửa `environments/production/image-revisions.yaml` để cart trỏ về tag/digest hợp lệ.
3. Merge GitOps PR.
4. Chờ ArgoCD sync.
5. Xác nhận:
   - `kubectl get pods -n techx-tf4 -l app.kubernetes.io/component=cart`
   - `kubectl get endpoints -n techx-tf4 cart`
   - Grafana `Cart Success` và `Checkout Success` phục hồi.

Không nên tắt Kyverno Deny nếu chưa cần thiết, vì policy đang làm đúng việc: chặn image không tồn tại/không verify được.

## 10. Hành động phòng ngừa

- Promotion workflow phải verify digest tồn tại trong ECR trước khi tạo GitOps PR.
- Promotion workflow phải fail nếu source commit là docs-only nhưng vẫn promote service image.
- Trước khi merge GitOps image promotion, chạy preflight:
  - `aws ecr describe-images` cho từng tag/digest.
  - `cosign verify` cho từng digest.
  - Render Helm chart và kiểm tra image reference đầy đủ tag + digest.
- Thêm canary/health gate sau Argo sync:
  - cart endpoint không rỗng.
  - checkout synthetic test thành công.
  - rollback tự động nếu cart endpoint rỗng quá ngưỡng thời gian.
- Lưu lại GitHub Actions run id vào commit message hoặc file promotion metadata để truy ngược được người/manual dispatch.

## 11. Kết luận

Sự cố không bắt đầu từ lỗi runtime của cart hay checkout. Sự cố bắt đầu từ PR GitOps `#63`, được `2hm1901` / `haihm191` approve và merge, làm GitOps pin sai cart image digest. Lỗi bị ẩn trong production vì pod cart cũ vẫn còn chạy.

Đến promotion cho source commit `36de18a` của PR `#373`, author `DVQuyet`, pod cart được tạo lại. Pod mới phải verify image. Kyverno hỏi ECR về digest `sha256:4b6d...`, ECR không tìm thấy digest và trả `MANIFEST_UNKNOWN`, nên Kyverno chặn pod mới. Cart mất toàn bộ endpoint. Checkout thất bại theo vì phụ thuộc vào cart.

PR GitOps cần truy vết đầu tiên:

```text
#63 - 2hm1901 / haihm191 - approved and merged d4bf3de
```

Source PR/commit kích hoạt outage:

```text
#373 - 36de18a - DVQuyet
```
