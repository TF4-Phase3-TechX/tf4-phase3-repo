# CDO08-REL-21 - Review Request: Quy trình chốt RPO/RTO cho Mandate 20

**Gửi:** Hải (PM)
**Từ:** Nguyên (Techlead)
**Mục đích:** Trình bày quy trình sẽ dùng để đi từ RPO/RTO draft hiện có đến ADR ký chính thức, kèm bằng chứng đây là quy trình chuẩn ngành chứ không phải tự nghĩ ra, để PM duyệt trước khi team bắt tay vào chạy drill thật.

> **Về nguồn trích dẫn trong file này:** mọi trang dưới đây đã được tự vào đọc trực tiếp để xác minh nguyên văn (không chỉ tin bản tóm tắt của công cụ tìm kiếm). Mỗi nguồn có: link để bạn tự bấm vào đọc lại, nguyên văn tiếng Anh (copy chính xác), bản dịch tiếng Việt, và phần diễn giải ý nghĩa tách riêng - để phân biệt rõ đâu là dữ liệu gốc, đâu là suy luận của tôi.

---

## 1. Vấn đề cần PM duyệt hướng đi

Hiện đã có bản draft RPO/RTO cho từng store ([CDO08-REL-21-rpo-rto-matrix.md](../adr/CDO08-REL-21-rpo-rto-matrix.md)) và cadence/retention tương ứng ([CDO08-REL-21-backup-policy-matrix.md](../adr/CDO08-REL-21-backup-policy-matrix.md)). Nhưng đây **chỉ là con số đề xuất ban đầu, chưa đo thật** - câu hỏi đặt ra là: có ký ADR luôn với số draft này không, hay phải làm gì trước?

Trả lời: **không ký ngay** - phải đi qua đủ 5 bước dưới đây. Đây không phải quy trình team tự nghĩ ra, mà dựa theo cách AWS và Google SRE khuyến nghị cho việc chốt RPO/RTO.

## 2. Quy trình 5 bước

### Bước 1 - Đặt target draft (đã xong)

Đặt con số RPO/RTO ban đầu dựa trên mức độ quan trọng của dữ liệu + khả năng lý thuyết của cơ chế backup đang có (RDS PITR, ElastiCache snapshot...). Chưa cần đo thật ở bước này.

**Nguồn:** AWS Well-Architected Framework, Reliability Pillar, mục REL13-BP02
Link: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_for_recovery_disaster_recovery.html

> Nguyên văn: *"Define a disaster recovery (DR) strategy that meets your workload's recovery objectives. Choose a strategy such as backup and restore, standby (active/passive), or active/active."*
>
> Dịch: *"Định nghĩa một chiến lược DR đáp ứng mục tiêu khôi phục của workload. Chọn 1 chiến lược như backup-and-restore, standby (active/passive), hoặc active-active."*

> Nguyên văn (phân loại tier chiến lược): *"Backup and restore (RPO in hours, RTO in 24 hours or less): ... Using automated or continuous backups will permit point in time recovery (PITR), which can lower RPO to as low as 5 minutes in some cases."*
>
> Dịch: *"Backup và restore (RPO tính bằng giờ, RTO trong vòng 24 giờ hoặc ít hơn): ... Dùng backup tự động/liên tục cho phép point-in-time recovery (PITR), có thể hạ RPO xuống thấp tới 5 phút trong một số trường hợp."*

**Diễn giải:** AWS khuyến nghị định nghĩa chiến lược/target **trước** (đúng Bước 1). Chiến lược của mình (RDS restore ra instance mới) khớp tier "Backup and Restore" - baseline mặc định RPO tính bằng giờ, RTO tới 24 giờ, nhưng AWS xác nhận **PITR có thể hạ RPO xuống ~5 phút**. Đây là căn cứ cho đề xuất RPO 15 phút của `accounting` trong file matrix (chọn 15 phút để có buffer an toàn hơn mức tối thiểu 5 phút AWS ghi, vì chưa đo thật).

