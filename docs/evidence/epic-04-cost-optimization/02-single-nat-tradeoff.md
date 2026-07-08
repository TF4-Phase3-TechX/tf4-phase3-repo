# COST-02: Ghi nhận trade-off giữa Single NAT Gateway và NAT Gateway per AZ

## 1. Mục tiêu task

Task này dùng để ghi nhận quyết định kiến trúc liên quan đến NAT Gateway trong Week 1 baseline.

Mục tiêu là giải thích rõ vì sao team chọn **Single NAT Gateway** để kiểm soát chi phí, đồng thời ghi nhận rủi ro về network availability và hướng cải thiện trong tương lai là **NAT Gateway per AZ**.

---

## 2. Bối cảnh

Trong kiến trúc baseline của TF4, hệ thống sử dụng EKS worker nodes nằm trong private subnets. Các workload trong private subnets cần outbound traffic để pull container images từ ECR hoặc truy cập external AWS services khi cần.

Vì private subnets không truy cập trực tiếp Internet Gateway, outbound traffic cần đi qua NAT Gateway.

Hiện tại, team cần chọn giữa hai phương án:

1. **Single NAT Gateway**
2. **NAT Gateway per Availability Zone**

---

## 3. Quyết định hiện tại

Trong Week 1 baseline, TF4 sử dụng:

- 1 VPC
- 2 Availability Zones
- Public subnets cho ALB và NAT Gateway
- Private subnets cho EKS worker nodes
- 1 Single NAT Gateway cho outbound traffic từ private subnets

Luồng outbound chính:

```txt
EKS Worker Nodes → NAT Gateway → ECR / External AWS Services
```

Luồng này chủ yếu dùng cho:

- Pull container images từ ECR
- Truy cập AWS managed services hoặc external services nếu workload cần outbound
- Hỗ trợ outbound traffic từ private workloads

---

## 4. Option 1: Single NAT Gateway

### 4.1. Mô tả

Single NAT Gateway nghĩa là toàn bộ private subnets route outbound traffic thông qua một NAT Gateway duy nhất, thường nằm trong một public subnet.

Ví dụ:

```txt
Private Subnet AZ-a ┐
                    ├── Single NAT Gateway → Internet / AWS Services
Private Subnet AZ-b ┘
```

### 4.2. Lợi ích

1. Chi phí thấp hơn trong Week 1.
2. Kiến trúc đơn giản hơn.
3. Dễ triển khai và dễ giải thích trong baseline.
4. Phù hợp với môi trường demo/baseline.
5. Tránh tăng chi phí cố định khi hệ thống chưa production-ready.
6. Giúp team ưu tiên ngân sách cho EKS nodes, ALB, observability và runtime validation.

### 4.3. Rủi ro

1. NAT Gateway trở thành một network dependency.
2. Nếu NAT Gateway hoặc AZ chứa NAT Gateway gặp sự cố, outbound traffic từ private subnets có thể bị ảnh hưởng.
3. Private subnet ở AZ khác có thể phải đi outbound cross-AZ qua NAT Gateway.
4. Không được claim đây là full network high availability.
5. Multi-AZ worker nodes không đồng nghĩa toàn bộ network path đã có Multi-AZ HA.
6. Nếu outbound traffic trở thành dependency quan trọng cho checkout/payment/core services, Single NAT có thể không còn phù hợp.

### 4.4. Khi nào Single NAT Gateway phù hợp?

Single NAT Gateway phù hợp với Week 1 vì:

- Mục tiêu hiện tại là baseline deployment và evidence collection.
- Team cần kiểm soát chi phí.
- Hệ thống chưa claim production-grade HA.
- Trọng tâm là chứng minh kiến trúc, deploy được hệ thống, thu thập observability/performance/cost evidence.
- NAT Gateway per AZ được ghi nhận là hướng hardening trong tương lai.

---

## 5. Option 2: NAT Gateway per AZ

### 5.1. Mô tả

NAT Gateway per AZ nghĩa là mỗi Availability Zone có một NAT Gateway riêng. Private subnet trong AZ nào sẽ route outbound traffic qua NAT Gateway trong cùng AZ đó.

Ví dụ:

```txt
Private Subnet AZ-a → NAT Gateway AZ-a → Internet / AWS Services
Private Subnet AZ-b → NAT Gateway AZ-b → Internet / AWS Services
```

### 5.2. Lợi ích

