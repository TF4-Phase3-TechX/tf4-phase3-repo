# 📋 BÁO CÁO KỸ THUẬT

# CHUYỂN ĐỔI PHƯƠNG ÁN BẢO VỆ CLOUDTRAIL TỪ PREVENTATIVE (SCP) SANG SELF-HEALING (EVENTBRIDGE + SSM AUTOMATION)

| Thuộc tính | Giá trị |
|------------|----------|
| **Người thực hiện (Owner)** | Đinh Văn Ty (Nhóm CDO-07 / Auditability) |
| **Dự án** | Task Force 4 — Enterprise Cloud Security & Compliance |
| **Mức độ ưu tiên** | 🔴 **CRITICAL** |

---

# 1. BỐI CẢNH VÀ MỤC TIÊU (CONTEXT & OBJECTIVES)

Trong khuôn khổ yêu cầu tuân thủ an toàn thông tin (**Mandate 12 - Anti-Blinding Audit Trail**), hệ thống ghi vết **AWS CloudTrail** phải được bảo vệ nghiêm ngặt nhằm đảm bảo tính liên tục (**Continuous Logging**) và chống lại các hành vi cố tình ngắt ghi log (`StopLogging`) hoặc xóa dấu vết (`DeleteTrail`) từ bất kỳ người dùng hoặc dịch vụ nào.

Ban đầu, nhóm đề xuất giải pháp **Preventative Control** bằng cách áp dụng **Service Control Policies (SCP)** ở cấp độ **AWS Organization** để chặn toàn bộ hành động `cloudtrail:StopLogging`.

Tuy nhiên, sau quá trình đánh giá kiến trúc thực tế, nhóm nhận thấy phương án này tồn tại những giới hạn kỹ thuật quan trọng của AWS và không đáp ứng đầy đủ mục tiêu bảo vệ.

---

# 2. LÝ DO NGHIÊN CỨU & NGHẼN KIẾN TRÚC VỚI SCP (TECHNICAL LIMITATIONS OF SCP)

Qua quá trình rà soát kiến trúc và cấu hình phân quyền trên hạ tầng hiện tại, việc áp dụng **SCP** để bảo vệ CloudTrail gặp các hạn chế sau:

## ❌ Giới hạn 1: SCP không có hiệu lực đối với Management Account

### Nguyên lý AWS

Mọi **Service Control Policy**, kể cả **Explicit Deny**, đều **không áp dụng** cho **Management Account (Master Account)** của AWS Organizations.

### Thực tế

Các tác vụ quản trị CloudTrail dùng chung cho toàn bộ Organization thường được thực hiện tại **Management Account** hoặc thông qua các IAM Role thuộc tài khoản này.

Do đó, nếu hành vi `StopLogging` xuất phát từ **Management Account**, SCP hoàn toàn không thể ngăn chặn.

---


# 3. GIẢI PHÁP THAY THẾ: TỪ PREVENTATIVE SANG SELF-HEALING

Nhận thấy không thể ngăn chặn tuyệt đối hành vi tắt CloudTrail bằng SCP trong mọi tình huống, nhóm **CDO-07**, do **Đinh Văn Ty** làm Owner, đã chuyển hướng thiết kế sang mô hình **Self-Healing (Reactive Control)**.

## 💡 Nguyên lý hoạt động

> **"Nếu không thể ngăn đối phương bấm nút tắt, hãy làm cho nút tắt trở nên vô dụng bằng cách tự động bật lại CloudTrail trong vòng vài giây."**

### Luồng hoạt động

```text
[StopLogging]
        │
        ▼
[CloudTrail Event]
        │
        ▼
[Amazon EventBridge Rule]
        │ (1–3 giây)
        ▼
[SSM Automation Runbook]
        │
        ▼
[cloudtrail:StartLogging]
        │
        ▼
[CloudTrail được bật trở lại]
```

---

# 4. BẢN THIẾT KẾ KỸ THUẬT & MÃ NGUỒN TERRAFORM (IMPLEMENTATION)

Toàn bộ hạ tầng **Self-Healing** được triển khai hoàn toàn bằng **Terraform (Infrastructure as Code)** nhằm đảm bảo:

- Tự động hóa
- Dễ kiểm toán
- Có thể tái sử dụng
- Quản lý phiên bản

## Các thành phần chính

### Amazon EventBridge Rule

**Tên Rule**

```text
security-remediation-cloudtrail-anti-blinding
```

**Chức năng**

- Lắng nghe thời gian thực các API Event từ `cloudtrail.amazonaws.com`
- Kích hoạt khi phát hiện sự kiện `StopLogging`

---

### Custom SSM Automation Document

**Tên Runbook**

```text
tf4-restore-cloudtrail-logging
```

**Chức năng**

- Tự động gọi API:

```text
cloudtrail:StartLogging
```

- Khôi phục Trail:

```text
tf4-general-cloudtrail
```

- Retry tối đa **03 lần** nếu thất bại.

---

### Least Privilege IAM Roles

#### SSM Automation Role

Chỉ được phép:

- `cloudtrail:StartLogging`

trên đúng ARN của Trail thuộc dự án.

#### EventBridge Role

Chỉ được phép:

- `ssm:StartAutomationExecution`
- `iam:PassRole`

để kích hoạt SSM Automation.

---

# 5. KẾT QUẢ ĐẠT ĐƯỢC & GIÁ TRỊ KIỂM TOÁN (AUDIT VALUE)

## 🚀 Hiệu năng thực tế (Expected - cần kiểm chứng lại)

### Thời gian phục hồi (RTO)

CloudTrail được khôi phục tự động trong vòng:

