# [REVIEW & VERIFY REQUEST] CDO07 — Audit Review cho CDO08-SEC-05

| Thông tin | Giá trị |
|---|---|
| Từ | CDO08 |
| Đến | CDO07 (Audit/Compliance) |
| Backlog | `CDO08-SEC-05` — Ingress Hardening |
| Ngày gửi | 2026-07-13 |
| Trạng thái | **REVIEW COMMENT RECEIVED — PORT MAPPING CONDITION OPEN** |

## 1. Thiết kế cần review

MANDATE-01 yêu cầu operational portals phải private nhưng Mentor/BTC vẫn truy cập được khi cần.

CDO08 đề xuất:

1. Public Envoy trả explicit `404` cho `/grafana`, `/jaeger`, `/loadgen`, `/feature`, `/flagservice` và `/otlp-http` sau approval.
2. Private access theo luồng:

```text
AWS SSO identity cá nhân
→ SSM Session Manager
→ EC2 Bastion private
→ kubectl port-forward chạy trên Bastion
→ operational portal
```

CDO07 đóng vai trò **Audit Backstop** cần thẩm định phương án thiết kế này trước khi deploy, và nghiệm thu bằng chứng (evidence) sau khi hoàn tất.

---

## 2. Điểm kiểm toán quan trọng (Audit Trail & Security)

### Cơ chế log audit của SSM:
Khác với SSH Bastion thông thường (vốn không log được người dùng làm gì và phải sửa Security Group liên tục), SSM Session Manager đi qua HTTPS và tích hợp chặt chẽ với **AWS CloudTrail**.
Mọi hành vi khởi tạo tunnel (`StartSession`) đều được ghi lại tự động:
* **Ai vào:** User ARN / IAM Role ARN (BTC dùng Admin profile sẵn có, team nội bộ dùng Read-only profile).
* **Lúc nào:** Timestamp chính xác theo múi giờ hệ thống.
* **Từ đâu:** Source IP Address của máy client.
* **Vào service nào:** Request parameter chỉ định cụ thể target host (vd: `grafana.techx-observability.svc`).

---

## 3. Quy trình Đánh giá & Nghiệm thu của CDO07

### Giai đoạn 1 — Nội dung CDO07 cần xác nhận (Trước khi deploy):
CDO07 vui lòng đọc thiết kế và check-off:
- [x] **Độ tin cậy của Audit Trail:** Xác nhận log sự kiện `StartSession` trên CloudTrail là đủ bằng chứng kiểm toán cho truy cập cổng vận hành. (CloudTrail đã được verify là đang hoạt động).

### Giai đoạn 2 — Xác nhận khả năng Audit (Sau khi deploy):
CDO07 kiểm tra thực tế trên CloudTrail:
- [ ] **Xác nhận có thể Audit:** Chạy query hoặc kiểm tra CloudTrail console xem event `StartSession` đã được ghi nhận thành công và đầy đủ thông tin (user ARN, timestamp, source IP, target service) khi có phiên truy cập thử nghiệm.


- Bastion không có public IP và không mở inbound SSH/port 22.
- Người dùng không dùng shared admin credential hoặc long-lived access key.
- Bastion instance role dùng EKS Access Entry/RBAC tối thiểu; không có `cluster-admin`.
- Bastion dùng `t3.nano` scheduled/on-demand, EBS gp3 mã hóa 8 GiB và single NAT
  Gateway hiện có; phải pilot đủ RAM trước deploy.
- Không tạo SSM VPC Endpoint mới trong phương án đã chọn.
- Không tạo internal ALB trong phương án hiện tại.

## 2. Audit coverage thực tế

| Lớp log | Chứng minh được | Không chứng minh được |
|---|---|---|
| AWS SSO/CloudTrail | Principal mở/kết thúc SSM session, timestamp, source IP, Bastion target | Portal/path hoặc hành động HTTP bên trong tunnel |
| SSM shell log, nếu bật | Lệnh `kubectl port-forward` và output trong **phiên shell Terminal A** | Nội dung của **phiên tunnel Terminal B** |
| EKS control-plane audit, nếu bật | Bastion role gọi Kubernetes `pods/portforward`, namespace/pod và timestamp | Request HTTP chạy qua port-forward |
| Portal audit/access log, nếu có auth cá nhân | Hành động/request mà portal hỗ trợ ghi log | Không đảm bảo tồn tại cho mọi portal; anonymous/shared identity làm giảm attribution |

AWS xác nhận Session Manager không log nội dung của port-forward session. Vì vậy không được kết luận CloudTrail cho biết người dùng đã mở dashboard, xem trace hoặc bấm Start Loadgen.

