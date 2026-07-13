# [REVIEW REQUEST] CDO04 — Cost Review cho CDO08-SEC-05 (Ingress Hardening)

| Thông tin | Giá trị |
|-----------|---------|
| Từ | CDO08 |
| Đến | CDO04 (Cost) |
| Backlog ID | `CDO08-SEC-05` |
| Ngày gửi | 2026-07-13 |
| Deadline approve | **2026-07-14 (trước khi deploy)** |

---

## 1. Bối cảnh & Yêu cầu thay đổi

Theo yêu cầu của **MANDATE-01**, toàn bộ các operational portals (Grafana, Jaeger, Load Generator) phải được chuyển về trạng thái private (chỉ người có thẩm quyền truy cập).

CDO08 đề xuất phương án dùng **AWS SSM Session Manager qua EC2 Bastion** chạy trong private subnet, đồng thời block các public routes trên Envoy Proxy.

CDO04 cần review phương án này để đảm bảo chi phí hạ tầng tối ưu và không vượt trần ngân sách `$300/tuần/TF`.

---

## 2. Chi tiết Chi phí & So sánh các phương án

| Phương án | Chi phí/tuần | Đánh giá vận hành & Cost |
|-----------|--------------|-------------------------|
| **AWS SSM Session Manager (Bastion EC2)** | **~$3.5** | **Rẻ nhất có Audit Trail.** Chỉ tốn phí chạy 1 EC2 `t3.nano` ở chế độ rảnh. SSM Session Manager hoàn toàn miễn phí. |
| SSH Bastion (port 22 public) | ~$3.5 | Bằng tiền EC2 nhưng tốn thêm nhiều công sức/giờ làm việc để quản trị SSH keys và sửa Security Group khi IP thay đổi. |
| VPN Gateway | ~$20 | Đắt đỏ, cấu hình phức tạp, vượt quá nhu cầu thực tế của team. |
| Internal ALB | +$20 | Đắt, phát sinh chi phí cố định cho một ALB mới chạy nội bộ. |

### Chi phí tăng thêm dự kiến cho SEC-05:

* **EC2 Instance `t3.nano` (Bastion):** ~$3.5/tuần
* **SSM Session Manager:** $0
* **Tổng cộng phát sinh:** **~$3.5/tuần** (Nằm sâu dưới hạn mức ngân sách còn lại của TF4).

---

## 3. CDO04 Check-off & Approve

CDO04 vui lòng xác nhận các hạng mục bên dưới:

- [ ] **Headroom Ngân sách:** Xác nhận chi phí tăng thêm **~$3.5/tuần** nằm trong ngân sách `$300/tuần` và không gây rủi ro tài chính.
- [ ] **Lựa chọn tối ưu:** Đồng ý SSM Session Manager qua EC2 Bastion là phương án tối ưu nhất về chi phí so với các giải pháp khác.

```text
Phản hồi từ CDO04:
✅ CDO04 Approve chi phí SEC-05: EC2 t3.nano ~$3.5/tuần.
Ngày duyệt: ___
Người duyệt: ___
```
