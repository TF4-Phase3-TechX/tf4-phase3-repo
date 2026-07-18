# CDO08-SEC-09 Runtime Hardening Guide

**Task:** `[CDO08-SEC-09][P0][Runtime] Remove root and privilege gaps from running workloads`  
**Owner chính:** Nhân  
**Pillar:** Security  
**Deadline mandate:** 17/07/2026  
**Scope:** workload trong namespace `techx-tf4` và `techx-observability`

## 1. Mục tiêu

Task này xử lý khoảng trống trước khi bật admission enforce cho Mandate 5: workload runtime không được chạy root nếu image hỗ trợ non-root, và container phải có baseline hardening rõ ràng.

Baseline tối thiểu cần đạt ở container-level:

```yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
  seccompProfile:
    type: RuntimeDefault
```

Không bật `readOnlyRootFilesystem` đại trà trong task này, vì nhiều image cần ghi cache, temp, data hoặc runtime files. Chỉ thêm sau khi đã audit write path của từng image.

## 2. Phạm vi và ranh giới

Workload runtime cần scan trong `techx-tf4`:

`accounting`, `ad`, `cart`, `checkout`, `currency`, `email`, `flagd`, `fraud-detection`, `image-provider`, `llm`, `load-generator`, `postgresql`, `product-catalog`, `recommendation`, `shipping`.

Workload observability cần scan trong `techx-observability`:

`jaeger`, `prometheus` và các container phụ của Prometheus như server, configmap reload, alertmanager nếu đang được render/deploy.

Out of scope:

- Không bật admission policy trong task này.
- Không đổi business logic app.
- Không thay đổi đường private access của Mandate 1.
- Không harden global một lần nếu chưa có evidence rollout an toàn.

## 3. Phân tích task

Rủi ro hiện tại:

- `techx-corp-chart/values.yaml` còn `default.securityContext: {}`, nên component không override sẽ render container không có runtime baseline.
- Nhiều workload trong `techx-tf4` chưa có container-level `securityContext`, hoặc mới có `runAsUser/runAsNonRoot` nhưng thiếu `allowPrivilegeEscalation`, `capabilities.drop` và `seccompProfile`.
- Observability dependency chart có thể không nhận default securityContext của app chart. Vì vậy Jaeger/Prometheus cần kiểm tra riêng theo value key của chart con.
- Một số image official như `postgres`, hoặc image cần ghi data có thể chạy non-root được nhưng cần UID/GID/fsGroup đúng với volume. Nếu áp sai UID có thể crash do permission.

Nguyên tắc xử lý:

- Ưu tiên workload stateless và image app tự build trước.
- Với stateful/data workload, audit UID/GID và volume ownership trước khi rollout.
- Mỗi batch rollout nhỏ, verify pods Ready và smoke checkout/storefront trước khi đi tiếp.
- Exception phải có lý do kỹ thuật, risk, owner và kế hoạch audit/enforce.

## 4. File cần kiểm tra

- `techx-corp-chart/values.yaml`: cấu hình default và từng component.
- `techx-corp-chart/templates/_objects.tpl`: render pod/container `securityContext`.
- `deploy/values-app-stamp.yaml`, `deploy/values-observability.yaml`, `deploy/values-aio-llm.yaml`: override runtime nếu đang dùng khi `helm upgrade`.
- Dockerfile dưới `techx-corp-platform/src/<service>/Dockerfile`: kiểm tra `USER`, write path, exposed port và thư mục runtime.

## 5. Bước 1 - Scan hiện trạng cluster

Chạy và lưu output raw:

```bash
kubectl -n techx-tf4 get deploy,sts -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":"}{.securityContext}{" | "}{end}{"\n"}{end}'
kubectl -n techx-observability get deploy,sts -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":"}{.securityContext}{" | "}{end}{"\n"}{end}'
```

Lấy thêm image và user đang chạy thực tế:

```bash
kubectl -n techx-tf4 get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.containers[*]}{.name}{":"}{.image}{" sc="}{.securityContext}{" | "}{end}{"\n"}{end}'
kubectl -n techx-observability get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.containers[*]}{.name}{":"}{.image}{" sc="}{.securityContext}{" | "}{end}{"\n"}{end}'
```

Với pod chưa rõ UID, kiểm tra bằng ephemeral command nếu image có shell:

```bash
kubectl -n techx-tf4 exec deploy/<workload> -- id
kubectl -n techx-observability exec deploy/<workload> -- id
```

Nếu image không có shell hoặc `id`, ghi `cannot exec id` và chuyển sang kiểm tra Dockerfile/image docs.

## 6. Bước 2 - Phân loại image

Tạo bảng phân loại trước khi patch:

| Namespace | Workload | Image | Evidence UID/GID | Nhóm | Quyết định |
| --- | --- | --- | --- | --- | --- |
| `techx-tf4` | `checkout` | `<image>` | Dockerfile/exec `id` | Non-root ready | Apply baseline |
| `techx-tf4` | `postgresql` | `postgres:17.6` | Cần verify UID/GID volume | Needs UID audit | Không đổi trước khi có test |
| `techx-observability` | `jaeger` | `<image>` | Chart docs/exec `id` | Needs chart-key mapping | Patch value chart con |

