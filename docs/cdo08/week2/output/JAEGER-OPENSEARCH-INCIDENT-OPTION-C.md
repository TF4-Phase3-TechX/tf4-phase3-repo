# Sự cố Jaeger/OpenSearch - Kế hoạch khôi phục Option C

**Ngày:** 2026-07-15  
**Namespace:** `techx-observability`  
**Phạm vi:** Jaeger không ghi được trace do OpenSearch chạm disk watermark.

---

## 1. Tóm tắt

Jaeger không lỗi vì thiếu PVC riêng. Jaeger đang lưu trace vào OpenSearch:

```text
Jaeger -> http://opensearch:9200 -> PVC/opensearch-opensearch-0
```

Sự cố hiện tại đến từ disk pressure của OpenSearch. PVC OpenSearch `8Gi` quá nhỏ so với lượng trace/log thực tế, trong khi retention đang giữ dữ liệu 3 ngày.

Triệu chứng runtime:

```text
Jaeger Restart Count: 26
Last State: OOMKilled
Jaeger memory: ~692Mi / 768Mi
OpenSearch disk: 7Gi used / 7.7Gi total, ~90.9%
OpenSearch PVC: 8Gi gp2
```

Log OpenSearch và Jaeger xác nhận:

```text
disk usage exceeded flood-stage watermark
index has read-only-allow-delete block
Jaeger bulk write failed with HTTP 429 cluster_block_exception
```

---

## 2. Bằng chứng

Các index lớn nhất đã quan sát được:

| Index | Size |
|-------|------|
| `jaeger-span-2026-07-14` | `3.1Gi` |
| `jaeger-span-2026-07-13` | `1.9Gi` |
| `otel-logs-2026-07-14` | `557.4Mi` |
| `jaeger-span-2026-07-15` | `502.9Mi` |
| `otel-logs-2026-07-13` | `288.9Mi` |
| `otel-logs-2026-07-15` | `92Mi` |

Jaeger index cleaner có tồn tại và chạy thành công, nhưng retention hiện tại là `3` ngày:

```text
Indices before this date will be deleted: 2026-07-12
Queried indices: 2026-07-13, 2026-07-14
No indices to delete
```

Điều này nghĩa là cleaner không hỏng. Vấn đề là retention window và dung lượng PVC không khớp với lượng dữ liệu ingest thực tế.

---

## 3. Quyết định Option C

Option C kết hợp khôi phục ngay và phòng ngừa bằng GitOps:

1. **Khôi phục ngay:** xóa các index cũ đã được approve để tạo disk headroom.
2. **GitOps fix:** tăng target size của OpenSearch PVC và giảm retention của Jaeger trace.

PR này triển khai phần GitOps:

| Setting | Before | After |
|---------|--------|-------|
| `jaeger.esIndexCleaner.numberOfDays` | `3` | `1` |
| `opensearch.persistence.size` | `8Gi` | `20Gi` |

PR này cố ý **không** chỉ tăng memory cho Jaeger. Jaeger OOM là hậu quả phía sau khi OpenSearch từ chối ghi, không phải root cause.

---

## 4. Lệnh khôi phục runtime

Các thao tác runtime dưới đây vẫn cần operator approve rõ ràng vì có xóa dữ liệu observability. GitOps change trong PR này không tự chạy các lệnh đó.

Target cleanup đầu tiên được đề xuất:

```bash
kubectl -n techx-observability exec opensearch-0 -- \
  curl -X DELETE 'http://localhost:9200/jaeger-span-2026-07-13,jaeger-service-2026-07-13,otel-logs-2026-07-13'
```

Sau đó kiểm tra disk headroom:

```bash
kubectl -n techx-observability exec opensearch-0 -- \
  curl -s 'http://localhost:9200/_cat/allocation?v'
```

Chỉ clear read-only block sau khi đã có free space:

```bash
kubectl -n techx-observability exec opensearch-0 -- \
  curl -X PUT 'http://localhost:9200/_all/_settings' \
  -H 'Content-Type: application/json' \
  -d '{"index.blocks.read_only_allow_delete": null}'
```

Không clear block trước khi giải phóng dung lượng. Nếu node vẫn vượt watermark, OpenSearch sẽ tự set block lại.

---

## 5. Kiểm tra sau deploy

Sau khi GitOps apply chart change, kiểm tra:

```bash
kubectl -n techx-observability get pvc opensearch-opensearch-0
kubectl -n techx-observability get cronjob jaeger-es-index-cleaner
kubectl -n techx-observability logs deploy/jaeger --tail=120
kubectl -n techx-observability get pod -l app.kubernetes.io/name=jaeger
```

Kiểm tra OpenSearch API:

```bash
kubectl -n techx-observability exec opensearch-0 -- \
  curl -s 'http://localhost:9200/_cat/allocation?v'

kubectl -n techx-observability exec opensearch-0 -- \
  curl -s 'http://localhost:9200/_all/_settings?filter_path=**.blocks.read_only_allow_delete'

kubectl -n techx-observability exec opensearch-0 -- \
  curl -s 'http://localhost:9200/_cat/indices?v&s=store.size:desc'
```

Acceptance:

- OpenSearch disk usage nằm dưới ngưỡng vận hành đã thống nhất.
- Không còn index liên quan nào có `read_only_allow_delete=true`.
- Jaeger restart count không tăng trong observation window.
- Trace mới được index sau khi cleanup và clear block.
- Index cleaner chỉ giữ retention window đã approve.

---

## 6. Ràng buộc an toàn

- Không xóa `PVC/opensearch-opensearch-0`.
- Không xóa OpenSearch StatefulSet hoặc EBS volume trong lúc recovery.
- Không clear read-only block trước khi giải phóng disk space.
- Không xem tăng memory Jaeger là fix chính.
- Không xóa index của ngày hiện tại trừ khi PM/mentor approve rõ việc mất evidence đó.