### Bước 2 - Xử lý các gap chặn đường trước khi test

Sửa nhanh các vấn đề khiến drill không chạy được hoặc không có ý nghĩa: GAP-01 và GAP-02 - xem [CDO08-REL-20-gap-register.md](../scan/CDO08-REL-20-gap-register.md).

**Nguồn:** SteadyOps - "Disaster Recovery Runbook Template: PostgreSQL + K8s"
Link: https://steadyops.best/articles/ha-dr-runbooks/

> Nguyên văn: *"RPO, RTO, owners, triggers, and stop conditions must exist before an incident."*
>
> Dịch: *"RPO, RTO, người chịu trách nhiệm, điều kiện kích hoạt, và điều kiện dừng phải tồn tại từ trước khi sự cố xảy ra."*

**Diễn giải:** Toàn bộ điều kiện vận hành (bao gồm ai được xoá backup, ai chịu trách nhiệm) phải rõ ràng **trước khi** thử nghiệm/xảy ra sự cố thật - không phải để đó rồi tính sau.

### Bước 3 - Chạy drill thật để đo số thật (chưa làm - task REL-26)

Không có cách tính RTO/RPO chính xác bằng suy đoán - phải restore thật, bấm giờ thật, so dữ liệu thật.

**Nguồn 1:** AWS Well-Architected Framework, "Back up data"
Link: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/back-up-data.html

> Nguyên văn: *"Back up data, applications, and configuration to meet requirements for recovery time objectives (RTO) and recovery point objectives (RPO)."* Trang này dẫn tới mục con **"REL09-BP04 Perform periodic recovery of the data to verify backup integrity and processes"**.
>
> Dịch: *"Backup dữ liệu, ứng dụng và cấu hình để đáp ứng yêu cầu RTO/RPO."* Mục con: *"Thực hiện khôi phục dữ liệu định kỳ để xác minh backup còn toàn vẹn và quy trình còn đúng."*

