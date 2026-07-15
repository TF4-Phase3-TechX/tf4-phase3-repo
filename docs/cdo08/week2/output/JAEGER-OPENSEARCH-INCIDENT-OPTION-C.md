# Jaeger/OpenSearch Incident - Option C Recovery Plan

**Date:** 2026-07-15  
**Namespace:** `techx-observability`  
**Scope:** Jaeger trace ingestion failure caused by OpenSearch disk watermark.

---

## 1. Summary

Jaeger is not failing because it needs a local PVC. Jaeger stores traces in OpenSearch:

```text
Jaeger -> http://opensearch:9200 -> PVC/opensearch-opensearch-0
```

The active incident is caused by OpenSearch disk pressure. The `8Gi` OpenSearch PVC is too small for the observed trace/log ingestion while retention keeps three days of data.

Runtime symptoms:

```text
Jaeger Restart Count: 26
Last State: OOMKilled
Jaeger memory: ~692Mi / 768Mi
OpenSearch disk: 7Gi used / 7.7Gi total, ~90.9%
OpenSearch PVC: 8Gi gp2
```

OpenSearch and Jaeger logs confirm:

```text
disk usage exceeded flood-stage watermark
index has read-only-allow-delete block
Jaeger bulk write failed with HTTP 429 cluster_block_exception
```

---

## 2. Evidence

Largest indices observed:

| Index | Size |
|-------|------|
| `jaeger-span-2026-07-14` | `3.1Gi` |
| `jaeger-span-2026-07-13` | `1.9Gi` |
| `otel-logs-2026-07-14` | `557.4Mi` |
| `jaeger-span-2026-07-15` | `502.9Mi` |
| `otel-logs-2026-07-13` | `288.9Mi` |
| `otel-logs-2026-07-15` | `92Mi` |

The Jaeger index cleaner exists and completes successfully, but current retention is `3` days:

```text
Indices before this date will be deleted: 2026-07-12
Queried indices: 2026-07-13, 2026-07-14
No indices to delete
```

This means the cleaner is not broken. The retention window and PVC capacity are not aligned with actual ingestion volume.

---

## 3. Option C Decision

Option C combines immediate recovery with GitOps prevention:

1. **Immediate recovery:** delete approved old indices to create disk headroom.
2. **GitOps fix:** increase OpenSearch PVC target size and reduce Jaeger trace retention.

This PR implements the GitOps part:

| Setting | Before | After |
|---------|--------|-------|
| `jaeger.esIndexCleaner.numberOfDays` | `3` | `1` |
| `opensearch.persistence.size` | `8Gi` | `20Gi` |

This intentionally does **not** just raise Jaeger memory. Jaeger OOM is a downstream symptom of OpenSearch refusing writes, not the root cause.

---

## 4. Runtime Recovery Command

The following runtime action still needs explicit operator approval because it deletes observability data. It is not performed by this GitOps change.

Recommended first cleanup target:

```bash
kubectl -n techx-observability exec opensearch-0 -- \
  curl -X DELETE 'http://localhost:9200/jaeger-span-2026-07-13,jaeger-service-2026-07-13,otel-logs-2026-07-13'
```

Then check disk headroom:

```bash
kubectl -n techx-observability exec opensearch-0 -- \
  curl -s 'http://localhost:9200/_cat/allocation?v'
```

Only after free space is available, clear the read-only block:

```bash
kubectl -n techx-observability exec opensearch-0 -- \
  curl -X PUT 'http://localhost:9200/_all/_settings' \
  -H 'Content-Type: application/json' \
  -d '{"index.blocks.read_only_allow_delete": null}'
```

Do not clear the block before freeing space. OpenSearch will set it again if the node is still over watermark.

---

## 5. Post-Deploy Verification

After GitOps applies the chart change, verify:

```bash
kubectl -n techx-observability get pvc opensearch-opensearch-0
kubectl -n techx-observability get cronjob jaeger-es-index-cleaner
kubectl -n techx-observability logs deploy/jaeger --tail=120
kubectl -n techx-observability get pod -l app.kubernetes.io/name=jaeger
```

OpenSearch API checks:

```bash
kubectl -n techx-observability exec opensearch-0 -- \
  curl -s 'http://localhost:9200/_cat/allocation?v'

kubectl -n techx-observability exec opensearch-0 -- \
  curl -s 'http://localhost:9200/_all/_settings?filter_path=**.blocks.read_only_allow_delete'

kubectl -n techx-observability exec opensearch-0 -- \
  curl -s 'http://localhost:9200/_cat/indices?v&s=store.size:desc'
```

Acceptance:

- OpenSearch disk usage is below the agreed operational threshold.
- No relevant index has `read_only_allow_delete=true`.
- Jaeger restart count stops increasing during the observation window.
- New traces are indexed after cleanup and block removal.
- Index cleaner keeps only the approved retention window.

---

## 6. Safety Constraints

- Do not delete `PVC/opensearch-opensearch-0`.
- Do not delete OpenSearch StatefulSet or EBS volume during recovery.
- Do not clear read-only blocks before freeing disk space.
- Do not treat increasing Jaeger memory as the primary fix.
- Do not delete current-day indices unless PM/mentor explicitly approves losing that evidence.