Trong thiết kế này, CloudTrail chỉ thấy Bastion target và session document/parameters liên quan; nó **không tự biết Kubernetes Service đích**. Service đích chỉ có thể đối chiếu từ SSM shell log và EKS audit log nếu hai lớp này đã được bật.

### Hai phiên SSM và cách đối soát

Mỗi lần mở portal dùng hai phiên riêng:

1. **Terminal A — SSM shell:** người dùng vào Bastion và chạy
   `kubectl port-forward --address 127.0.0.1 ...`.
2. **Terminal B — SSM port-forward:** đưa Bastion loopback port về `localhost` trên
   máy người dùng bằng document `AWS-StartPortForwardingSession`.

CDO07 đối soát hai `StartSession` event bằng cùng AWS SSO principal, Bastion instance
ID và test window. Event Terminal B cung cấp `portNumber`; SSM shell log Terminal A
và EKS audit log cung cấp bằng chứng bổ sung cho lệnh/API Kubernetes tương ứng.
EKS audit log nhìn thấy **Bastion instance role**, không tự nhìn thấy AWS SSO identity
của người dùng; attribution end-to-end phải dựa trên correlation các lớp log này.

Nếu SSM shell logging hoặc EKS audit logging chưa bật thì port baseline source-controlled
chỉ là bằng chứng thiết kế, không phải bằng chứng runtime rằng người dùng đã forward đúng
Service. Portal cũng không tự biết AWS SSO principal nếu portal chưa có authentication và
application access log riêng.

## 3. CDO07 review comment và port-mapping baseline

CDO07 xác nhận `StartSession` đáp ứng các tiêu chí audit cốt lõi ở mức AWS API:

- Identity: `userIdentity.arn`/assumed-role session của AWS SSO identity cá nhân.
- Time: `eventTime` UTC.
- Source: `sourceIPAddress`.
- Target: Bastion EC2 instance và `portNumber` của SSM port-forward session.

Điều kiện CDO07 yêu cầu: CDO08 phải duy trì mapping cố định từ Bastion port trong
CloudTrail raw event đến Kubernetes Service đích. Baseline source-controlled:

| CloudTrail/SSM `portNumber` | Kubernetes target | Source path |
|---:|---|---|
| `13000` | `techx-observability/svc/grafana:80` | `docs/cdo08/week2/CDO08-SEC-05-INGRESS-HARDENING-RUNBOOK.md`, mục 6.3/Bước 4 |
| `16686` | `techx-observability/svc/jaeger:16686` | Cùng source path |
| `18089` | `techx-tf4/svc/load-generator:8089` | Cùng source path |

Không đổi/reuse các port trên cho service khác nếu chưa có PR cập nhật baseline và
CDO07 review. CloudTrail SSM target là **Bastion instance**, không phải Kubernetes Pod.
CDO07 đối soát service đích bằng port baseline, SSM shell log và EKS audit log.

Ví dụ một test Grafana hợp lệ phải có:

```text
AWS SSO principal A
→ StartSession Terminal A vào Bastion I trong test window T
→ shell log: kubectl ... svc/grafana 13000:80
→ EKS audit: Bastion role gọi pods/portforward
→ StartSession Terminal B vào Bastion I với portNumber=13000 trong T
```

Chuỗi này chứng minh principal A đã thiết lập đường truy cập đến Grafana theo baseline;
nó vẫn không chứng minh A đã xem dashboard hoặc thực hiện HTTP action cụ thể.

### S3 retention/immutability cần xác minh

Repo hiện khai báo bucket `tf4-cloudtrail-logs-bucket-<account-id>` trong
`infra/terraform/cloudtrail.tf`, bật Versioning nhưng cũng có `force_destroy = true`;
chưa thấy S3 Object Lock. Versioning hỗ trợ khôi phục/đối soát version nhưng không
tự tương đương WORM immutability. Trước khi ghi “log bất biến”, CDO07 cần attach
runtime evidence về bucket thực tế, bucket policy, retention, delete permissions và
Object Lock/giải pháp chống sửa-xóa nếu compliance yêu cầu.

## 4. Residual risk cần CDO07/Tech Lead xác nhận

```text
Audit được: ai mở phiên, lúc nào, từ đâu, vào Bastion nào;
có thể audit API port-forward nếu EKS audit log bật.

Không audit đầy đủ: người dùng đã thực hiện hành động HTTP nào
trong Grafana, Jaeger hoặc Loadgen.
```

