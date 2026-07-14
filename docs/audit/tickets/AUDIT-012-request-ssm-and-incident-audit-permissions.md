# [AUDIT-012] Yêu cầu bổ sung quyền SSM và incident audit cho checkout/payment

**Trạng thái**: TO DO  
**Người yêu cầu (Reporter)**: Trần Minh Quang - Nhóm CDO07 (Audit)  
**Người thực hiện (Assignee)**: Nhóm CDO08 (Security/SSO/IAM)  
**Nhóm phối hợp**: Nhóm CDO04 (Observability/Platform), Nhóm CDO07 (Audit evidence), Nhóm CDO08 (Reliability/SLO threshold), Nhóm AIO01 (AI/flow signal nếu cần)  
**Độ ưu tiên (Priority)**: P0 (Blocker private access và incident evidence)  
**Epic**: Mandate 01 - Network Exposure / OBS-01 - Incident Observability / SEC-05 SSM Bastion

---

## 1. Bối cảnh (Context)

Mandate 01 yêu cầu storefront vẫn public cho người dùng, nhưng các cổng vận hành như Grafana, Jaeger và Load Generator phải bị chặn khỏi internet công cộng. Đường truy cập riêng tư được thiết kế là:

`AWS SSO identity cá nhân -> SSM Session Manager -> bastion i-072084d1cf0b2f1c9 -> port-forward tới operational portals`

CDO07 đã kiểm tra lại và xác nhận:

- Bastion `i-072084d1cf0b2f1c9` vẫn `running`.
- SSM target vẫn `connected`.
- Profile `TF4-AuditReadOnlyAndAnalyze-511825856493` đọc được một số thông tin SSM.
- Tuy nhiên profile hiện vẫn thiếu `ssm:StartSession` và `ssm:GetDocument`, nên chưa mở được tunnel vào Grafana/Jaeger/OpenSearch để lấy evidence.

Ngoài nhu cầu nghiệm thu Mandate 01, trong incident user báo **không thanh toán được** vào khoảng **14:15-14:30 ICT ngày 14/07/2026**, CDO07 chỉ xác định được bằng AWS CLI rằng:

- ALB/frontend vẫn healthy, chưa thấy target 5xx hoặc latency spike rõ ở tầng ALB.
- EKS audit log không thấy delete/change bất thường trực tiếp với checkout/payment trong window.
- Code path nghi ngờ nằm tại luồng `checkout -> payment`, cụ thể là gRPC call `/oteldemo.PaymentService/Charge`.
- Chưa thể truy vết trực tiếp vì thiếu quyền đọc Kubernetes pod logs và chưa vào được Grafana/Jaeger/OpenSearch qua SSM.

Vì vậy ticket này mở rộng phạm vi từ "SSM port-forward" sang **SSM + quyền đọc evidence phục vụ audit incident checkout/payment**. Ticket không yêu cầu quyền write/deploy, không yêu cầu SSH, không yêu cầu mở public ingress, và không yêu cầu quyền vận hành rộng ngoài phạm vi đọc/port-forward phục vụ audit.

## 2. Evidence lỗi hiện tại

CDO07 chạy lệnh mở tunnel bằng profile audit:

```cmd
aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters "{\"portNumber\":[\"13000\"],\"localPortNumber\":[\"3000\"]}" --profile TF4-AuditReadOnlyAndAnalyze-511825856493 --region us-east-1
```

Kết quả:

```text
AccessDeniedException: User: arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/quang.tranminh is not authorized to perform: ssm:StartSession on resource: arn:aws:ec2:us-east-1:511825856493:instance/i-072084d1cf0b2f1c9 because no identity-based policy allows the ssm:StartSession action
```

Lệnh đọc SSM document cũng bị chặn:

```text
ssm:GetDocument -> AccessDenied on arn:aws:ssm:us-east-1::document/AWS-StartPortForwardingSession
```

Khi thử dùng `kubectl` để đọc manifest/log runtime, local hiện chưa đủ quyền Kubernetes:

```text
error: You must be logged in to the server (the server has asked for the client to provide credentials)
```

## 3. Yêu cầu bổ sung quyền (The What)

Đề nghị CDO08/IAM owner bổ sung quyền tối thiểu để CDO07 có thể:

1. Mở SSM tunnel vào các cổng vận hành private.
2. Đọc AWS evidence liên quan ALB, CloudWatch, EKS và CloudTrail.
3. Đọc Kubernetes logs của các service liên quan incident checkout/payment.
4. Truy cập read-only vào Grafana/Prometheus/Jaeger/OpenSearch để lấy dashboard, metrics, trace và log evidence.

### 3.1 SSM port-forward permissions