Nhóm phân loại:

- `Non-root ready`: Dockerfile có `USER` non-root hoặc service đã chạy được với UID cụ thể.
- `Needs UID/GID audit`: image official/stateful cần biết UID, GID, `fsGroup`, volume ownership.
- `Exception temporary`: chưa thể harden trong deadline vì crash risk hoặc thiếu owner/evidence.

## 7. Bước 3 - Patch chart app theo batch nhỏ

Với component app trong `techx-corp-chart/values.yaml`, thêm baseline ở từng workload phù hợp:

```yaml
components:
  checkout:
    securityContext:
      runAsNonRoot: true
      allowPrivilegeEscalation: false
      capabilities:
        drop:
          - ALL
      seccompProfile:
        type: RuntimeDefault
```

Nếu workload đã có UID/GID thì giữ lại và bổ sung baseline còn thiếu:

```yaml
securityContext:
  runAsUser: 1001
  runAsGroup: 1001
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
  seccompProfile:
    type: RuntimeDefault
```

Không nên chỉ đặt `default.securityContext` rồi rollout toàn bộ ngay. Có thể cập nhật default sau khi đã phân loại đủ image, nhưng rollout thực tế vẫn nên đi theo nhóm workload đã có evidence.

Init containers cũng cần kiểm tra. Trong chart này `_objects.tpl` có render securityContext cho init container từ default hoặc component value. Nếu init container dùng `busybox` để wait/copy config, cần test kỹ vì một số lệnh copy file vào mounted volume có thể cần UID phù hợp.

## 8. Bước 4 - Patch observability

Observability là dependency chart nên cần xem value key của từng chart con. Không giả định `default.securityContext` của app chart tự áp vào Jaeger/Prometheus.

Checklist:

- Render manifest trước bằng `helm template` và tìm `securityContext`.
- Với `jaeger`, tìm key chart hỗ trợ container security context cho Jaeger main container và cleaner job nếu bật.
- Với `prometheus`, kiểm tra server, alertmanager và configmap-reload container. Prometheus chart thường tách value cho `server.securityContext`, `server.containerSecurityContext`, `alertmanager.securityContext`, `configmapReload.prometheus.containerSecurityContext` tùy version.

Lệnh render gợi ý:

```bash
helm template techx techx-corp-chart -n techx-observability -f deploy/values-observability.yaml > /tmp/techx-observability-rendered.yaml
grep -n "securityContext\|name: prometheus\|name: jaeger" /tmp/techx-observability-rendered.yaml
```

Nếu không chắc chart key, dùng:

```bash
helm show values techx-corp-chart/charts/prometheus-29.6.0.tgz | grep -n "securityContext\|containerSecurityContext"
helm show values techx-corp-chart/charts/jaeger-4.7.0.tgz | grep -n "securityContext\|containerSecurityContext"
```

## 9. Bước 5 - Rollout an toàn

Thực hiện theo batch:

1. Batch 1: stateless app có Dockerfile rõ `USER` non-root hoặc đã chạy non-root.
2. Batch 2: workload có init container hoặc mounted config.
3. Batch 3: observability.
4. Batch 4: stateful/data workload sau khi đã xác nhận UID/GID và volume permission.

Mỗi batch:

```bash
helm upgrade <release> techx-corp-chart -n <namespace> -f <values-file>
kubectl -n <namespace> rollout status deploy/<workload> --timeout=180s
kubectl -n <namespace> get pods
kubectl -n <namespace> describe pod <pod-name>
kubectl -n <namespace> logs <pod-name> --tail=100
```

Nếu pod crash vì permission/UID:

```bash
kubectl -n <namespace> rollout undo deploy/<workload>
```

Hoặc rollback bằng commit/values trước đó và `helm upgrade` lại riêng workload/batch đó. Ghi exception ngay, không tiếp tục rollout global.

## 10. Bước 6 - Verify acceptance criteria

Verify securityContext:

```bash
kubectl -n techx-tf4 get deploy,sts -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":"}{.securityContext}{" | "}{end}{"\n"}{end}'
kubectl -n techx-observability get deploy,sts -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{":"}{.securityContext}{" | "}{end}{"\n"}{end}'
```

Verify không còn chạy root:

```bash
kubectl -n techx-tf4 get pods -o name | while read p; do echo "== $p =="; kubectl -n techx-tf4 exec "$p" -- id || true; done
kubectl -n techx-observability get pods -o name | while read p; do echo "== $p =="; kubectl -n techx-observability exec "$p" -- id || true; done
```

Smoke storefront và checkout:

```bash
kubectl -n techx-tf4 get ingress,svc
kubectl -n techx-tf4 get deploy checkout frontend frontend-proxy cart product-catalog currency shipping payment -o wide
kubectl -n techx-tf4 rollout status deploy/checkout --timeout=180s
kubectl -n techx-tf4 rollout status deploy/frontend --timeout=180s
kubectl -n techx-tf4 logs deploy/checkout --tail=100
```