**1 – 3 giây**

sau khi phát hiện sự kiện `StopLogging`.

### Độ tin cậy

Giải pháp khắc phục hoàn toàn điểm yếu của SCP đối với **Management Account**, đồng thời không ảnh hưởng đến quy trình DevOps và CI/CD.

---

## 📜 Giá trị chứng minh kiểm toán (Audit Evidence) (Sample)

Khi có hành vi cố tình tắt CloudTrail, hệ thống không chỉ tự khôi phục mà còn tạo ra **hai sự kiện liên tiếp** phục vụ điều tra pháp y.

| Event Time | Event Name | User / Principal | Ý nghĩa kiểm toán |
|------------|------------|------------------|-------------------|
| 10:00:00Z | StopLogging | `arn:aws:iam::...:user/tester` | Ghi nhận chính xác đối tượng thực hiện hành vi tắt CloudTrail |
| 10:00:02Z | StartLogging | `arn:aws:iam::...:role/SSM-AutoRemediate-Role` | SSM Automation tự động khôi phục CloudTrail sau khoảng 2 giây |

Nhờ đó, ngay cả khi có hành vi cố tình làm mù hệ thống ghi log (Anti-Blinding), chuỗi bằng chứng phục vụ điều tra vẫn được bảo toàn.

---

# 6. KẾT LUẬN VÀ ĐỀ XUẤT (CONCLUSION)

## Kết luận

Giải pháp **Self-Healing** sử dụng **Amazon EventBridge kết hợp SSM Automation** là phương án phù hợp hơn so với **Service Control Policies (SCP)** đối với kiến trúc **AWS Multi-Account** hiện tại.

Giải pháp vừa đáp ứng yêu cầu của **Mandate 12**, vừa đảm bảo:

- Không ảnh hưởng tới quy trình DevOps
- Không cản trở CI/CD
- Có khả năng tự động khôi phục CloudTrail
- Gia tăng khả năng điều tra pháp y và đáp ứng yêu cầu kiểm toán

---

## Kiến nghị mở rộng: Triển khai AWS Config cho Continuous Compliance

### 1. Sự cần thiết (The "Why")

Nếu **Amazon EventBridge** đóng vai trò là **"Cảnh sát phản ứng nhanh"** (phát hiện và xử lý ngay khi có sự kiện), thì **AWS Config** đóng vai trò là **"Thanh tra định kỳ"**, liên tục kiểm tra trạng thái cấu hình của hệ thống.

Việc kết hợp cả hai dịch vụ sẽ giúp giải quyết triệt để bài toán **Configuration Drift (Sai lệch cấu hình)** và nâng cao khả năng kiểm toán.

Cụ thể:

- **Phát hiện các thay đổi ngoại lệ:** Một số thay đổi cấu hình hoặc sai lệch trạng thái có thể không tạo ra API Call (ví dụ: thay đổi do hệ thống tự điều chỉnh hoặc khi import tài nguyên cũ). Trong các trường hợp này, EventBridge sẽ không phát hiện được, trong khi AWS Config sẽ định kỳ quét trạng thái thực tế để phát hiện các điểm mù.

- **Chứng minh tuân thủ liên tục:** AWS Config lưu trữ lịch sử cấu hình (Configuration Timeline), cho phép đội Auditability tạo các báo cáo chứng minh rằng **CloudTrail luôn ở trạng thái Enabled** trong suốt các khoảng thời gian như 30, 90 hoặc 365 ngày, phục vụ các đợt thanh tra và đánh giá tuân thủ.

---

### 2. Lộ trình triển khai (Proposed Roadmap)

Nhóm kiến nghị triển khai các **AWS Managed Rules** sau:

| AWS Config Rule | Mục đích |
|-----------------|----------|
| **cloud-trail-enabled** | Đảm bảo CloudTrail luôn được bật trên toàn bộ tài khoản (tầng kiểm tra trạng thái). |
| **cloud-trail-log-file-validation-enabled** | Đảm bảo chức năng xác thực tính toàn vẹn (Log File Validation) luôn được bật nhằm phát hiện các hành vi chỉnh sửa hoặc làm giả log. |
| **s3-bucket-logging-enabled** | Đảm bảo S3 Bucket lưu trữ CloudTrail Logs cũng được bật Access Logging để ghi nhận đầy đủ các hoạt động truy cập vào bucket chứa chứng cứ kiểm toán. |

---

### 3. Giá trị gia tăng cho dự án (Value Proposition)

Việc bổ sung AWS Config mang lại các giá trị sau:

- **Continuous Compliance:** Chuyển từ mô hình "kiểm tra log khi xảy ra sự cố" sang mô hình **liên tục giám sát và đảm bảo hệ thống luôn tuân thủ các chuẩn cấu hình bảo mật**.

- **Audit Trail of the Audit System:** Đây là lớp giám sát bổ sung dành cho chính hệ thống ghi log và kiểm toán. Nếu CloudTrail hoặc các thành phần liên quan bị cấu hình sai, AWS Config sẽ là cơ chế đầu tiên phát hiện và cảnh báo.

- **Chi phí tối ưu:** Với cơ chế đánh giá định kỳ và việc chỉ triển khai các Managed Rules thiết yếu, chi phí vận hành ước tính dưới **1 USD/tháng**, phù hợp với mục tiêu tối ưu ngân sách của dự án (khoảng **300 USD/tuần/Task Force**) trong khi vẫn nâng cao đáng kể năng lực tuân thủ và khả năng kiểm toán.


---

## Chữ ký xác nhận

**Owner**

**Đinh Văn Ty**  
**Group CDO-07 – Auditability**