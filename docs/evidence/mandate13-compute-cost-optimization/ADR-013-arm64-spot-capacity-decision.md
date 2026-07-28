# ADR-013 — Quyết định Kiến trúc Capacity ARM64 & Spot đi kèm Đánh đổi Reliability với Mandate 21

## Trạng thái
**ĐÃ CHẤP NHẬN / ĐÃ KÝ (ACCEPTED / SIGNED)**

## Ngày
28/07/2026

## Bối cảnh & Đặt vấn đề
Epic-09 Directive #13 đặt mục tiêu cắt giảm đáng kể chi phí compute EKS bằng cách đưa các workload phù hợp lên Spot instances và kiến trúc Graviton/ARM64 trong khi vẫn giữ nguyên các SLO dịch vụ (Checkout >= 99%, Browse/Cart >= 99.5%, Storefront p95 < 1000ms).

Đồng thời, Mandate 21 yêu cầu khả năng chịu lỗi multi-AZ và phương án khắc phục sự cố disaster recovery (DR). Yêu cầu cốt lõi là phải duy trì một On-Demand Reliability Floor (ngưỡng On-Demand tối thiểu bảo vệ hệ thống) để các dịch vụ quan trọng thuộc control-plane (Karpenter controller, CoreDNS, EBS CSI, các admission controllers) và workload lưu trữ dữ liệu bền vững (OpenSearch) không bị ảnh hưởng khi thị trường Spot bị thu hồi hoặc xảy ra sự cố AZ.

## Quyết định Kiến trúc
1. **Chuyển đổi 100% sang ARM64**: Toàn bộ worker nodes của EKS (cả On-Demand và Spot) được chuyển sang kiến trúc ARM64 (`t4g.large`, `c7g.large`, `c7g.xlarge`, `r7g.large`).
2. **Approved On-Demand Reliability Floor (Ngưỡng On-Demand được duyệt)**:
   - 2 Managed ARM64 `t4g.large` On-Demand nodes phân bổ trên 2 AZ (us-east-1a và us-east-1b) làm nền tảng bootstrap & daemon điều khiển cluster.
   - 1 Protected ARM64 `t4g.large` On-Demand node (us-east-1b) dành riêng cho OpenSearch và hệ thống observability lưu trữ dữ liệu (gắn volume EBS RWO AZ-bound).
3. **Chấp nhận Tỷ lệ Spot**:
   - **Tỷ lệ Steady State**: Tỷ lệ Spot duy trì ở mức ~40% (2 Spot nodes / 5 tổng số nodes) là thiết kế chủ động nhằm bảo đảm tuyệt đối yêu cầu DR của Mandate 21.
   - **Tỷ lệ High-Load Scale-Out**: Khi có tải cao, Karpenter sẽ tự động scale-out bổ sung các Spot nodes, đưa tỷ lệ Spot đạt >= 50%.

## Hậu quả & Đánh đổi
- **Tích cực**: Triệt tiêu hoàn toàn rủi ro kẹt control-plane hoặc OpenSearch bị evict khi Spot bị ngắt; đáp ứng 100% yêu cầu Mandate 21 DR; giảm từ 36.6% đến 49.2% node-hours compute.
- **Đánh đổi**: Tỷ lệ Spot lúc tải thấp duy trì ở 40% để bảo vệ 3 nodes On-Demand nền tảng.

## Chữ ký Xác nhận
- **Cost & Performance Lead**: Đã duyệt (CDO-04)
- **Platform & Reliability Lead**: Đã duyệt (CDO-08 / Reliability)
