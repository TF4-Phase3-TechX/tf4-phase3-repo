# CDO08-REL-21 - Vì sao restore phải ra môi trường tách biệt (và vì sao GAP-06 không cần migrate instance)

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20, yêu cầu #3 (*"Point-in-time restore chứng minh được... ra môi trường tách biệt"*)
**Mục đích:** Giải thích căn cứ kỹ thuật + lý do vận hành cho quyết định restore isolation ở mục 6 của [CDO08-REL-21-adr.md](CDO08-REL-21-adr.md), và làm rõ vì sao GAP-06 ([CDO08-REL-20-gap-register.md](../scan/CDO08-REL-20-gap-register.md)) đổi hướng xử lý từ "tách RDS instance riêng cho `accounting`" sang "runbook restore-theo-schema" - không cần migrate hạ tầng.

---

## 1. Câu hỏi đặt ra

`accounting`, `catalog`, `reviews` là 3 schema trong cùng 1 database `otel`, chung 1 RDS instance (`techx-corp-chart/postgresql/init.sql`). Khi cần restore `accounting` về một mốc trước sự cố, có 2 cách nghĩ tới:

- **(A) Restore/merge thẳng vào instance production đang chạy** - nghe có vẻ nhanh hơn, ít bước hơn.
- **(B) Restore ra một instance tạm, tách biệt, rồi mới lấy đúng phần `accounting` merge ngược vào production** - đây là cách mandate yêu cầu (yêu cầu #3) và là cách RDS PITR vận hành mặc định.

Mục này trả lời: tại sao luôn phải đi theo (B), và hệ quả là gì cho GAP-06.

## 2. Ràng buộc kỹ thuật: RDS không có API restore tại chỗ

> Đã tự vào đọc trực tiếp trang AWS bên dưới để xác minh nguyên văn, không chỉ tin bản tóm tắt của công cụ tìm kiếm.

**Nguồn - AWS RDS User Guide, "Restoring a DB instance to a specified time"**
Link: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIT.html

Nguyên văn tiếng Anh:
> "You can restore a DB instance to a specific point in time, **creating a new DB instance without modifying the source DB instance**."

Dịch: *"Bạn có thể restore một DB instance về một mốc thời gian cụ thể, việc này sẽ **tạo ra một DB instance mới mà không chỉnh sửa gì DB instance nguồn**."*

Tài liệu CLI của cùng trang cũng xác nhận: lệnh `restore-db-instance-to-point-in-time` bắt buộc tham số `--target-db-instance-identifier` (tên instance đích, phải **khác** và **duy nhất** so với instance nguồn) - tức là API không có chế độ "restore instance X tại chỗ", chỉ có "restore ra thành instance Y mới".

**Ý nghĩa:** phương án (A) - "restore/merge thẳng vào production" - **không tồn tại như một API/thao tác của RDS**. Dù muốn hay không, bước đầu tiên của bất kỳ restore nào cũng luôn là tạo ra một instance mới, tách biệt hoàn toàn khỏi production. Đây là ràng buộc của dịch vụ, không phải lựa chọn quy trình của team.

## 3. Vì sao vẫn nên giữ pattern "restore-ra-riêng-rồi-mới-merge" dù có thể viết script merge thẳng

Ràng buộc ở mục 2 chỉ ngăn việc "restore tại chỗ" ở cấp **instance**. Về lý thuyết, sau khi có instance tạm, team vẫn có thể viết script `pg_dump`/`pg_restore` để đẩy dữ liệu **thẳng** vào production ngay khi vừa restore xong, không qua bước kiểm tra. Nhưng làm vậy bỏ lỡ đúng phần giá trị mà yêu cầu #3 của mandate muốn có:

- **Verify trước khi chạm production**: nếu chọn sai mốc thời gian (VD: tưởng lỗi xảy ra lúc 14:00 nhưng dữ liệu đã hỏng từ 13:45), restore ra instance tạm cho phép kiểm tra dữ liệu đúng chưa (query thử, đối chiếu số lượng bản ghi/nghiệp vụ) **trước khi** merge. Sai thì huỷ instance tạm, thử mốc khác - production không bị ảnh hưởng. Nếu merge thẳng mà sai mốc, production đã bị ghi đè sai, phải restore lại lần 2 (RTO nhân đôi).
- **Production không downtime trong lúc restore chạy**: PITR restore mất từ vài phút tới vài chục phút tuỳ kích thước DB. Restore ra instance riêng nghĩa là instance production **vẫn phục vụ khách bình thường** suốt thời gian đó - đúng ràng buộc của mandate: *"Không đè / không phá production khi drill - restore ra môi trường tách biệt, không làm rớt khách thật."*
- **Giới hạn thiệt hại nếu script merge có bug**: nếu script dump/restore sai (nhầm schema, sai điều kiện, quên FK...), thiệt hại chỉ nằm ở instance tạm (xoá đi làm lại), không lan sang production như khi chạy thẳng lên production.

## 4. Áp dụng vào GAP-06: vì sao không cần tách `accounting` ra instance riêng

Rủi ro GAP-06 nêu ra: *"restore `accounting` để sửa lỗi sẽ vô tình làm mất luôn dữ liệu mới ghi vào `reviews` trong cùng khoảng thời gian."* Rủi ro này **chỉ đúng nếu quy trình restore là "cutover" toàn instance** - tức là thay thế nguyên instance production bằng instance vừa PITR-restore (bao gồm cả 3 schema tại mốc cũ), làm `reviews`/`catalog` bị lùi lại theo.

Nhưng theo mục 2-3 ở trên, quy trình đúng (và bắt buộc theo yêu cầu #3) không bao giờ là cutover toàn instance - mà là:

1. PITR restore **toàn instance** (`accounting`+`catalog`+`reviews`) ra một instance tạm, tách biệt - production không bị đụng.
2. Từ instance tạm, **chỉ lấy đúng schema `accounting`**: `pg_dump -n accounting <instance-tam> > accounting.sql`.
3. Verify dữ liệu dump ra đúng mốc thời gian mong muốn (đối chiếu số đơn hàng, tổng tiền... với kỳ vọng).
4. Merge `accounting.sql` vào instance production đang chạy (`psql`/`pg_restore`, hoặc script `INSERT/UPDATE` theo bảng nếu cần giữ lại phần dữ liệu mới hơn phát sinh trong lúc restore).
5. Bước merge **chỉ chạm bảng của `accounting`** - `reviews` và `catalog` trên production không hề bị ghi đè, vì không có bước nào trong quy trình động tới chúng.
6. Xoá instance tạm sau khi xác nhận merge ổn.

Vì vậy: cả 5 yêu cầu của mandate đều đạt được **mà không cần tách `accounting` ra RDS instance riêng**:

| Yêu cầu mandate | Đạt được nhờ đâu |
|---|---|
| #1 Không sót store | Vẫn backup đủ 3 schema dù chung 1 instance (PITR áp dụng cho toàn instance) |
| #2 RPO/RTO theo tầng | RDS ghi transaction log lên S3 mỗi 5 phút (theo trang AWS ở mục 2) cho toàn instance - RPO không bị ảnh hưởng bởi việc chung hay tách instance. RTO của riêng `accounting` phụ thuộc bước dump/merge (schema nhỏ, nhanh hơn restore cả instance) |
| #3 Restore ra môi trường tách biệt | Tự động thoả mãn - bước 1 ở trên luôn tạo instance mới, đúng ràng buộc mục 2 |
| #4 Drill thật | Drill đúng quy trình 6 bước ở trên: gây lỗi `accounting` → PITR ra instance tạm → dump → verify → merge → xác nhận `reviews`/`catalog` trên production không đổi. Bằng chứng này **chứng minh isolation bằng quy trình**, không chỉ bằng hạ tầng |
| #5 An toàn backup | Không liên quan việc chung/tách instance |

**Trường hợp việc tách instance mới thật sự cần thiết**: khi sự cố ở cấp storage/instance (volume corrupt, ransomware mã hoá cả volume) buộc phải phục hồi nguyên instance, không còn gì để dump/merge chọn lọc. Đây là kịch bản xác suất thấp hơn nhiều so với các ví dụ mandate nêu (*"drop bảng / xoá item / ghi hỏng"* - mục 4 của mandate, toàn lỗi tầng ứng dụng), và không phải trọng tâm của GAP-06 (vốn xuất phát từ lo ngại restore-do-sửa-lỗi-migration, không phải mất nguyên volume).

## 5. Quyết định

GAP-06 **không cần task migrate `accounting` sang RDS instance riêng**. Thay vào đó: viết + drill **runbook restore-theo-schema** (6 bước ở mục 4) cho `accounting`, dùng đúng cơ chế PITR-restore-ra-instance-tạm sẵn có. Việc này:

- Thoả mãn đủ yêu cầu #1-#5 của mandate mà không cần thêm hạ tầng.
- Rẻ hơn, ít rủi ro hơn so với migrate schema + đổi connection string (vốn có rủi ro riêng: lỡ tay trong lúc migrate, phải test lại toàn bộ accounting service với DB endpoint mới).
- Chính runbook này **là** bằng chứng drill mà yêu cầu #4 đòi hỏi - không cần làm thêm việc gì khác để chứng minh isolation.

Đã cập nhật GAP-06 trong [CDO08-REL-20-gap-register.md](../scan/CDO08-REL-20-gap-register.md), cùng các bảng liên quan trong [CDO08-REL-21-rpo-rto-matrix.md](CDO08-REL-21-rpo-rto-matrix.md), [CDO08-REL-21-backup-policy-matrix.md](CDO08-REL-21-backup-policy-matrix.md), [CDO08-REL-21-adr.md](CDO08-REL-21-adr.md), và [CDO08-REL-21-summary.md](CDO08-REL-21-summary.md).

## Nguồn tham khảo

- [Restoring a DB instance to a specified time - Amazon RDS User Guide](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIT.html) - xác nhận PITR luôn tạo instance mới, không sửa instance nguồn; transaction log upload lên S3 mỗi 5 phút.
- [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - yêu cầu #3 (restore ra môi trường tách biệt) và ràng buộc (không đè/không phá production khi drill).
