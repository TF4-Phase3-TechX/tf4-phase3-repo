# ADR-016: Cost dashboard estimate-first trước khi đồng bộ chi phí thực tế

- Ngày: 2026-07-16
- Trạng thái: Đã chấp nhận
- Người phụ trách: CDO-07
- Jira: N/A
- PR liên quan: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/204
- Dashboard liên quan: `techx-corp-chart/grafana/provisioning/dashboards/cost-dashboard.json`

## Bối Cảnh

Hệ thống TF4 cần một Grafana cost dashboard để team nhanh chóng nắm được trạng thái chi phí hiện tại, ước tính chi phí baseline, và các workload/cost driver chính trong cụm EKS.

Tại thời điểm triển khai dashboard, nguồn dữ liệu runtime sẵn có là Prometheus/Kubernetes metrics từ EKS và observability stack. Dữ liệu AWS billing thực tế chưa được đưa vào Grafana. Nếu thêm actual billing ở phase này thì cần mở rộng IAM permission, thêm luồng ingest dữ liệu, và kiểm soát việc gọi Cost Explorer/CUR/Athena để tránh phát sinh query cost không cần thiết.

PR #204 đã thêm dashboard `Cost Overview and EKS Allocation` theo hướng chỉ triển khai dashboard. Dashboard hiển thị ước tính AWS baseline và tín hiệu phân bổ chi phí EKS, nhưng chưa đọc Cost Explorer hoặc CUR.

## Quyết Định

Chọn hướng estimate-first cho phase đầu của cost visibility.

Dashboard sẽ:

- Hiển thị ước tính chi phí cố định baseline cho footprint AWS/EKS hiện tại.
- Phân bổ estimated EKS compute cost theo workload dựa trên CPU usage share từ Prometheus.
- Hiển thị các cost driver như ready worker nodes, workload memory, observability memory, load-generator activity, và node pressure.
- Ghi rõ các giá trị trong dashboard là estimate, không phải actual AWS billing.

Phase đầu sẽ không thêm:

- Cost Explorer API calls.
- CUR/Athena query flow.
- CronJob billing sync.
- IAM/IRSA permission mới cho billing APIs.
- Thành phần runtime mới ngoài Grafana dashboard ConfigMap.

Actual billing sẽ được triển khai ở phase sau theo hướng sync 1 lần/ngày nếu team duyệt nhu cầu billing visibility.

## Các Phương Án Đã Cân Nhắc

| Phương án | Ưu điểm | Nhược điểm | Kết luận |
| --- | --- | --- | --- |
| Dashboard estimate-first | Triển khai nhanh, không cần IAM mới, không phát sinh billing API query cost, rollback dễ qua Grafana dashboard provisioning | Không phải actual AWS bill, chi phí dịch vụ ngoài EKS vẫn là estimate hoặc gap note | Chấp nhận |
| Query Cost Explorer trực tiếp từ dashboard/backend | Có actual billing visibility | Tốn phí theo request, cần IAM, dễ phát sinh query cost do dashboard refresh nhiều lần | Từ chối cho phase 1 |
| Daily Cost Explorer sync sang cached metrics | Có actual billing và kiểm soát số lần gọi API | Cần CronJob/service, IAM, metric export, và phạm vi test riêng | Defer |
| CUR + Athena reporting | Phân tích cost chi tiết và reconcile lịch sử tốt hơn | Setup lớn hơn, có storage/query cost, vận hành phức tạp hơn | Defer |

## Hệ Quả

- Tác động tích cực: Team có cost visibility ban đầu ngay trong Grafana mà không cần thay đổi runtime ứng dụng hoặc AWS IAM.
- Tác động tích cực: Dashboard có rủi ro thấp vì được provision bằng Grafana dashboard ConfigMap.
- Tác động tích cực: Phase này không phát sinh Cost Explorer/CUR query cost.
- Đánh đổi: Dashboard chưa thể dùng làm nguồn sự thật cho invoice-level AWS billing.
- Đánh đổi: NAT data processing, ALB LCU, ECR storage, CloudWatch ingest, data transfer, và exact EBS/PVC billing vẫn nằm ngoài actual-cost view cho tới khi có billing sync.
- Rủi ro còn lại: Người xem có thể hiểu nhầm estimate là actual billing nếu phần note và mô tả panel bị bỏ qua.

## Kiểm Chứng / Evidence

- Dashboard file: `techx-corp-chart/grafana/provisioning/dashboards/cost-dashboard.json`
- PR: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/204
- Merge commit: `09d0caf feat(cdo07): add cost dashboard (#204)`
- Runtime ConfigMap kỳ vọng: `grafana-dashboard-cost-dashboard` trong namespace `techx-observability`
- Kiểm chứng runtime: Chờ evidence sau khi GitOps/Argo sync chart revision đã merge.

Evidence đề xuất khi nghiệm thu:

- Screenshot hoặc command output của `kubectl -n techx-observability get cm grafana-dashboard-cost-dashboard`.
- Screenshot Grafana dashboard list có `Cost Overview and EKS Allocation`.
- Screenshot trang detail của dashboard với các panel estimate đã render.

## Rollback / Xem Xét Lại

Rollback bằng cách remove `cost-dashboard.json` khỏi Grafana provisioning và để GitOps/Helm xóa dashboard ConfigMap tương ứng.

Xem xét lại ADR này khi:

- Team duyệt nhu cầu actual billing visibility.
- IAM permission như `ce:GetCostAndUsage` được cấp.
- Thiết kế daily billing sync đã sẵn sàng.
- Người dùng dashboard cần invoice-level service cost thay vì estimate.

Hướng tiếp theo được ưu tiên là một PR riêng cho Cost Explorer sync 1 lần/ngày, export cached billing metrics sang Prometheus hoặc nguồn dữ liệu mà Grafana đọc được.

## Xác Nhận

- Người phụ trách: CDO-07
- Reviewer: TBD
- Ngày: 2026-07-16
