# [REVIEW REQUEST] CDO04 — Cost Review cho CDO08-SEC-05

| Thông tin | Giá trị |
|---|---|
| Từ | CDO08 |
| Đến | CDO04 (Cost) |
| Backlog | `CDO08-SEC-05` — Ingress Hardening |
| Ngày gửi | 2026-07-13 |
| Deadline | 2026-07-14, trước deploy |
| Review result | **APPROVED WITH CONDITIONS** |

## 1. Thay đổi đề xuất

MANDATE-01 yêu cầu storefront tiếp tục public, còn Grafana, Jaeger, Load Generator và các operational route phải private.

CDO08 đề xuất:

```text
AWS SSO identity cá nhân
→ SSM Session Manager
→ EC2 Bastion private
→ kubectl port-forward chạy trên Bastion
→ operational portal
```

- Bastion không có public IP, không mở SSH/port 22.
- Chặn sáu operational route trên public Envoy sau approval.
- Không tạo VPN Gateway hoặc internal ALB.
- Không thay flagd/OpenFeature hooks.

## 2. Cost assumptions

CDO04 đồng ý về mặt budget vì fixed incremental cost dự kiến thấp hơn đáng kể so với trần `$300/tuần/TF`. Preliminary estimate do CDO04 cung cấp:

```text
EC2 t3.nano + EBS gp3 ≈ $3.7–$3.9/tuần
```

Con số này chưa gồm NAT data processing, VPC Endpoint hoặc logging usage. Trước implementation phải chốt đầy đủ assumptions bằng AWS Pricing Calculator/Cost Explorer tại `us-east-1`.

| Thành phần | Cách tính | Ghi chú |
|---|---|---|
| EC2 Bastion | Giá On-Demand × số giờ chạy/tuần | Preliminary dùng `t3.nano`; Infra phải xác nhận đủ CPU/RAM trước deploy |
| EBS encrypted root volume | GB-tháng quy đổi theo tuần | Dung lượng tối thiểu đủ OS, SSM Agent, AWS CLI và kubectl |
| SSM Session Manager trên EC2 | Không có phí Session Manager riêng | Theo AWS Systems Manager pricing; quota/related-service cost vẫn áp dụng |
| CloudWatch/S3 session logs | Ingestion + retention | Chỉ phát sinh nếu bật; port-forward không ghi nội dung HTTP |
| Network egress | Theo traffic thực tế | Portal traffic dự kiến thấp |
| NAT Gateway | Chỉ tính **incremental cost** nếu NAT hiện có được tái sử dụng | Không được ghi `$0` trước khi xác nhận route private subnet |
| SSM VPC interface endpoints | Hourly/AZ + data, nếu phải tạo mới | Chọn NAT hiện có **hoặc** endpoints sau cost/network review |
| Internal ALB/VPN | `$0` trong phương án này | Không tạo mới |

### Công thức approval

```text
Incremental weekly cost
= EC2 compute
 + EBS
 + incremental logging
 + incremental network
 + NAT hoặc VPC endpoint mới (nếu có)
```

CDO04 cần so sánh ít nhất hai chế độ:

1. Bastion chạy `24x7`.
2. Bastion chạy theo lịch/on-demand trong deploy hoặc review window, nếu cách này không làm Mentor/BTC mất quyền truy cập bắt buộc.

## 3. Trade-off

| Phương án | Chi phí | Nhận xét |
|---|---|---|
| **SSM Bastion + kubectl port-forward** | Cần CDO04 tính theo công thức trên | Phương án chọn; không SSH key/public IP/internal ALB |
| Laptop chạy kubectl trực tiếp | Compute `$0` | Phải cấp kubeconfig/RBAC trực tiếp; không có điểm truy cập tập trung |
| SSH Bastion public | EC2 tương tự + vận hành key/SG | Không chọn vì mở inbound và tăng công quản trị |
| VPN | Cần estimate riêng | Quá rộng so với phạm vi portal hiện tại |
| Internal ALB/private ingress | Cần estimate riêng | Không chọn trong phương án hiện tại |

SSM/CloudTrail cung cấp identity/session-level audit, không phải application-level audit. Đây là trade-off bảo mật, không được dùng làm lý do cộng hoặc trừ chi phí không có thật.

## 4. CDO04 review result

**Decision: `APPROVED WITH CONDITIONS`.**

CDO04 approve phương án SSM Session Manager qua EC2 Bastion về mặt budget, với các điều kiện bắt buộc trước implementation:

- [ ] Xác nhận Bastion dùng NAT Gateway hiện có hay tạo SSM VPC Endpoints.
- [ ] Ghi EBS root volume type, size và projected cost.
- [ ] Ghi NAT data processing hoặc VPC Endpoint hourly/data cost.
- [ ] Ghi CloudTrail/CloudWatch/S3 logging configuration, retention và projected cost.
- [ ] Xác nhận Bastion không có public IPv4, Elastic IP hoặc inbound port 22.
- [ ] Chốt runtime assumption: `24x7` hoặc scheduled/on-demand.
- [ ] Chứng minh projected total weekly cost của TF vẫn `<= $300` trước deploy.

Điều kiện kiểm soát thay đổi:

- Không tạo VPC Endpoint mới nếu chưa được CDO04 review lại.
- Không tăng instance size ngoài `t3.nano` nếu chưa được CDO04 review lại.
- Actual incremental cost không được vượt estimate đáng kể nếu không có explanation và follow-up review.

Evidence sau triển khai:

- [ ] Attach projected estimate/Calculator evidence trước deploy.
- [ ] Attach actual incremental cost từ Cost Explorer sau khi đủ dữ liệu billing.
- [ ] So sánh projected với actual và giải thích variance.

```text
CDO04 approval record

Decision: APPROVED WITH CONDITIONS
Preliminary fixed cost: EC2 t3.nano + EBS gp3 ≈ $3.7–$3.9/tuần
Usage-based cost excluded: NAT/VPC Endpoint/logging/data processing
Budget condition: total projected weekly TF cost <= $300
Ngày duyệt: ___
Người duyệt: ___
Comment/Evidence link: ___
```

## 5. Nguồn tham chiếu

- [AWS Systems Manager pricing](https://aws.amazon.com/systems-manager/pricing/) — Session Manager không có phí bổ sung khi truy cập EC2.
- [Amazon EC2 On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/).
- [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/).
- [Amazon CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/).
