# ADR-001: Tách biệt quyền Audit và Platform (Separation of Duties)

**Ngày:** 2026-07-08
**Trạng thái:** Accepted
**Người quyết định:** CDO-07 (Audit Lead)
**Người review:** Toàn TF4
**Pillar liên quan:** Auditability, Security

---

## 1. Bối cảnh (Context)

Trong TF4, có hai luồng công việc song song:

- **Platform/DevOps (CDO-04, CDO-08):** Triển khai và cấu hình hạ tầng (Terraform, Helm, Kubernetes).
- **Audit (CDO-07):** Kiểm toán, xác minh tính toàn vẹn của hệ thống và thu thập bằng chứng.

Nếu team Audit cũng có quyền thay đổi hạ tầng, thì không thể đảm bảo tính khách quan khi kiểm toán — một người không thể vừa thực thi vừa kiểm tra chính công việc của mình. Đây là nguyên tắc **Separation of Duties** trong security compliance.

---

## 2. Quyết định (Decision)

**CDO-07 (Audit) chỉ sử dụng các quyền Read-only trên AWS:**

```
CloudTrail:read
IAM:read
Access Analyzer:read
AWS Config:read
CloudWatch Logs:read
S3:read
```

**Mọi thay đổi hạ tầng phải được thực hiện bởi CDO-04 hoặc CDO-08 qua Terraform/Helm (IaC).** CDO-07 không được và không cần quyền write vào bất kỳ resource AWS nào.

---

## 3. Lý do (Rationale)

| Lý do | Giải thích |
|---|---|
| Separation of Duties | Audit không thể kiểm tra công việc của chính mình |
| Audit trail integrity | Nếu Audit có quyền write, họ có thể vô tình (hoặc cố ý) thay đổi log/evidence |
| Least Privilege | Audit chỉ cần đọc, không cần thực thi |
| Compliance | Nguyên tắc phổ biến trong SOC 2, ISO 27001 |
| Trách nhiệm rõ ràng | Mọi thay đổi infra đều có owner cụ thể (CDO-04/08), Audit chỉ verify |

---

## 4. Hệ quả (Consequences)

**Tích cực:**
- Audit trail không bị ô nhiễm bởi hành động của chính team Audit.
- Mọi thay đổi hạ tầng đều truy được về CDO-04 hoặc CDO-08 (accountability rõ ràng).
- CDO-07 có thể verify độc lập mà không conflict of interest.

**Rủi ro / Trade-off:**
- CDO-07 phụ thuộc vào CDO-04/08 để thực thi các yêu cầu (ví dụ: bật CloudTrail, EKS logs).
- Có thể tạo bottleneck nếu CDO-04/08 không phản hồi yêu cầu kịp thời.

**Mitigation:**
- CDO-07 viết ticket yêu cầu rõ ràng với acceptance criteria cụ thể.
- Escalate qua PM/Lead nếu bị block quá 24h.

---

## 5. Các thay thế đã xem xét (Alternatives Considered)

| Phương án | Lý do không chọn |
|---|---|
| Cấp quyền Admin cho Audit | Vi phạm Separation of Duties; Audit có thể tự modify rồi tự verify |
| Cấp quyền Write có giới hạn | Vẫn tạo conflict of interest; khó kiểm soát scope |
| Không phân quyền riêng | Không có accountability rõ ràng giữa các nhóm |

---

## 6. Tham chiếu (References)

- `docs/audit/TEAM_ASSIGNMENT.md` — Bảng phân công quyền hạn
- `docs/audit/DELEGATED_TASKS_P0.md` — Danh sách task ủy quyền cho Platform
- `docs/requirements/RULES.md` Section 4 — Phân trụ pillar
