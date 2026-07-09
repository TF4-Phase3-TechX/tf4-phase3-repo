# Epic 07 - Security Scan Findings

**Owner:** CDO08  
**Pillar:** Security  
**Scan time:** 2026-07-09 09:31 ICT  
**Environment:** EKS `techx-tf4-cluster`, namespace `techx-tf4`  
**Purpose:** Tổng hợp các lỗ hổng/gap bảo mật hiện tại để đưa vào Jira tổng và backlog tuần sau.

## Scope

Scan này tập trung vào các rủi ro bảo mật có evidence từ source/chart hoặc runtime:

- Secret/config nhạy cảm trong Helm values.
- Grafana/OpenSearch security posture.
- Network exposure risk khi observability hoặc admin UI được expose.

## Runtime Context

App hiện đang chạy trong namespace `techx-tf4`.

Commands đã kiểm tra:

```bash
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get svc grafana prometheus jaeger opensearch otel-collector
```

Kết quả chính:

- App pods trong `techx-tf4` đang `Running 1/1`.
- `grafana`, `prometheus`, `jaeger`, `opensearch`, `otel-collector` không còn service trong namespace `techx-tf4` tại thời điểm scan.

## Findings

| ID | Finding | Evidence | Impact | Priority gợi ý | Backlog candidate |
|---|---|---|---|---|---|
| SEC-01 | Hardcoded DB credentials/API key trong Helm values | `techx-corp-chart/values.yaml:182-183`, `581-582`, `618-619`, `600-601`, `870-871` chứa DB password/API key/config nhạy cảm | Secret/config nhạy cảm nằm trong repo; dễ lộ qua Git/diff/PR; khó rotate an toàn | P1 | Migrate sensitive config sang Kubernetes Secret hoặc secret manager phù hợp |
| SEC-02 | Grafana anonymous user có quyền Admin nếu Grafana được expose lại | `techx-corp-chart/values.yaml:1190-1193` bật anonymous và `org_role: Admin`; `1197` có `adminPassword: admin` | Nếu Grafana được expose qua ALB/path, người ngoài có thể có quyền admin dashboard/datasource | P1; P0 nếu public expose được xác nhận | Tắt anonymous Admin, đổi admin password, giới hạn access Grafana |
| SEC-03 | OpenSearch security plugin disabled | `techx-corp-chart/values.yaml:1227-1230` có `DISABLE_SECURITY_PLUGIN=true` | Logs/traces có thể không được bảo vệ ở layer OpenSearch; rủi ro cao hơn nếu network exposure sai | P1/P2 | Bật security plugin hoặc giới hạn network access chặt hơn |

## Evidence Details

### SEC-01 - Hardcoded credentials/config

Các vị trí cần review:

- `techx-corp-chart/values.yaml:182-183`: `DB_CONNECTION_STRING` chứa username/password.
- `techx-corp-chart/values.yaml:581-582`: product catalog DB connection string chứa password.
- `techx-corp-chart/values.yaml:618-619`: product reviews DB connection string chứa password.
- `techx-corp-chart/values.yaml:600-601`: `OPENAI_API_KEY` đang có value `dummy`.
- `techx-corp-chart/values.yaml:870-871`: `POSTGRES_PASSWORD` hardcoded.

Việc cần làm tuần sau:

- Phân loại item nào là secret thật, item nào chỉ là demo/dummy.
- Chọn migration candidates có rủi ro cao nhất.
- Đề xuất rollback path trước khi migrate.

### SEC-02 - Grafana anonymous Admin

Evidence:

```yaml
auth.anonymous:
  enabled: true
  org_role: Admin
adminPassword: admin
```

Việc cần làm tuần sau:

- Xác nhận Grafana đang deploy ở namespace nào.
- Xác nhận Grafana có public route/path qua ALB không.
- Nếu public exposure tồn tại, nâng priority lên P0.

### SEC-03 - OpenSearch security disabled

Evidence:

```yaml
- name: "DISABLE_SECURITY_PLUGIN"
  value: "true"
```

Việc cần làm tuần sau:

- Xác nhận OpenSearch chỉ internal hay có route/access path khác.
- Nếu cần giữ plugin disabled cho demo, phải có network restriction rõ ràng.

## Suggested Backlog Items

| Backlog ID | Title | Suggested Owner | Priority |
|---|---|---|---|
| SEC-BL-01 | Move hardcoded DB credentials from Helm values to Secret-backed config | Thủy + Nhân + Deploy Operator | P1 |
| SEC-BL-02 | Disable Grafana anonymous Admin and rotate default admin password | Quyết + Nhân | P1/P0 nếu expose public |
| SEC-BL-03 | Review OpenSearch security posture and network exposure | Quyết + Nhân | P1/P2 |

## Notes For Jira Epic

Security Week 1 scan đã tìm thấy các rủi ro có thể đưa vào backlog tuần sau: hardcoded credentials, Grafana anonymous Admin, và OpenSearch security disabled. Các item cần được validate thêm bằng runtime evidence trước khi triển khai thay đổi, đặc biệt với Grafana/OpenSearch exposure.