Acceptance Criteria của SEC-05 yêu cầu portal private, private access cho Mentor/BTC, evidence trước/sau và rollback; không yêu cầu application-level audit. CDO08 đề nghị chấp nhận hạn chế trên cho phương án hiện tại, hoặc yêu cầu ticket riêng về portal SSO/application audit nếu compliance bắt buộc.

## 5. Phase 1 — Design review trước deploy

CDO07 vui lòng xác nhận:

- [ ] Mỗi Mentor/BTC/operator dùng AWS SSO identity cá nhân; không dùng shared admin profile.
- [ ] IAM Permission Set chỉ cho phép session vào đúng Bastion và đúng SSM documents.
- [ ] CloudTrail đang ghi SSM management events và có retention phù hợp.
- [ ] Session Manager preferences đã cấu hình CloudWatch/S3 shell logging, hoặc ghi rõ lý do không bật.
- [ ] EKS control-plane audit logging đang bật, hoặc residual gap được ghi nhận.
- [ ] Bastion role dùng EKS Access Entry/RBAC tối thiểu và không có `cluster-admin`.
- [ ] Bastion không có public IPv4/EIP, không có inbound rule và không mở port 22.
- [ ] Network đúng phương án đã chọn: dùng NAT hiện có, không tạo SSM VPC Endpoint/Internal ALB mới.
- [ ] CDO07 chấp nhận mô hình hai SSM session và phương pháp correlation bằng principal, Bastion ID, port và timestamp.
- [ ] Port baseline `13000/16686/18089` được CDO07 chấp nhận và không có mapping conflict.
- [ ] Xác minh đúng tên S3 bucket runtime và mức bảo vệ retention/immutability; không chỉ dựa vào Versioning.
- [ ] CDO07/Tech Lead chấp nhận residual risk không có application-level audit đầy đủ.

## 6. Phase 2 — Evidence verification sau deploy

CDO08 tạo một phiên test bằng identity cá nhân; CDO07 xác minh tối thiểu:

### CloudTrail

- [ ] Có hai `StartSession` tương ứng Terminal A và Terminal B trong cùng test window; có evidence kết thúc/session history tương ứng.
- [ ] Hai event có cùng user/role ARN và Bastion instance ID; có event time, source IP và session document.
- [ ] Event Terminal B dùng `AWS-StartPortForwardingSession`; `portNumber` khớp baseline `13000/16686/18089`.
- [ ] Không có secret/token trong evidence.

Ví dụ query:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --start-time <ISO-8601> \
  --end-time <ISO-8601>
```

### SSM/EKS logs

- [ ] Nếu SSM shell logging bật: tìm thấy lệnh `kubectl port-forward` tương ứng.
- [ ] Nếu EKS audit logging bật: tìm thấy request `pods/portforward` của Bastion role, đúng namespace/pod và timestamp.
- [ ] Timestamp giữa CloudTrail, SSM và EKS log correlation hợp lý.

### Security outcome

- [ ] Public operational paths trả explicit `404` hoặc policy `401/403`.
- [ ] Mentor/BTC truy cập private thành công qua SSO → SSM → Bastion → port-forward.
- [ ] Storefront vẫn `200`, checkout smoke test pass và flagd/OpenFeature không bị ảnh hưởng.

## 7. Phản hồi CDO07

```text
Phase 1 — Design review
Decision: APPROVE / APPROVE WITH CONDITIONS / REJECT
CloudTrail enabled: YES / NO
SSM shell logging enabled: YES / NO
EKS audit logging enabled: YES / NO
Port mapping baseline accepted: YES / NO
Two-session correlation accepted: YES / NO
CloudTrail S3 bucket/retention verified: YES / NO
Application-level audit required for SEC-05: YES / NO
Residual risk accepted: YES / NO
Conditions:

Phase 2 — Evidence verification
StartSession/TerminateSession verified: PASS / FAIL
Terminal A/Terminal B correlation: PASS / FAIL
SSM shell evidence: PASS / FAIL / NOT ENABLED
EKS pods/portforward evidence: PASS / FAIL / NOT ENABLED
Public route restriction: PASS / FAIL
Private access: PASS / FAIL
Storefront/checkout/flagd verification: PASS / FAIL

Ngày duyệt:
Người duyệt:
Evidence link:
```

## 8. Nguồn tham chiếu

- [AWS Session Manager logging](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging.html) — port-forward session content không được log.
- [AWS Session Manager auditing](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-auditing.html) — CloudTrail ghi Session Manager API activity.
- [Amazon EKS control-plane logs](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html).