1. Network resilience tốt hơn.
2. Giảm dependency outbound cross-AZ.
3. Nếu một NAT Gateway hoặc một AZ gặp sự cố, workload ở AZ còn lại vẫn có thể dùng NAT Gateway local.
4. Phù hợp hơn với production-grade Multi-AZ architecture.
5. Câu chuyện HA cho outbound traffic rõ ràng hơn.
6. Giảm rủi ro single point of dependency cho outbound network path.

### 5.3. Đánh đổi

1. Chi phí cao hơn vì mỗi NAT Gateway có hourly cost riêng.
2. Cần quản lý nhiều route table hơn.
3. Có thêm thành phần cần monitor.
4. Có thể chưa cần thiết cho Week 1 baseline/demo.
5. Có thể làm giảm ngân sách dành cho EKS nodes, ALB, observability và runtime validation.
6. Nếu chưa có runtime evidence, việc tăng NAT Gateway có thể là premature optimization.

### 5.4. Khi nào nên dùng NAT Gateway per AZ?

NAT Gateway per AZ nên được cân nhắc khi:

- Hệ thống tiến gần hơn tới production-grade reliability.
- Outbound connectivity trở thành dependency quan trọng cho checkout, payment hoặc core services.
- Client yêu cầu network availability cao hơn.
- Budget cho phép tăng chi phí NAT Gateway.
- Có evidence cho thấy Single NAT Gateway là bottleneck hoặc reliability risk.
- Team cần claim Multi-AZ network resilience rõ ràng hơn.
- Cost Explorer cho thấy team vẫn còn đủ budget headroom.

---

## 6. So sánh hai phương án

| Tiêu chí | Single NAT Gateway | NAT Gateway per AZ |
|---|---|---|
| Chi phí | Thấp hơn | Cao hơn |
| Độ phức tạp | Đơn giản hơn | Phức tạp hơn |
| Network resilience | Thấp hơn | Tốt hơn |
| Cross-AZ dependency | Có thể có | Giảm đáng kể |
| Phù hợp Week 1 baseline | Phù hợp | Có thể chưa cần |
| Phù hợp production-grade HA | Chưa đủ | Phù hợp hơn |
| Route table management | Đơn giản | Cần quản lý theo AZ |
| Monitoring effort | Ít hơn | Nhiều hơn |
| Risk chính | NAT là dependency risk | Tăng fixed cost |

---

## 7. Quyết định cho Week 1

TF4 chọn:

```txt
Single NAT Gateway cho Week 1 baseline.
```

### 7.1. Lý do

Lý do chính là **kiểm soát chi phí**.

Week 1 tập trung vào:

- Baseline architecture
- EKS deployment
- Observability evidence
- Performance baseline
- Cost visibility
- Week 1 Pitch

Ở giai đoạn này, dùng NAT Gateway per AZ sẽ làm tăng chi phí cố định trước khi team có đủ runtime evidence để chứng minh sự cần thiết.

Single NAT Gateway được chấp nhận với điều kiện team phải ghi rõ:

- Đây là quyết định để kiểm soát chi phí.
- Đây không phải full network HA.
- Multi-AZ hiện tại chỉ claim cho EKS compute layer.
- Stateful workload HA chưa được claim trong Week 1.
- NAT Gateway per AZ là future hardening option.

---

## 8. Architecture Statement

Câu mô tả kiến trúc chính xác:

```txt
TF4 sử dụng hai Availability Zones cho EKS compute-layer resilience, nhưng Week 1 chỉ dùng Single NAT Gateway như một cost-control trade-off. Vì vậy, kiến trúc hiện tại không được claim là full network high availability. NAT Gateway per AZ được ghi nhận là hướng hardening trong tương lai.
```

---

## 9. Cách trình bày trong Week 1 Pitch

Khi trình bày, team nên nói:

```txt
Trong Week 1 baseline, team chủ động sử dụng Single NAT Gateway để kiểm soát chi phí. EKS worker nodes được phân bổ trên hai Availability Zones, nhưng team không claim full network HA ở giai đoạn này. Single NAT Gateway là một dependency risk đã được ghi nhận, và NAT Gateway per AZ sẽ là hướng cải thiện khi hệ thống tiến gần hơn tới production-grade reliability.
```

---

## 10. Góc nhìn chi phí

Single NAT Gateway giúp giảm chi phí cố định của hạ tầng.

NAT Gateway per AZ cải thiện availability nhưng làm tăng baseline cost. Vì Week 1 tập trung vào deploy baseline và thu thập evidence, team ưu tiên kiểm soát chi phí trước.