**Nguồn 2:** Google Cloud Blog - "SRE principles in practice for business continuity" (bài chính chủ Google, thay cho nguồn O'Reilly cũ đã bị khoá trả phí không verify được)
Link: https://cloud.google.com/blog/products/management-tools/sre-principles-in-practice-for-business-continuity

> Nguyên văn: *"For more than a decade, extensive disaster recovery planning and testing has been a key part of SRE's practice. At Google, we regularly conduct disaster recovery testing, or DiRT for short: a regular, coordinated set of both real and fictitious incidents and outages across the company to test everything from our technical systems to processes and people. Yes, that's right—we intentionally bring down parts of our production services as part of these exercises. To avoid affecting our users, we use capacity that is unneeded at the time of the test; if engineers can't find the fix quickly, we'll stop the test before the capacity is needed again."*
>
> Dịch: *"Hơn một thập kỷ nay, việc lên kế hoạch và test khôi phục sự cố (disaster recovery) luôn là phần cốt lõi trong cách làm việc của SRE. Tại Google, chúng tôi thường xuyên chạy disaster recovery testing, gọi tắt là DiRT: một chuỗi sự kiện định kỳ, có tổ chức, gồm cả sự cố thật và giả định trên toàn công ty, để test mọi thứ từ hệ thống kỹ thuật cho tới quy trình và con người. Đúng vậy - chúng tôi **cố ý** làm sập một phần dịch vụ production như một phần của bài test này. Để không ảnh hưởng người dùng thật, chúng tôi dùng phần tài nguyên dư thừa lúc đó; nếu kỹ sư không tìm ra cách sửa kịp, bài test sẽ dừng trước khi phần tài nguyên đó cần dùng lại."*
>
> Nguyên văn (giá trị của việc test): *"This kind of testing takes time, but it pays off in the long run. Rigorous testing lets our SRE teams find unknown weaknesses, blind spots, and edge cases, and create processes to fix them."*
>
> Dịch: *"Kiểu test này tốn thời gian, nhưng về lâu dài xứng đáng. Test kỹ giúp đội SRE tìm ra điểm yếu chưa biết, điểm mù, và edge case, rồi tạo quy trình để sửa."*

**Diễn giải:** Google - công ty vận hành hệ thống lớn nhất - vẫn phải **cố ý gây sự cố thật** để biết hệ chịu được không, không dựa vào suy đoán. Vai trò trong drill (theo SteadyOps, cùng nguồn Bước 2): cần 1 người **"incident commander"** (điều phối, chịu trách nhiệm báo cáo) và 1 người **"recovery operator"** (bấm lệnh restore thật) - team nhỏ như TF này có thể để Techlead kiêm cả 2, hoặc Techlead điều phối còn owner từng store bấm lệnh.

### Bước 4 - Điều chỉnh nếu số đo được không khớp target

So sánh số đo thật (bước 3) với target draft (bước 1). Nếu số đo tệ hơn target → hoặc cải thiện cơ chế, hoặc sửa lại target cho khớp thực tế và ghi rõ lý do - không giữ nguyên số ảo ban đầu.

**Nguồn:** SteadyOps (cùng nguồn Bước 2)

> Nguyên văn: *"A clean restore drill is the evidence that turns backups into a recovery strategy, and every drill should produce measured results and owned improvements."*
>
> Dịch: *"Một lần restore drill sạch chính là bằng chứng biến backup thành 1 chiến lược khôi phục thật sự, và mỗi lần drill đều phải cho ra kết quả đo được cùng những cải thiện có người chịu trách nhiệm."*

**Diễn giải:** Kết quả drill luôn phải dẫn tới 1 trong 2: xác nhận số đạt, hoặc 1 hành động cải thiện cụ thể có người chịu trách nhiệm - không được kết thúc mà không có kết luận rõ ràng.

### Bước 5 - Ký ADR với số đã chứng minh

Chỉ sau khi có bằng chứng đo thật (bước 3-4) mới chuyển [CDO08-REL-21-adr-draft.md](../adr/CDO08-REL-21-adr-draft.md) từ trạng thái DRAFT sang SIGNED, kèm tên người ký + ngày ký.

**Nguồn:** chính văn bản Mandate 20 (nội bộ)
Link: [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md), yêu cầu #4

> Nguyên văn: *"Không chấp nhận 'đã bật backup nhưng chưa từng restore thử' - đó chính là chỗ hầu hết đội gãy."*

**Diễn giải:** Mandate tự đặt ra đúng nguyên tắc này, không phải team tự thêm vào.

## 3. Trạng thái hiện tại

| Bước | Trạng thái |
|---|---|
| 1. Đặt target draft | Đã xong |
| 2. Xử lý gap chặn đường (GAP-01, GAP-02) | Chưa làm |
| 3. Chạy drill thật (REL-26) | Chưa làm |
| 4. Điều chỉnh số nếu cần | Phụ thuộc bước 3 |
| 5. Ký ADR | Phụ thuộc bước 3-4 |

## 4. Đề xuất xin PM duyệt

- Xác nhận hướng đi 5 bước trên là được phép triển khai.
- Xin PM xác nhận chi phí/effort cho GAP-02 (MSK Connect + S3 Sink Connector - xem gap register).
- Sau khi PM duyệt, Techlead sẽ điều phối bước 2-3 và báo cáo kết quả để tiến hành bước 5.

---

## Nguồn tham khảo (đầy đủ, đã tự vào đọc để xác minh)

- [REL13-BP02 Use defined recovery strategies to meet the recovery objectives - AWS Well-Architected Reliability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_for_recovery_disaster_recovery.html)
- [Back up data - AWS Well-Architected Reliability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/back-up-data.html)
- [Disaster Recovery Runbook Template: PostgreSQL + K8s - SteadyOps](https://steadyops.best/articles/ha-dr-runbooks/)
- [SRE principles in practice for business continuity - Google Cloud Blog](https://cloud.google.com/blog/products/management-tools/sre-principles-in-practice-for-business-continuity)
- [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) (nội bộ)
