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

CDO04 đồng ý về mặt budget vì incremental cost thấp hơn đáng kể so với trần
`$300/tuần/TF`. CDO08 tính lại bằng giá public AWS tại `us-east-1`:

| Assumption | Giá dùng để tính |
|---|---:|
| EC2 Linux On-Demand `t3.nano` | `$0.0052/giờ` |
| EBS gp3 baseline | `$0.08/GiB-tháng` |
| Root volume | `8 GiB`, encrypted gp3, không provision thêm IOPS/throughput |
| Existing NAT data processing | `$0.045/GB`; NAT hourly charge đã tồn tại, không tính lại vào SEC-05 |
| SSM Session Manager trên EC2 | Không có phí Session Manager riêng |

Estimate `$3.7–$3.9/tuần` trước đó cao hơn phép tính public-price cho
`t3.nano + 8 GiB gp3`; con số này được giữ như budget ceiling sơ bộ, không dùng làm
projected cost chính thức.

| Thành phần | Cách tính | Ghi chú |
|---|---|---|
| EC2 Bastion | Giá On-Demand × số giờ chạy/tuần | Preliminary dùng `t3.nano`; Infra phải xác nhận đủ CPU/RAM trước deploy |
| EBS encrypted root volume | GB-tháng quy đổi theo tuần | Dung lượng tối thiểu đủ OS, SSM Agent, AWS CLI và kubectl |
| SSM Session Manager trên EC2 | Không có phí Session Manager riêng | Theo AWS Systems Manager pricing; quota/related-service cost vẫn áp dụng |
| CloudWatch/S3 session logs | Ingestion + retention | Chỉ phát sinh nếu bật; port-forward không ghi nội dung HTTP |
| Network egress | Theo traffic thực tế | Portal traffic dự kiến thấp |
| NAT Gateway | TF4 đã có single NAT trong `infra/terraform/vpc.tf` | Fixed incremental `$0`; cộng `$0.045/GB` usage và cross-AZ cost nếu có |
| SSM VPC interface endpoints | Không tạo trong phương án chọn | Ba endpoint/1 AZ đã khoảng `$5.04/tuần` + data; đắt hơn reuse NAT ở traffic thấp |
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

### Tính fixed cost

```text
EBS 8 GiB gp3/tuần
= 8 × $0.08 × 12 / 52
≈ $0.148/tuần

t3.nano 24x7
= 168 giờ × $0.0052
= $0.874/tuần

Tổng fixed 24x7
= $0.874 + $0.148
≈ $1.02/tuần
```

| Runtime | EC2/tuần | EBS/tuần | Fixed total/tuần |
|---|---:|---:|---:|
| On-demand `8 giờ/tuần` | `$0.042` | `$0.148` | **`$0.19`** |
| Scheduled `40 giờ/tuần` | `$0.208` | `$0.148` | **`$0.36`** |
| `24x7` | `$0.874` | `$0.148` | **`$1.02`** |

Các số trên chưa gồm NAT data, CloudWatch/S3 log và thuế. Với ví dụ `1 GB/tuần`
đi qua NAT, cộng khoảng `$0.045/tuần` trước cross-AZ/data-transfer charge.

## 3. Trade-off

| Phương án | Chi phí | Nhận xét |
|---|---|---|
| **SSM Bastion on-demand + existing NAT** | **Khoảng `$0.19/tuần` fixed tại 8 giờ chạy** | **Phương án chọn; private, tập trung, không SSH/public IP/internal ALB** |
| SSM Bastion `24x7` + existing NAT | Khoảng `$1.02/tuần` fixed | Fallback nếu Mentor/BTC cần truy cập không báo trước |
| Laptop chạy kubectl trực tiếp | Compute `$0` | Phải cấp kubeconfig/RBAC trực tiếp; không có điểm truy cập tập trung |
| SSH Bastion public | EC2 tương tự + vận hành key/SG | Không chọn vì mở inbound và tăng công quản trị |
| VPN | Cần estimate riêng | Quá rộng so với phạm vi portal hiện tại |
| Internal ALB/private ingress | Cần estimate riêng | Không chọn trong phương án hiện tại |

### Quyết định cost

Chọn **`t3.nano` scheduled/on-demand + NAT Gateway hiện có + EBS gp3 8 GiB**.
Bastion mặc định ở trạng thái stopped và được operator có quyền start khi có review
window; EBS vẫn phát sinh khoảng `$0.148/tuần`. Nếu yêu cầu luôn sẵn sàng, chuyển
sang `24x7` vẫn chỉ khoảng `$1.02/tuần` fixed. Không tạo SSM VPC Endpoints vì fixed
endpoint cost cao hơn đáng kể ở traffic thấp.

`t3.nano` chỉ có `0.5 GiB` RAM. Infra phải pilot AWS CLI + SSM Agent + `kubectl`
trước deploy; nếu không ổn định, nâng `t3.micro` phải quay lại CDO04 review.

SSM/CloudTrail cung cấp identity/session-level audit, không phải application-level
audit. Đây là trade-off bảo mật, không được dùng làm lý do cộng hoặc trừ chi phí
không có thật.

## 4. CDO04 review result

**Decision: `APPROVED WITH CONDITIONS`.**

CDO04 approve phương án SSM Session Manager qua EC2 Bastion về mặt budget, với các điều kiện bắt buộc trước implementation:

- [x] Chọn single NAT Gateway hiện có trong `infra/terraform/vpc.tf`; không tạo SSM VPC Endpoints.
- [x] Chọn encrypted EBS gp3 `8 GiB`, khoảng `$0.148/tuần`.
- [x] Ghi NAT data processing `$0.045/GB`; fixed NAT hourly cost không tính lại vì resource đã tồn tại.
- [ ] Ghi CloudTrail/CloudWatch/S3 logging configuration, retention và projected cost.
- [ ] Xác nhận Bastion không có public IPv4, Elastic IP hoặc inbound port 22.
- [x] Chọn scheduled/on-demand, baseline `8 giờ/tuần`; `24x7` là fallback.
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
Selected design: t3.nano scheduled/on-demand + existing NAT + encrypted gp3 8 GiB
Projected fixed cost at 8 runtime hours/week: ≈ $0.19/tuần
Projected fixed cost at 24x7 fallback: ≈ $1.02/tuần
Previous CDO04 preliminary ceiling: $3.7–$3.9/tuần
Usage-based cost excluded: NAT data/logging/data transfer/tax
Budget condition: total projected weekly TF cost <= $300
Ngày duyệt: ___
Người duyệt: ___
Comment/Evidence link: ___
```

## 5. Nguồn tham chiếu

- [AWS Systems Manager pricing](https://aws.amazon.com/systems-manager/pricing/) — Session Manager không có phí bổ sung khi truy cập EC2.
- [Amazon EC2 T3 pricing](https://aws.amazon.com/ec2/instance-types/t3/) — `t3.nano` Linux tại US East (N. Virginia): `$0.0052/giờ`.
- [Amazon EBS gp3 pricing](https://aws.amazon.com/ebs/pricing/) — gp3 tính theo provisioned GiB-tháng.
- [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/).
- [Amazon CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/).