Test luồng từ private/public path đang dùng trong team:

- Mở storefront, xem product list load được.
- Add to cart.
- Checkout thành công.
- Kiểm tra không tăng lỗi 5xx hoặc latency bất thường trên Grafana/Prometheus.

Verify observability:

- Grafana vẫn truy cập qua private access path.
- Prometheus query được metrics.
- Jaeger nhận trace checkout/frontend sau smoke test.

## 11. Exception log bắt buộc

Mọi workload chưa harden đủ phải có dòng exception:

| Namespace | Workload | Missing control | Lý do kỹ thuật | Risk | Owner | Kế hoạch xử lý | Deadline |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `techx-tf4` | `postgresql` | `runAsNonRoot`/UID chưa xác nhận | Cần audit UID/GID và PVC ownership trước khi đổi | Crash DB hoặc mất khả năng ghi data | Nhân + Nam | Test trên staging, xác nhận UID postgres, thêm `fsGroup`, rollout riêng | `<date>` |

Mẫu risk wording:

- `Risk`: container còn có thể chạy root hoặc thiếu drop capability, tăng blast radius nếu bị compromise.
- `Mitigation tạm thời`: không expose trực tiếp, NetworkPolicy/private path hiện hữu, monitor logs/alerts, rollout UID audit theo kế hoạch.
- `Enforce plan`: sau khi pass UID/GID audit và smoke test, remove exception rồi bật admission enforce ở task Mandate 5 riêng.

## 12. Evidence cần attach vào Jira

Nộp tối thiểu các phần sau:

1. Link PR/commit thay đổi Helm values/chart.
2. Output scan trước khi sửa cho `techx-tf4`.
3. Output scan trước khi sửa cho `techx-observability`.
4. Bảng phân loại image: non-root ready, needs UID/GID audit, exception.
5. Output `helm template` hoặc diff manifest cho các workload đã patch.
6. Output rollout status từng batch.
7. Output verify sau rollout bằng 2 lệnh jsonpath trong task.
8. Smoke test storefront/checkout: ảnh hoặc log kết quả.
9. Observability check: ảnh Grafana/Prometheus/Jaeger hoặc command output.
10. Exception log nếu còn workload chưa harden đủ.
11. Rollback note: ghi rõ có rollback hay không; nếu có, workload nào và lý do.

Gợi ý lưu evidence:

```text
docs/cdo08/week2/evidence/cdo08-sec-09-before-techx-tf4.txt
docs/cdo08/week2/evidence/cdo08-sec-09-before-observability.txt
docs/cdo08/week2/evidence/cdo08-sec-09-after-techx-tf4.txt
docs/cdo08/week2/evidence/cdo08-sec-09-after-observability.txt
docs/cdo08/week2/evidence/cdo08-sec-09-image-classification.md
docs/cdo08/week2/evidence/cdo08-sec-09-exceptions.md
docs/cdo08/week2/evidence/cdo08-sec-09-smoke-test.md
```

## 13. Nội dung comment nộp Jira

Copy mẫu này khi nộp:

```markdown
## CDO08-SEC-09 Evidence

Owner: Nhân
Reviewer/support: Nam rollout, Nguyên exception/risk review

### Change
- Added container runtime baseline for eligible workloads:
  - runAsNonRoot=true
  - allowPrivilegeEscalation=false
  - capabilities.drop=[ALL]
  - seccompProfile=RuntimeDefault
- Did not enable readOnlyRootFilesystem globally.
- Admission policy not changed in this task.

### Evidence
- PR/commit: <link>
- Before scan techx-tf4: <link/file>
- Before scan techx-observability: <link/file>
- After scan techx-tf4: <link/file>
- After scan techx-observability: <link/file>
- Image classification: <link/file>
- Rollout logs: <link/file>
- Storefront/checkout smoke test: <link/file>
- Observability verification: <link/file>
- Exceptions: <link/file or "None">

### Result
- Runtime workload no longer runs root where image supports non-root.
- Remaining exceptions are documented with reason, risk, owner and audit-to-enforce plan.
- Storefront and checkout smoke test passed.
- Mandate 1 private access path unchanged.
```

## 14. Definition of Done checklist

- [ ] Before scan captured for `techx-tf4`.
- [ ] Before scan captured for `techx-observability`.
- [ ] Image classification completed.
- [ ] Eligible app workloads patched with baseline.
- [ ] Init containers reviewed.
- [ ] Jaeger securityContext reviewed/patched.
- [ ] Prometheus container-level securityContext reviewed/patched.
- [ ] Rollout done by small batch.
- [ ] After scan shows expected securityContext.
- [ ] Storefront smoke test passed.
- [ ] Checkout smoke test passed.
- [ ] Grafana/Prometheus/Jaeger still working.
- [ ] Exceptions documented with owner and deadline.
- [ ] Jira comment submitted with links/evidence.
- [ ] Owner confirms acceptance criteria.
- [ ] PM updates backlog status.
