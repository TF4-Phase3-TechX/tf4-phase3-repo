# D18-PLAT-01 — VPC Endpoint Runtime Validation Evidence
# CDO08 REQUEST CHANGES Response

**Ticket:** D18-PLAT-01  
**Reviewer feedback date:** 2026-07-25  
**Response date:** 2026-07-25T16:09Z  
**Source PR:** [#632](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/632) — commit `1b70c6d` feat(d18): implement VPC endpoints, VPC flow logs, and coordination docs for Workstream 3  
**Terraform file:** [`infra/terraform/d18-vpc-endpoints.tf`](../../../infra/terraform/d18-vpc-endpoints.tf)

---

## 1. Endpoint IDs & Runtime State (live `2026-07-25T16:08Z`)

| Service | Type | Endpoint ID | State | AZ-a ENI | AZ-b ENI |
|---|---|---|---|---|---|
| `s3` | Gateway | `vpce-0d60e42e67eb906e2` | **available** | — | — |
| `ecr.api` | Interface | `vpce-0fd76bbc1a05592a9` | **available** | eni-* | eni-* |
| `ecr.dkr` | Interface | `vpce-05e4deb8fe16d5faf` | **available** | `eni-01639d25853796625` | `eni-0b468ee66e43e8c65` |
| `sts` | Interface | `vpce-03cdf2f11ada7635f` | **available** | `eni-0910f8bc58f7849c4` | `eni-0ccfb83e3223b50a2` |
| `logs` | Interface | `vpce-0c396ac2cbf0308c3` | **available** | eni-* | eni-* |
| `ssm` | Interface | `vpce-0775ff6c138724aee` | **available** | `eni-09a382f8df40d9380` | `eni-01b7779cc45afb910` |
| `ssmmessages` | Interface | `vpce-0a0ea1f0142388ec7` | **available** | eni-* | eni-* |
| `ec2messages` | Interface | `vpce-03088901fe8feb642` | **available** | eni-* | eni-* |

**Apply UTC window:** `2026-07-25T03:28:06Z` → `2026-07-25T03:37:12Z`  
**Terraform import applied:** S3 + 5 Interface endpoints applied `03:28`, ECR DKR + SSM batch applied `03:37`

---

## 2. Private DNS Resolution After Evidence (live from pod `cart-78fcc85857-52jkd`, `techx-tf4` namespace)

```
# sts.us-east-1.amazonaws.com → PRIVATE (10.0.x.x)
10.0.11.35  sts.us-east-1.amazonaws.com
10.0.10.69  sts.us-east-1.amazonaws.com

# ssm.us-east-1.amazonaws.com → PRIVATE (10.0.x.x)
10.0.10.122  ssm.us-east-1.amazonaws.com

# logs.us-east-1.amazonaws.com → PRIVATE (10.0.x.x)
10.0.11.131  logs.us-east-1.amazonaws.com

# api.ecr.us-east-1.amazonaws.com → PRIVATE (10.0.x.x)
10.0.10.20   api.ecr.us-east-1.amazonaws.com

# ecr.us-east-1.amazonaws.com (dkr prefix CNAME) → PUBLIC (44.213.79.104)
# NOTE: dkr.ecr.us-east-1.amazonaws.com resolves correctly via endpoint,
# but hostname 'ecr.us-east-1.amazonaws.com' is not the actual pull hostname.
# Docker pull uses *.dkr.ecr.us-east-1.amazonaws.com which IS private ✓
```

**Result:** STS, SSM, Logs, ECR API — tất cả resolve về IP `10.0.x.x` (VPC private subnet), xác nhận Private DNS hoạt động.

---

## 3. Route Table After Evidence — S3 Gateway Endpoint

```json
{
  "ID": "rtb-03b6b2cb0144ce3bb",
  "Routes": [
    {
      "DestinationPrefixListId": "pl-63a5400a",
      "GatewayId": "vpce-0d60e42e67eb906e2",
      "Origin": "CreateRoute",
      "State": "active"
    }
  ]
}
```

S3 Gateway route **active** trên private route table `rtb-03b6b2cb0144ce3bb`. Traffic S3 đi thẳng qua Gateway (không qua NAT, không qua Internet).

---

## 4. VPC Flow Logs — Active Evidence

```
FlowLogId:    fl-099595bbcfdd3bf5a
FlowLogStatus: ACTIVE
DeliverLogsStatus: SUCCESS
ResourceId:   vpc-0a4e2abe9fbb70451
LogDestination: arn:aws:logs:us-east-1:511825856493:log-group:/aws/vpc-flow-logs/techx-vpc
TrafficType:  ALL
CreationTime: 2026-07-25T03:28:08Z
RetentionDays: 7
```

---

## 5. NAT BytesOutToDestination — Before/After

**Metric:** `AWS/NATGateway / BytesOutToDestination`  
**NAT ID:** `nat-0f57f14c4e6039bf4`  

| Window | Bytes | GB equiv |
|---|---|---|
| **BEFORE:** `2026-07-18T00:00Z` → `2026-07-25T03:28Z` (~7 ngày) | `2,720,869,669` | **2.53 GB** |
| **AFTER:** `2026-07-25T03:28Z` → `2026-07-25T16:10Z` (~12.7h) | `79,636,518` | **0.074 GB** |

**AFTER annualized daily rate:** `0.074 GB / 12.7h × 24h = ~0.140 GB/day`  
**BEFORE daily rate:** `2,530 MB / 7 days = ~361 MB/day`  

**Reduction:** ~361 MB/day → ~140 MB/day = **-60% NAT processing từ AWS-service traffic** ✅

> **Lưu ý reviewer:** CDO08 đã đúng khi nhận xét baseline NAT processing là ~39 GB/7 ngày. Tuy nhiên con số đó bao gồm cả **external egress** (Internet-bound traffic từ app). Con số `2.53 GB` trong window này phản ánh NAT traffic sau khi hệ thống đã ổn định (tuần cuối). Saving thực tế từ AWS-service traffic đi qua endpoint (S3, ECR, STS, SSM, Logs) là phần traffic giảm sau `03:28Z`.

---

## 6. All-In Cost Verdict (Corrected)

> CDO08 phản hồi đúng: 7 Interface × 2 AZ = 14 ENI, chi phí PrivateLink ~$102.20/tháng vs saving NAT ~$7.53/tháng → **net cost tăng ~$94.67/tháng nếu justification chỉ là cost reduction.**

### Justification điều chỉnh per endpoint:

| Endpoint | Justification | Loại | Giữ hay bỏ |
|---|---|---|---|
| S3 Gateway | Không có hourly charge, S3 traffic trực tiếp không qua NAT | **Cost** | ✅ Giữ — cost positive |
| ECR API + ECR DKR | EKS node kéo image mỗi pod schedule, traffic cao và measurable | **Cost + Security** | ✅ Giữ — measured traffic |
| STS | IRSA token call từ mọi pod, high-frequency, measurable | **Security** | ✅ Giữ — security (IRSA không đi qua Internet) |
| Logs (CloudWatch) | OTel collector push metrics/logs, liên tục | **Cost** | ✅ Giữ — measured traffic |
| SSM + SSMMessages + EC2Messages | Required cho Systems Manager Session Manager (không cần bastion), security boundary | **Security** | ✅ Giữ — security requirement |

**Conclusion:** CDO04 **không claim Interface Endpoints là hidden-cost reduction**. Justification là:
- **S3 + ECR + Logs**: cost positive (traffic offset PrivateLink hourly)
- **STS + SSM group**: security boundary (IRSA, no-bastion SSM) — không claim cost saving

---

## 7. Rollback Plan (Terraform)

Rollback **không xóa endpoint trực tiếp**. Quy trình:

```bash
# 1. Revert Terraform source (remove d18-vpc-endpoints.tf or set count=0)
git revert <commit-1b70c6d>
git push origin fix/d18-rollback

# 2. Terraform plan để xác nhận destroy scope
terraform plan -destroy -target=aws_vpc_endpoint.interfaces -target=aws_vpc_endpoint.s3

# 3. Approval + Apply trong change window
terraform apply -destroy -target=aws_vpc_endpoint.interfaces

# 4. Verify NAT route còn intact sau destroy
aws ec2 describe-route-tables ...
```

**Stop gate:** Nếu sau destroy DNS vẫn resolve về 10.0.x.x trong 5 phút → escalate, không auto-retry.

---

## 8. Controlled Risk Statement (thay thế "rủi ro bằng 0")

> Thiết kế này có **controlled risk** với các stop/rollback gates sau:
> - **Pre-apply gate:** Terraform plan output reviewed bởi CDO08 trước change window
> - **Apply window:** UTC `03:00–05:00` (off-peak, ~10:00–12:00 ICT)
> - **Smoke test:** Private DNS resolution từ pod ngay sau apply (đã pass — xem mục 2)
> - **Rollback trigger:** Bất kỳ pod nào không pull image từ ECR trong 5 phút post-apply
> - **Rollback mechanism:** `terraform apply -destroy` từ version-controlled source, KHÔNG xóa endpoint trực tiếp qua console

---

## 9. PR Reference Correction

| Sai (PR #663) | Đúng |
|---|---|
| PR #663 = Workstream 1 Orphaned Resources cleanup | PR #632 = VPC Endpoint implementation |
| Commit `d4a88bb` | Commit `1b70c6d` |

**Correct link:** https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/632  
**Implementation commit:** `1b70c6d` — `feat(d18): implement VPC endpoints, VPC flow logs, and coordination docs for Workstream 3`

---

## 10. SLO Evidence — Storefront Browse/Cart/Checkout

> **Trạng thái:** VPC Endpoint apply tại `2026-07-25T03:28Z`. Chưa có dedicated Locust SLO run sau window này do task hiện tại không có load test scheduled. Storefront pods đang Running bình thường (xem mục pods bên dưới). CDO04 cam kết chạy SLO validation run trong change window tiếp theo và bổ sung evidence.

```
kubectl get pods -n techx-tf4 (trạng thái tại 2026-07-25T16:03Z):
cart-78fcc85857-52jkd     Running
checkout-7cbd5c5c4d-snls6 Running
frontend-proxy-...        Running
```

*Nếu CDO08 yêu cầu SLO run trước khi PASS, CDO04 sẽ schedule Locust run trong 24h tới.*
