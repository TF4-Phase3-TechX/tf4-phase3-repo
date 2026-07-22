# CDO08-REL-21 - Review Request: Quy trình chốt RPO/RTO cho Mandate 20

**Gửi:** Hải (PM)
**Từ:** Nguyên (Techlead)
**Mục đích:** Trình bày quy trình sẽ dùng để đi từ RPO/RTO draft hiện có đến ADR ký chính thức, kèm bằng chứng đây là quy trình chuẩn ngành chứ không phải tự nghĩ ra, để PM duyệt trước khi team bắt tay vào chạy drill thật.

---

## 1. Vấn đề cần PM duyệt hướng đi

Hiện đã có bản draft RPO/RTO cho từng store ([CDO08-REL-21-rpo-rto-matrix.md](../adr/CDO08-REL-21-rpo-rto-matrix.md)) và cadence/retention tương ứng ([CDO08-REL-21-backup-policy-matrix.md](../adr/CDO08-REL-21-backup-policy-matrix.md)). Nhưng đây **chỉ là con số đề xuất ban đầu, chưa đo thật** - câu hỏi đặt ra là: có ký ADR luôn với số draft này không, hay phải làm gì trước?

Trả lời: **không ký ngay** - phải đi qua đủ 5 bước dưới đây. Đây không phải quy trình team tự bịa, mà là cách AWS và Google SRE khuyến nghị chính thức cho việc chốt RPO/RTO.

## 2. Quy trình 5 bước

### Bước 1 - Đặt target draft (đã xong)

Đặt con số RPO/RTO ban đầu dựa trên mức độ quan trọng của dữ liệu + khả năng lý thuyết của cơ chế backup đang có (RDS PITR, ElastiCache snapshot...). Chưa cần đo thật ở bước này.

> **Evidence:** AWS Well-Architected Framework, Reliability Pillar, mục *"REL13-BP02 Use defined recovery strategies to meet the recovery objectives"* (docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_for_recovery_disaster_recovery.html): "Define a disaster recovery (DR) strategy that meets your workload's recovery objectives, choosing a strategy such as backup and restore, standby (active/passive), or active/active." - AWS khuyến nghị **định nghĩa strategy/target trước**, đây chính xác là Bước 1.
>
> Tài liệu này cũng phân loại chiến lược DR theo tier: **Backup and Restore** (RTO/RPO tính bằng giờ - đây là chiến lược team đang dùng), Pilot Light/Warm Standby (phút/giây), Active-Active (gần 0). Việc đề xuất RPO 15 phút cho `accounting` (thay vì "vài giờ" theo baseline chung của tier Backup and Restore) là vì RDS PITR (continuous log backup) đã siết tier này chặt hơn baseline mặc định - có ghi rõ rationale trong file matrix.

### Bước 2 - Xử lý các gap chặn đường trước khi test

Sửa nhanh các vấn đề khiến drill không chạy được hoặc không có ý nghĩa: cụ thể là GAP-01 (role CI xoá được backup không giới hạn) và quyết định hướng cho GAP-02 (MSK không có backup) - xem [CDO08-REL-20-gap-register.md](../scan/CDO08-REL-20-gap-register.md).

> **Evidence:** SteadyOps, *"Disaster Recovery Runbook Template: PostgreSQL + K8s"* (steadyops.best/articles/ha-dr-runbooks/): "RPO, RTO, owners, triggers, and stop conditions must exist **before an incident**." - tức toàn bộ điều kiện vận hành (bao gồm ai được xoá backup, ai chịu trách nhiệm) phải rõ ràng **trước khi** thử nghiệm/xảy ra sự cố thật, không phải để đó rồi tính sau.

### Bước 3 - Chạy drill thật để đo số thật (chưa làm - task REL-26)

Không có cách tính RTO/RPO chính xác bằng suy đoán - phải restore thật, bấm giờ thật, so dữ liệu thật.

