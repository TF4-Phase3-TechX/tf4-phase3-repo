# CDO08-REL-28: Yêu Cầu AI Kiểm Tra Secret Cho Frontend

**Ngày phát hiện:** 2026-07-28  
**Cluster:** `techx-tf4-cluster`  
**Namespace:** `techx-tf4`  
**Workload:** `frontend`  
**Người gửi:** CDO08  
**Team cần xử lý:** AI / owner phần AI state HMAC secret  
**Mức độ:** Blocker trước Mandate 21 AZ-loss drill

## 1. Tóm tắt

Trong lúc CDO08 scan hệ thống để hoàn thành REL-28 cho Mandate 21, `frontend` đang chưa đạt trạng thái ổn định:

```text
deployment/frontend: desired 2, available 1
frontend pod mới: CreateContainerConfigError
```

Nguyên nhân trực tiếp từ `kubectl describe pod`:

```text
Error: secret "ai-state-hmac-secret" not found
```

Pod `frontend` hiện đang tham chiếu secret:

```text
AI_PRINCIPAL_HMAC_SECRET:
  secret name: ai-state-hmac-secret
  key: principal-hmac-secret
```

Vì secret này không tồn tại trong namespace `techx-tf4`, pod mới của `frontend` không start được.

## 2. Ảnh hưởng

Đây là blocker trước khi chạy Mandate 21 AZ-loss drill vì:

- `frontend` thuộc customer-facing revenue path.
- Deployment `frontend` hiện không đạt đủ `2/2 available`.
- Nếu mất AZ chứa pod frontend Ready còn lại, hệ có nguy cơ mất endpoint frontend trước khi Kubernetes tạo được pod thay thế.
- Drill Mandate 21 yêu cầu hệ thống không có `Pending`, `CreateContainerConfigError`, `CrashLoopBackOff` hoặc rollout lỗi trên workload trong scope trước khi bắt đầu.

## 3. Evidence đã kiểm tra

Lệnh kiểm tra:

```bash
kubectl -n techx-tf4 get deploy frontend
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=frontend
kubectl -n techx-tf4 describe pod <frontend-pod-dang-loi>
kubectl -n techx-tf4 get secret ai-state-hmac-secret
```

Kết quả quan trọng:

```text
frontend pod mới:
State: Waiting
Reason: CreateContainerConfigError

Events:
Warning Failed
Error: secret "ai-state-hmac-secret" not found
```

## 4. Yêu cầu xử lý từ team AI

AI team vui lòng xác nhận một trong hai hướng:

1. `frontend` vẫn cần `AI_PRINCIPAL_HMAC_SECRET`
   - Tạo/codify secret `ai-state-hmac-secret` trong namespace `techx-tf4`.
   - Secret phải có key `principal-hmac-secret`.
   - Nếu secret thuộc AWS Secrets Manager/External Secrets, cần tạo ExternalSecret tương ứng trong GitOps.

2. `frontend` không còn cần `AI_PRINCIPAL_HMAC_SECRET`
   - Gỡ env var này khỏi Helm values/template của `frontend`.
   - Rollout lại và verify `frontend` đạt `2/2 available`.

Không nên tạo secret live bằng tay làm trạng thái cuối nếu GitOps/ESO là source of truth. Có thể tạo tạm để unblock incident, nhưng cần PR codify sau đó.

## 5. Acceptance Criteria

- `kubectl -n techx-tf4 get secret ai-state-hmac-secret` trả về secret tồn tại, hoặc frontend manifest không còn tham chiếu secret này.
- `kubectl -n techx-tf4 rollout status deployment/frontend --timeout=180s` thành công.
- `kubectl -n techx-tf4 get deploy frontend` hiển thị đủ `2/2` available.
- Không còn pod `frontend` ở trạng thái `CreateContainerConfigError`.
- CDO08 có thể đánh dấu blocker REL-28/REL-35 preflight đã được xử lý.

## 6. Lệnh verify sau khi AI xử lý

```bash
kubectl -n techx-tf4 get deploy frontend
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=frontend
kubectl -n techx-tf4 describe pod -l app.kubernetes.io/component=frontend | grep -E 'CreateContainerConfigError|secret "ai-state-hmac-secret" not found' || true
kubectl -n techx-tf4 rollout status deployment/frontend --timeout=180s
```