| Quyền | Mục đích |
|---|---|
| `ssm:StartSession` | Mở SSM port-forward session tới bastion để truy cập Grafana/Jaeger/Load Generator/OpenSearch qua localhost |
| `ssm:TerminateSession` | Kết thúc session của người dùng sau khi nghiệm thu/audit |
| `ssm:ResumeSession` | Nối lại session nếu phiên bị gián đoạn |
| `ssm:DescribeSessions` | Xem session history/active session để đối soát evidence |
| `ssm:GetConnectionStatus` | Kiểm tra bastion có sẵn sàng nhận SSM session không |
| `ssm:DescribeInstanceInformation` | Xác nhận bastion là SSM managed instance và đang Online |
| `ssm:GetDocument` | Đọc/verify SSM document dùng cho port-forward |
| `ssm:DescribeDocument` | Xem metadata/trạng thái document SSM |

Scope đề xuất:

```text
arn:aws:ec2:us-east-1:511825856493:instance/i-072084d1cf0b2f1c9
arn:aws:ssm:us-east-1::document/AWS-StartPortForwardingSession
```

### 3.2 AWS read-only permissions cho incident audit

| Quyền | Mục đích |
|---|---|
| `eks:DescribeCluster` | Lấy endpoint/certificate cluster để cấu hình kubeconfig và xác nhận cluster target |
| `eks:ListNodegroups` | Liệt kê node group để kiểm tra runtime capacity |
| `eks:DescribeNodegroup` | Xem trạng thái node group, instance type, desired/min/max capacity và health issue |
| `logs:DescribeLogGroups` | Tìm log groups hiện có phục vụ incident evidence |
| `logs:DescribeLogStreams` | Liệt kê streams trong log group liên quan |
| `logs:FilterLogEvents` | Lọc CloudWatch Logs theo window incident và keyword |
| `logs:GetLogEvents` | Đọc log events chi tiết theo stream |
| `logs:StartQuery` | Chạy CloudWatch Logs Insights query nếu log được ship lên CloudWatch |
| `logs:GetQueryResults` | Lấy kết quả Logs Insights query |
| `cloudwatch:GetMetricData` | Query nhiều metric cùng lúc cho ALB/EKS/app evidence |
| `cloudwatch:GetMetricStatistics` | Query metric theo window incident |
| `cloudwatch:ListMetrics` | Tìm metric/label đang có trước khi viết query |
| `cloudwatch:DescribeAlarms` | Xem alarm có tự động detect incident hay không |
| `elasticloadbalancing:DescribeLoadBalancers` | Xác nhận ALB public/private và DNS đang phục vụ storefront |
| `elasticloadbalancing:DescribeTargetGroups` | Xác định target group/frontend route để query metric |
| `elasticloadbalancing:DescribeTargetHealth` | Kiểm tra target health trong incident window |
| `elasticloadbalancing:DescribeListeners` | Đối chiếu listener/routing của ALB |
| `elasticloadbalancing:DescribeRules` | Đối chiếu path rule public/private theo Mandate 01 |
| `cloudtrail:LookupEvents` | Đối soát thao tác AWS/SSM/EKS API quanh incident |

### 3.3 Kubernetes RBAC read-only trong namespace `techx-tf4`

Đề nghị cấp Kubernetes RBAC read-only cho identity/profile được CDO08 xác nhận, giới hạn namespace `techx-tf4`.

| Kubernetes permission | Mục đích |
|---|---|
| `get/list/watch pods` | Xem pod hiện tại của checkout/payment/flagd/frontend |
| `get/list/watch deployments` | Xem rollout/runtime config của các service |
| `get/list/watch replicasets` | Đối chiếu pod thuộc revision nào |
| `get/list/watch services` | Xác nhận service DNS/port nội bộ |
| `get/list/watch endpoints` | Xác nhận service có endpoint backing pod |
| `get/list/watch events` | Xem event restart, probe fail, scheduling, image pull |
| `get/list/watch configmaps` | Xem config không nhạy cảm liên quan observability/flag reference nếu được phép |
| `get pods/log` | Đọc logs `checkout`, `payment`, `flagd`, `frontend` để truy vết incident |

Quyền quan trọng nhất cho incident checkout/payment:

```text
get pods/log
```

Các service cần đọc log tối thiểu:

```text
checkout
payment
flagd
frontend
```

Nếu CDO08 cho phép debug nâng cao, có thể cấp thêm `pods/exec` read/debug có kiểm soát. Tuy nhiên `pods/exec` không bắt buộc cho nghiệm thu ban đầu và có thể tách ticket riêng nếu cần.

### 3.4 Observability portal read-only access

Ngoài IAM/SSM, cần quyền trong các portal sau:

| Portal | Quyền cần |
|---|---|
| Grafana | Viewer/read-only, xem dashboard và alert history |
| Prometheus | Query/read-only, chạy PromQL phục vụ SLI/SLO |
| Jaeger | Read-only/search traces, xem trace `checkout -> payment` |
| OpenSearch | Read-only/search logs, lọc logs theo service/time window |

