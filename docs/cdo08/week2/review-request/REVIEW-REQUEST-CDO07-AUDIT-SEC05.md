# [REVIEW & VERIFY REQUEST] CDO07 — Audit Review cho CDO08-SEC-05 (Ingress Hardening)

| Thông tin | Giá trị |
|-----------|---------|
| Từ | CDO08 |
| Đến | CDO07 (Audit/Compliance) |
| Backlog ID | `CDO08-SEC-05` |
| Ngày gửi | 2026-07-13 |
| Trạng thái | **Đợi Phê Duyệt Thiết Kế (Phase 1) & Nghiệm Thu Bằng Chứng (Phase 2)** |

---

## 1. Bối cảnh & Phương án đề xuất

Nhằm tuân thủ **MANDATE-01** (private hóa các cổng vận hành), CDO08 đề xuất:
1. Sửa Envoy Proxy (`envoy.tmpl.yaml`) trả `404` trực tiếp cho 6 routes vận hành khi truy cập từ public internet.
2. Dựng **EC2 Bastion trong private subnet kết hợp AWS SSM Session Manager** để làm cổng truy cập an toàn cho người vận hành (BTC, Team).

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
- [ ] **Độ tin cậy của Audit Trail:** Xác nhận log sự kiện `StartSession` trên CloudTrail là đủ bằng chứng kiểm toán cho truy cập cổng vận hành.

### Giai đoạn 2 — Xác nhận khả năng Audit (Sau khi deploy):
CDO07 kiểm tra thực tế trên CloudTrail:
- [ ] **Xác nhận có thể Audit:** Chạy query hoặc kiểm tra CloudTrail console xem event `StartSession` đã được ghi nhận thành công và đầy đủ thông tin (user ARN, timestamp, source IP, target service) khi có phiên truy cập thử nghiệm.

```text
Phản hồi từ CDO07 (Phê duyệt & Xác nhận):
✅ Giai đoạn 1: CDO07 Xác nhận thiết kế SEC-05 đáp ứng trụ Auditability.
✅ Giai đoạn 2: CDO07 Xác nhận CloudTrail logs đã ghi nhận thành công dữ liệu audit thực tế.
Ngày duyệt: ___
Người duyệt: ___
```
