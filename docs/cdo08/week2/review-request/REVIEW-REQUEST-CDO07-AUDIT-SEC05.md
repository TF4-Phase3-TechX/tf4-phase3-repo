# [REVIEW & VERIFY REQUEST] CDO07 — Audit Review cho CDO08-SEC-05

| Thông tin | Giá trị |
|---|---|
| Từ | CDO08 |
| Đến | CDO07 (Audit/Compliance) |
| Backlog | `CDO08-SEC-05` — Ingress Hardening |
| Ngày gửi | 2026-07-13 |
| Trạng thái | Chờ design review (Phase 1) và evidence verification (Phase 2) |

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

- Bastion không có public IP và không mở inbound SSH/port 22.
- Người dùng không dùng shared admin credential hoặc long-lived access key.
- Bastion instance role dùng EKS Access Entry/RBAC tối thiểu; không có `cluster-admin`.
- Không tạo internal ALB trong phương án hiện tại.

## 2. Audit coverage thực tế

| Lớp log | Chứng minh được | Không chứng minh được |
|---|---|---|
| AWS SSO/CloudTrail | Principal mở/kết thúc SSM session, timestamp, source IP, Bastion target | Portal/path hoặc hành động HTTP bên trong tunnel |
| SSM shell log, nếu bật | Lệnh `kubectl port-forward` và output trong interactive shell | Nội dung của SSM port-forward tunnel |
| EKS control-plane audit, nếu bật | Bastion role gọi Kubernetes `pods/portforward`, namespace/pod và timestamp | Request HTTP chạy qua port-forward |
| Portal audit/access log, nếu có auth cá nhân | Hành động/request mà portal hỗ trợ ghi log | Không đảm bảo tồn tại cho mọi portal; anonymous/shared identity làm giảm attribution |

AWS xác nhận Session Manager không log nội dung của port-forward session. Vì vậy không được kết luận CloudTrail cho biết người dùng đã mở dashboard, xem trace hoặc bấm Start Loadgen.

Trong thiết kế này, CloudTrail chỉ thấy Bastion target và session document/parameters liên quan; nó **không tự biết Kubernetes Service đích**. Service đích chỉ có thể đối chiếu từ SSM shell log và EKS audit log nếu hai lớp này đã được bật.

## 3. Residual risk cần CDO07/Tech Lead xác nhận

```text
Audit được: ai mở phiên, lúc nào, từ đâu, vào Bastion nào;
có thể audit API port-forward nếu EKS audit log bật.

Không audit đầy đủ: người dùng đã thực hiện hành động HTTP nào
trong Grafana, Jaeger hoặc Loadgen.
```

Acceptance Criteria của SEC-05 yêu cầu portal private, private access cho Mentor/BTC, evidence trước/sau và rollback; không yêu cầu application-level audit. CDO08 đề nghị chấp nhận hạn chế trên cho phương án hiện tại, hoặc yêu cầu ticket riêng về portal SSO/application audit nếu compliance bắt buộc.

## 4. Phase 1 — Design review trước deploy

CDO07 vui lòng xác nhận:

- [ ] Mỗi Mentor/BTC/operator dùng AWS SSO identity cá nhân; không dùng shared admin profile.
- [ ] IAM Permission Set chỉ cho phép session vào đúng Bastion và đúng SSM documents.
- [ ] CloudTrail đang ghi SSM management events và có retention phù hợp.
- [ ] Session Manager preferences đã cấu hình CloudWatch/S3 shell logging, hoặc ghi rõ lý do không bật.
- [ ] EKS control-plane audit logging đang bật, hoặc residual gap được ghi nhận.
- [ ] Bastion role dùng EKS Access Entry/RBAC tối thiểu và không có `cluster-admin`.
- [ ] CDO07/Tech Lead chấp nhận residual risk không có application-level audit đầy đủ.

## 5. Phase 2 — Evidence verification sau deploy

CDO08 tạo một phiên test bằng identity cá nhân; CDO07 xác minh tối thiểu:

### CloudTrail

- [ ] Có `StartSession` và `TerminateSession`.
- [ ] Có user/role ARN, event time, source IP, Bastion instance ID và session document.
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

## 6. Phản hồi CDO07

```text
Phase 1 — Design review
Decision: APPROVE / APPROVE WITH CONDITIONS / REJECT
CloudTrail enabled: YES / NO
SSM shell logging enabled: YES / NO
EKS audit logging enabled: YES / NO
Application-level audit required for SEC-05: YES / NO
Residual risk accepted: YES / NO
Conditions:

Phase 2 — Evidence verification
StartSession/TerminateSession verified: PASS / FAIL
SSM shell evidence: PASS / FAIL / NOT ENABLED
EKS pods/portforward evidence: PASS / FAIL / NOT ENABLED
Public route restriction: PASS / FAIL
Private access: PASS / FAIL
Storefront/checkout/flagd verification: PASS / FAIL

Ngày duyệt:
Người duyệt:
Evidence link:
```

## 7. Nguồn tham chiếu

- [AWS Session Manager logging](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging.html) — port-forward session content không được log.
- [AWS Session Manager auditing](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-auditing.html) — CloudTrail ghi Session Manager API activity.
- [Amazon EKS control-plane logs](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html).
