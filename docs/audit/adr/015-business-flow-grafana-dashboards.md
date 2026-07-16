# ADR-015: Business Flow Grafana Dashboards cho OBS-01

- Ngày: 2026-07-16
- Trạng thái: Accepted - Implemented
- Người phụ trách: Trần Minh Quang - CDO07 Audit
- Stakeholder / Reviewer: CDO08 - Reliability/SLO owner
- Jira liên quan: AUDIT-011
- PR liên quan: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/187

## Bối Cảnh

Theo `docs/requirements/onboarding/ARCHITECTURE.md`, hệ thống TF4 có 5 business flow chính: browse, product review + AI, cart, checkout và post-checkout async. Trước thay đổi này, Grafana đã có datasource và dashboard nền tảng, nhưng góc nhìn chủ yếu vẫn là service-level/APM-level. Cách này chưa đủ thuận tiện để CDO08 theo dõi SLO/reliability theo luồng nghiệp vụ và chưa đủ rõ để CDO07 lưu evidence nghiệm thu OBS-01.

CDO08 là trụ liên quan trực tiếp tới reliability/SLO đã yêu cầu có dashboard theo business flow để theo dõi sức khỏe hệ thống, phát hiện suy giảm trong các flow quan trọng và hỗ trợ điều tra sự cố. CDO07 chịu trách nhiệm ghi nhận quyết định, bảo đảm evidence có thể truy vết từ repo, PR và runtime Grafana.

## Quyết Định

Chấp nhận và ghi nhận việc triển khai 3 Grafana dashboards theo business flow chính:

- `Business Flow Health Overview`: tổng quan 5 flow chính gồm browse, product review + AI, cart, checkout và post-checkout async.
- `Checkout Revenue Dashboard`: tập trung vào revenue-critical path, checkout success rate, request volume, latency, error rate và dependency path qua cart, product-catalog, currency, shipping/quote, payment, email và Kafka.
- `Product Review + AI Dashboard`: tập trung vào product-reviews, llm, PostgreSQL review query và tín hiệu AI error/rate-limit/fallback nếu hệ thống có metric/log tương ứng.

Ba dashboard được provision bằng JSON trong Helm chart tại:

- `techx-corp-chart/grafana/provisioning/dashboards/business-flow-health-overview.json`
- `techx-corp-chart/grafana/provisioning/dashboards/checkout-revenue-dashboard.json`
- `techx-corp-chart/grafana/provisioning/dashboards/product-review-ai-dashboard.json`

Dashboard sử dụng các datasource UID hiện có:

- `webstore-metrics`
- `webstore-traces`
- `webstore-logs`

Dashboard phục vụ quan sát, nghiệm thu và điều tra sự cố. Dashboard không thay thế alerting; các cảnh báo chủ động vẫn cần được cấu hình bằng Grafana/Prometheus alert rules và receiver riêng.

## Các Phương Án Đã Cân Nhắc

| Phương án | Ưu điểm | Nhược điểm | Kết luận |
| --- | --- | --- | --- |
| Chỉ dùng dashboard service-level/APM hiện có | Không cần thay đổi repo | Khó map trực tiếp sang 5 business flow; evidence OBS-01 không rõ theo luồng nghiệp vụ | Từ chối |
| Tạo dashboard thủ công trực tiếp trên Grafana | Nhanh, dễ thử nghiệm | Khó audit, khó review qua PR, có nguy cơ mất khi Grafana reset hoặc sync lại provisioning | Từ chối |
| Provision dashboard JSON qua Helm chart | Có audit trail qua Git/PR, tái lập được, phù hợp GitOps/Helm hiện tại | Cần deploy chart để dashboard xuất hiện trên Grafana; một số panel có thể No data nếu thiếu traffic hoặc thiếu instrumentation | Chấp nhận |

## Hệ Quả

- Tác động tích cực: CDO08 có góc nhìn vận hành theo business flow; CDO07 có evidence rõ ràng cho OBS-01, Ops Review và incident investigation.
- Tác động tích cực: thay đổi được review qua GitHub PR, có lịch sử commit và có thể rollback bằng Git/Helm.
- Đánh đổi: dashboard phụ thuộc vào spanmetrics, Kubernetes metrics, logs và traces đang có. Nếu app chưa emit đủ metric AI/Kafka/payment chi tiết, một số panel sẽ No data hoặc chỉ hiển thị ở mức gần đúng.
- Đánh đổi: dashboard không tự tạo alert. Nếu cần cảnh báo chủ động, phải bổ sung alert rules riêng.
- Rủi ro còn lại: Grafana/Prometheus/Jaeger/OpenSearch có vấn đề thì dashboard có thể mất dữ liệu hoặc không phản ánh đủ timeline sự cố.

## Kiểm Chứng / Evidence

- Ticket yêu cầu: `docs/audit/tickets/AUDIT-011-request-flow-health-grafana-dashboards.md`
- PR triển khai dashboard: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/187
- Runtime evidence sau deploy:
  - `docs/audit/postmortems/incident-20260715-checkout-cart-recommendation.md`
  - `docs/audit/postmortems/incident-20260715-grafana-business-flow-radar-1855-1910.png`
  - `docs/audit/postmortems/incident-20260715-grafana-business-flow-panels-1855-1910.png`
  - `docs/audit/postmortems/incident-20260715-grafana-traffic-service-callout-1855-1910.png`
- Đã kiểm chứng runtime: Có, dashboard đã xuất hiện trên Grafana và đã được dùng làm evidence trong điều tra sự cố ngày 2026-07-15.

## Rollback / Xem Xét Lại

Nếu dashboard gây lỗi provisioning hoặc gây nhầm lẫn khi nghiệm thu, rollback theo một trong các cách sau:

- Revert PR/commit đã thêm 3 file dashboard JSON nếu thay đổi chưa deploy.
- Nếu đã deploy bằng Helm, dùng `helm history techx-observability -n techx-observability` để tìm revision trước đó, sau đó rollback bằng `helm rollback techx-observability <revision> -n techx-observability`.
- Nếu triển khai qua GitOps/ArgoCD, revert source commit hoặc GitOps targetRevision về revision ổn định trước đó.

ADR này cần được xem xét lại khi:

- CDO08 thay đổi SLO threshold hoặc định nghĩa business flow.
- AIO01 bổ sung metric AI-specific như token usage, rate-limit, fallback hoặc quality/eval signal.
- Hệ thống chuyển từ in-cluster observability sang managed/long-retention observability.
- Alert rules được chuẩn hóa để gắn trực tiếp với từng business flow.

## Xác Nhận

- Người phụ trách: Trần Minh Quang - CDO07
- Stakeholder / Reviewer: CDO08
- Ngày: 2026-07-16
