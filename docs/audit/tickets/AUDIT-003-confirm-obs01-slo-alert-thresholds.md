# [AUDIT-003] Xác nhận ngưỡng SLI/Alert bổ sung cho OBS-01 SLO Alerts

**Trạng thái**: TO DO  
**Người yêu cầu (Reporter)**: Trần Minh Quang - Nhóm CDO07 (Audit)  
**Người thực hiện (Assignee)**: Nhóm CDO08 (Reliability/Security)  
**Nhóm phối hợp**: Nhóm CDO04 (Observability/Platform, nếu cần triển khai Grafana/Alertmanager)  
**Độ ưu tiên (Priority)**: P0 (Blocker nghiệm thu OBS-01)  
**Epic**: EPIC-01 / OBS-01 - Observability baseline

---

## 1. Bối cảnh (Context)

Trong task OBS-01, team CDO07 cần nghiệm thu việc bổ sung SLI queries, Grafana alerts và Alertmanager/Slack receiver cho các tín hiệu trọng tâm:

- checkout success/latency
- payment error/latency
- Kafka producer/consumer health
- PostgreSQL/DB saturation

Tài liệu SLO hiện tại đã có baseline SLO cho các luồng chính tại `docs/requirements/onboarding/SLO.md`, ví dụ:

- Browse non-5xx >= 99.5%
- Browse p95 latency < 1s
- Cart success >= 99.5%
- Checkout success >= 99.0%
- AI summary best-effort, không được hiển thị tóm tắt sai lệch

Tuy nhiên, OBS-01 cần thêm ngưỡng vận hành cụ thể cho alert rule. Các ngưỡng này không thay thế SLO baseline của BTC, mà dùng để quyết định khi nào Grafana/Alertmanager phải cảnh báo on-call.

Gap này đã được ghi nhận trong `docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md`: repo hiện chỉ có cart add-item latency alert, chưa có checkout/payment/Kafka/DB SLO alerts và Prometheus Alertmanager đang disabled.

## 2. Yêu cầu xác nhận từ CDO08 (The What)

Team CDO08 vui lòng xác nhận hoặc chỉnh sửa bộ ngưỡng alert đề xuất dưới đây để CDO07 dùng làm căn cứ nghiệm thu OBS-01.

| Component | SLI / Signal | Proposed warning | Proposed critical | Ghi chú |
|---|---|---:|---:|---|
| Checkout | Success rate | < 99.5% trong 10m | < 99.0% trong 10m | Checkout SLO chính thức là >= 99.0%; warning sớm để tránh burn error budget |
| Checkout | p95 latency | > 1s trong 10m | > 3s trong 5m | 1s lấy theo browse latency baseline; CDO08 cần xác nhận có áp dụng cho checkout không |
| Payment | Error rate | > 1% trong 10m | > 5% trong 5m | Payment là dependency trực tiếp của checkout |
| Payment | p95 latency | > 1s trong 10m | > 3s trong 5m | Cần xác nhận theo baseline runtime |
| Kafka | Consumer lag | > 100 messages trong 10m | > 1000 messages trong 10m | Áp dụng cho consumer groups `accounting` và `fraud-detection` nếu metric available |
| Kafka | Producer/send failures | > 0 sustained trong 5m | > 0 sustained trong 10m | Vì checkout order event là revenue/audit-critical |
| PostgreSQL | Connection saturation | > 80% | > 90% | Nếu không có max connection metric trực tiếp, dùng available proxy signal được CDO08 approve |
| PostgreSQL | Deadlocks/conflicts | > 0 trong 5m | > 0 trong 10m | Bất kỳ deadlock sustained nào cần điều tra |
| PostgreSQL | Cache hit ratio | < 95% trong 10m | < 90% trong 10m | Cần xác nhận có phù hợp với workload hiện tại không |

CDO08 có thể chọn một trong hai hướng:

1. Approve bảng trên để CDO04/CDO07 triển khai Grafana alerts.
2. Trả lại bảng threshold chính thức khác, kèm lý do.

## 3. Ranh giới trách nhiệm

- CDO08 owns quyết định reliability threshold và severity.
- CDO04 owns phần platform/observability implementation nếu cần sửa Helm/Grafana/Alertmanager.
- CDO07 owns audit/evidence: kiểm tra threshold đã được xác nhận, alert tồn tại, receiver hoạt động, và evidence được lưu đúng file.

## 4. Tiêu chí nghiệm thu (Acceptance Criteria / Evidence)

- [ ] CDO08 xác nhận bảng threshold cuối cùng cho checkout/payment/Kafka/PostgreSQL.
- [ ] Threshold có phân biệt warning/critical hoặc có lý do nếu chỉ dùng một mức.
- [ ] CDO08 xác nhận cửa sổ đo/evaluation window cho từng alert.
- [ ] CDO08 xác nhận Slack channel/receiver hoặc escalation path mong muốn cho OBS-01.
- [ ] Nếu threshold khác proposal, có ghi chú lý do để CDO07 lưu evidence.
- [ ] CDO07 có thể tham chiếu quyết định này trong evidence file `006-obs-01-slo-alert-dashboard-baseline.md`.

## 5. Ghi chú cho implementation sau khi được approve

Sau khi CDO08 xác nhận, nhóm triển khai cần:

- Viết PromQL/Grafana alert rules dựa trên datasource `webstore-metrics`.
- Bổ sung dashboard/panel nếu cần để hiển thị SLI hiện tại.
- Cấu hình Alertmanager hoặc Grafana contact point gửi Slack.
- Fire test alert và lưu screenshot Slack vào evidence.

*(Sau khi hoàn thành, vui lòng tag team CDO07 để nghiệm thu evidence OBS-01.)*