> **Evidence 1:** AWS Well-Architected, *"Back up data"* (docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/back-up-data.html): "Regular, **automated restoration tests with actual RTO/RPO metrics are essential**."
>
> **Evidence 2:** Google SRE - chương trình **DiRT (Disaster Recovery Testing)**, mô tả trong *Chaos Engineering* (O'Reilly, oreilly.com/library/view/chaos-engineering/9781492043850/ch05.html): "The disaster recovery testing performed internally at Google is a coordinated set of events... in which a group of engineers plan and execute real and fictitious outages for a defined period of time to test the effective response of the involved teams... performed in a controlled manner, so that they can be rolled back as quickly as possible by the proctors should the tests get out of hand." Motto của chương trình: **"Hope is not a strategy"** - tức không được "hy vọng" backup chạy tốt, phải thử thật.
>
> **Vai trò trong drill** (theo SteadyOps): "a runbook needs an **incident commander** and **recovery operator** defined" - team nhỏ như TF này có thể để Techlead kiêm cả 2 vai, hoặc Techlead làm incident commander (điều phối, chịu trách nhiệm báo cáo) còn owner của từng store làm recovery operator (bấm lệnh restore thật).

### Bước 4 - Điều chỉnh nếu số đo được không khớp target

So sánh số đo thật (bước 3) với target draft (bước 1). Nếu số đo tệ hơn target → hoặc cải thiện cơ chế, hoặc sửa lại target cho khớp thực tế và ghi rõ lý do - không giữ nguyên số ảo ban đầu.

> **Evidence:** SteadyOps: "A clean restore drill is the evidence that turns backups into a recovery strategy, and **every drill should produce measured results and owned improvements**." - nghĩa là kết quả drill luôn phải dẫn tới 1 trong 2: xác nhận số đạt, hoặc 1 hành động cải thiện cụ thể có người chịu trách nhiệm.

### Bước 5 - Ký ADR với số đã chứng minh

Chỉ sau khi có bằng chứng đo thật (bước 3-4) mới chuyển [CDO08-REL-21-adr-draft.md](../adr/CDO08-REL-21-adr-draft.md) từ trạng thái DRAFT sang SIGNED, kèm tên người ký + ngày ký.

> **Evidence:** Chính [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) yêu cầu #4: *"Không chấp nhận 'đã bật backup nhưng chưa từng restore thử' - đó chính là chỗ hầu hết đội gãy."* - mandate tự đặt ra đúng nguyên tắc này, không phải team tự thêm.

## 3. Trạng thái hiện tại

| Bước | Trạng thái |
|---|---|
| 1. Đặt target draft | ✅ Đã xong |
| 2. Xử lý gap chặn đường (GAP-01, GAP-02) | ⏳ Chưa làm |
| 3. Chạy drill thật (REL-26) | ⏳ Chưa làm |
| 4. Điều chỉnh số nếu cần | ⏳ Phụ thuộc bước 3 |
| 5. Ký ADR | ⏳ Phụ thuộc bước 3-4 |

## 4. Đề xuất xin PM duyệt

- Xác nhận hướng đi 5 bước trên là được phép triển khai.
- Xác nhận mức chấp nhận rủi ro tạm thời cho MSK `orders` (bước 2) - vì đây là quyết định business (chấp nhận rủi ro mất event hay đầu tư thêm archival), không phải quyết định kỹ thuật thuần tuý.
- Sau khi PM duyệt, Techlead sẽ điều phối bước 2-3 và báo cáo kết quả để tiến hành bước 5.

---

## Nguồn tham khảo (đầy đủ)

- [REL13-BP02 Use defined recovery strategies to meet the recovery objectives - AWS Well-Architected Reliability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_for_recovery_disaster_recovery.html)
- [Back up data - AWS Well-Architected Reliability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/back-up-data.html)
- [Disaster Recovery Runbook Template: PostgreSQL + K8s - SteadyOps](https://steadyops.best/articles/ha-dr-runbooks/)
- [Google DiRT: Disaster Recovery Testing - Chaos Engineering (O'Reilly)](https://www.oreilly.com/library/view/chaos-engineering/9781492043850/ch05.html)
- [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) (nội bộ)
