# [REVIEW REQUEST] CDO04 — Cost & Capacity Review cho CDO08-REL-01 (Replica Availability)

| Thông tin | Giá trị |
|-----------|---------|
| Từ | CDO08 |
| Đến | CDO04 (Cost/Capacity) |
| Backlog ID | `CDO08-REL-01` |
| Ngày gửi | 2026-07-13 |
| Deadline approve | **2026-07-14 (trước khi deploy)** |

---

## 1. Bối cảnh & Yêu cầu thay đổi

Để loại bỏ Single Point of Failure (SPOF) cho luồng mua hàng nhạy cảm (Checkout path), CDO08 đề xuất nâng số lượng replicas từ **1 lên 2** đối với 7 critical stateless services:
`frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `shipping`, `product-catalog`.

CDO04 cần review tác động tài nguyên (Capacity/Headroom) trên 2 worker nodes hiện tại để tránh việc kích hoạt AWS Auto Scaling Group kéo thêm node mới làm phình to chi phí cố định (MANDATE-02).

---

## 2. Ước tính Tác động Tài nguyên (Capacity Impact)

Nâng từ 1 lên 2 replicas sẽ tạo thêm **7 pods** mới chạy trên cluster. 

### Tác động Memory Limit lý thuyết:

| Service | Memory limit/pod | Replica tăng | Memory limit tăng thêm |
|---------|-----------------|--------------|-----------------------|
| `frontend-proxy` | 65 Mi | +1 | 65 Mi |
| `frontend` | 250 Mi | +1 | 250 Mi |
| `checkout` | 20 Mi | +1 | 20 Mi |
| `cart` | 160 Mi | +1 | 160 Mi |
| `payment` | 140 Mi | +1 | 140 Mi |
| `shipping` | 20 Mi | +1 | 20 Mi |
| `product-catalog` | 20 Mi | +1 | 20 Mi |
| **Tổng cộng** | | **+7 pods** | **675 Mi** |

> ⚠️ Đây là Memory **Limit**, thực tế scheduler của Kubernetes dựa vào Memory **Request** (hiện tại chart chưa định nghĩa rõ CPU/Memory requests nên scheduler chủ yếu dùng limit hoặc default policy ngoài chart).

---

## 3. Các kịch bản Chi phí (Cost Scenarios)

Kubernetes không tính phí theo số pod hay replica. Chi phí chỉ thực sự tăng khi các pod mới không còn vừa trên 2 worker nodes hiện có (`t3.large`), ép cluster phải scale thêm node thứ 3.

| Kịch bản | Số Node | Chi phí tăng thêm | Ghi chú |
|----------|---------|-------------------|---------|
| **2 replicas fit vừa 2 node** | 2 | **$0 / tuần** | Chỉ sử dụng phần tài nguyên dư thừa (headroom) đang có. |
| **Phải scale lên 3 node** | 3 | **+~$14.40 / tuần** | Thêm 1 instance `t3.large` ($14.03) và 20GB gp3 root volume ($0.37). |
| **Phải scale lên 4 node** | 4 | **+~$28.80 / tuần** | Thêm 2 instances `t3.large`. |

*Chưa bao gồm các chi phí usage-based tiềm ẩn như: telemetry volume tăng lên, cross-AZ traffic tăng khi pod phân bố đa zone, hoặc phí CPU surplus credit của dòng burstable T3.*

---

## 4. CDO04 Check-off & Approve

CDO04 vui lòng thực hiện đánh giá metrics và xác nhận:

- [ ] **Khả năng đáp ứng của Node (Headroom):** Xác nhận 2 worker nodes hiện tại còn đủ dung lượng RAM/CPU để chạy thêm 7 pods (tổng cộng ~675 Mi Limit) mà không bị nghẽn CPU hoặc OOM.
- [ ] **Kịch bản chi phí dự kiến:** Xác định xem phương án 2 replicas sẽ rơi vào kịch bản nào (fit vừa 2 node hay cần scale thêm node).
- [ ] **Ủy quyền Rollout:** Đồng ý cho phép CDO08 nâng replicas lên 2 theo quy trình cuốn chiếu từng service.

```text
Phản hồi từ CDO04:
✅ CDO04 Xác nhận capacity: [Fit vừa 2 node / Cần scale node]
✅ CDO04 Approve thiết kế REL-01.
Ngày duyệt: ___
Người duyệt: ___
```