Quyết định này cần được xem xét lại sau khi:

1. EKS baseline đã deploy.
2. Cost Explorer có dữ liệu.
3. Traffic pattern thực tế rõ hơn.
4. Mức độ phụ thuộc outbound traffic được xác nhận.
5. Budget headroom được kiểm tra.

---

## 11. Risk Register

| Risk ID | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| COST-RISK-01 | Single NAT Gateway là network dependency | Outbound traffic từ private subnets có thể bị ảnh hưởng nếu NAT/AZ gặp sự cố | Medium | Ghi nhận trade-off, monitor NAT usage, cân nhắc NAT per AZ trong future hardening |
| COST-RISK-02 | NAT Gateway per AZ làm tăng fixed cost | Chi phí baseline cao hơn, giảm ngân sách cho nodes/observability/testing | High | Dùng Single NAT trong Week 1, xem xét lại sau khi có Cost Explorer data |
| ARCH-RISK-01 | Multi-AZ compute có thể bị hiểu nhầm là full HA | Stakeholder có thể hiểu sai rằng app/network/data đều đã HA | Medium | Ghi rõ Week 1 chỉ claim Multi-AZ cho EKS compute layer |
| ARCH-RISK-02 | Outbound dependency chưa được xác nhận đầy đủ | Nếu workload phụ thuộc outbound liên tục, Single NAT có thể gây rủi ro vận hành | Medium | Runtime validation sau deploy, kiểm tra traffic và dependency thực tế |
| COST-RISK-03 | Cross-AZ routing có thể phát sinh thêm dependency/cost | Private subnet khác AZ có thể route qua NAT ở AZ còn lại | Low/Medium | Verify route table sau deploy, cân nhắc NAT per AZ nếu traffic lớn |

---

## 12. Follow-up Actions

| Action | Owner | Status |
|---|---|---|
| Verify NAT Gateway placement trong AWS VPC | Infra / Architecture | Pending after deploy |
| Verify route tables cho private subnets | Infra / Architecture | Pending after deploy |
| Capture NAT Gateway cost trong Cost Explorer | Cost Owner | Pending after deploy |
| Xem xét lại NAT per AZ sau khi có runtime evidence | PM / Cost / Tech Lead | Pending |
| Bổ sung trade-off này vào Week 1 Pitch notes | PM | To Do |
| Kiểm tra outbound dependency của workload sau deploy | Infra / Reliability | Pending after deploy |

---

## 13. Runtime Validation Commands

Sau khi deploy, cần verify NAT Gateway và route table.

### 13.1. Kiểm tra NAT Gateway

```bash
aws ec2 describe-nat-gateways \
  --filter "Name=state,Values=available" \
  --query "NatGateways[*].[NatGatewayId,VpcId,SubnetId,State]" \
  --output table
```

### 13.2. Kiểm tra route tables

```bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=<vpc-id>" \
  --query "RouteTables[*].[RouteTableId,Associations[*].SubnetId,Routes[*].NatGatewayId]" \
  --output table
```

### 13.3. Kiểm tra node group subnets

```bash
aws eks describe-nodegroup \
  --cluster-name <cluster-name> \
  --nodegroup-name <nodegroup-name> \
  --query "nodegroup.subnets" \
  --output table
```

### 13.4. Kiểm tra worker nodes có nằm trên nhiều AZ không

```bash
kubectl get nodes -L topology.kubernetes.io/zone
```

---

## 14. Evidence Location

Evidence của task này được lưu tại:

```txt
docs/evidence/epic-04-cost-optimization/02-single-nat-tradeoff.md
```

Related architecture evidence:

```txt
docs/evidence/epic-02-baseline-architecture/01-aws-high-level-architecture.md
docs/evidence/epic-02-baseline-architecture/04-architecture-assumptions.md
docs/evidence/epic-02-baseline-architecture/05-architecture-risk-register.md
```

Related diagram:

```txt
docs/architecture/01-techx-tf4-aws-high-level-architecture.jpg
```

---


## 16. Jira Evidence Comment

Team cần ghi rõ trong architecture và Week 1 Pitch rằng:

- Multi-AZ hiện tại chỉ áp dụng cho EKS compute layer.
- Single NAT Gateway là một dependency risk.
- NAT Gateway per AZ là hướng hardening trong tương lai.
- Quyết định này cần được xem xét lại sau khi có runtime evidence và Cost Explorer data.