## 4. Ranh giới trách nhiệm

- CDO08 owns SSO/IAM permission set, EKS access entry/RBAC mapping và scope quyền SSM vào đúng bastion/document đã duyệt.
- CDO04 confirms bastion/runtime path, port mapping, observability endpoints và datasource nếu có thay đổi.
- CDO07 owns audit evidence:
  - private access qua SSM tunnel hoạt động,
  - CloudTrail ghi nhận `StartSession`,
  - dashboard/metrics/log/trace evidence cho incident checkout/payment,
  - ghi rõ nếu evidence không tồn tại hoặc không truy cập được.

Quyền trong ticket này chỉ dùng cho audit/read-only và private port-forward. Không yêu cầu quyền deploy, sửa workload, sửa IAM, sửa dashboard, mở SSH hoặc mở public ingress.

## 5. Lệnh verify sau khi được cấp quyền

Kiểm tra identity:

```cmd
aws sts get-caller-identity --profile TF4-AuditReadOnlyAndAnalyze-511825856493 --region us-east-1
```

Kiểm tra bastion SSM:

```cmd
aws ssm get-connection-status --target i-072084d1cf0b2f1c9 --profile TF4-AuditReadOnlyAndAnalyze-511825856493 --region us-east-1
```

Verify SSM document:

```cmd
aws ssm get-document --name AWS-StartPortForwardingSession --profile TF4-AuditReadOnlyAndAnalyze-511825856493 --region us-east-1
```

Mở tunnel Grafana:

```cmd
aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters "{\"portNumber\":[\"13000\"],\"localPortNumber\":[\"3000\"]}" --profile TF4-AuditReadOnlyAndAnalyze-511825856493 --region us-east-1
```

Sau đó mở:

```text
http://localhost:3000
```

Cấu hình kubeconfig:

```cmd
aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1 --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

Kiểm tra Kubernetes read-only:

```cmd
kubectl -n techx-tf4 get pods
kubectl -n techx-tf4 get deploy checkout payment flagd frontend
kubectl -n techx-tf4 get events --sort-by=.lastTimestamp
```

Đọc logs phục vụ incident checkout/payment:

```cmd
kubectl -n techx-tf4 logs deploy/checkout --since-time=2026-07-14T07:10:00Z --timestamps
kubectl -n techx-tf4 logs deploy/payment --since-time=2026-07-14T07:10:00Z --timestamps
kubectl -n techx-tf4 logs deploy/flagd --since-time=2026-07-14T07:10:00Z --timestamps
kubectl -n techx-tf4 logs deploy/frontend --since-time=2026-07-14T07:10:00Z --timestamps
```

Keyword cần grep khi audit incident:

```text
failed to charge card
could not charge the card
Payment request failed
Invalid token
PaymentService/Charge
checkout
payment
```

Đối soát CloudTrail:

```cmd
aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession --max-results 10 --profile TF4-AuditReadOnlyAndAnalyze-511825856493 --region us-east-1
```

## 6. Tiêu chí nghiệm thu (Acceptance Criteria / Evidence)

- [ ] CDO07 chạy được `aws ssm start-session` tới bastion `i-072084d1cf0b2f1c9` bằng profile được CDO08 xác nhận.
- [ ] Grafana truy cập được qua `http://localhost:3000` khi tunnel `13000 -> 3000` đang mở.
- [ ] Jaeger truy cập được qua `http://localhost:16686/jaeger/ui/` khi tunnel `16686 -> 16686` đang mở.
- [ ] Load Generator truy cập được qua `http://localhost:8089` khi tunnel `18089 -> 8089` đang mở.
- [ ] Public paths `/grafana/`, `/jaeger/ui/`, `/loadgen/` trên ALB vẫn bị chặn theo Mandate 01.
- [ ] CloudTrail có event `StartSession` khớp principal CDO07, bastion ID, timestamp và document `AWS-StartPortForwardingSession`.
- [ ] CDO07 đọc được Kubernetes logs của `checkout`, `payment`, `flagd`, `frontend` trong namespace `techx-tf4`.
- [ ] CDO07 truy cập được Grafana/Prometheus/Jaeger/OpenSearch read-only để lấy dashboard, metrics, trace và log evidence.
- [ ] Incident checkout/payment có thể được audit bằng ít nhất một trong các nguồn: pod logs, Jaeger trace, Prometheus/Grafana metrics hoặc OpenSearch logs.
- [ ] Nếu không có log/trace/metric tương ứng, CDO07 ghi rõ là observability gap thay vì kết luận thiếu căn cứ.
- [ ] Nếu quyền được cấp qua profile mới, tài liệu nghiệm thu được cập nhật đúng tên profile mới.

*(Sau khi hoàn thành, vui lòng tag CDO07 để chạy lại verification, lưu evidence Mandate 01 và bổ sung incident report checkout/payment.)*
