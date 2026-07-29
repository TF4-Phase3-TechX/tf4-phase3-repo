# BÁO CÁO TIẾN ĐỘ THỰC HIỆN TASK: CENTRALIZE LOG & FORENSIC SECURITY ANALYTICS

| Thuộc tính | Giá trị |
|------------|----------|
| **Dự án** | Task Force 4 — Phase 3 |
| **Đội thực hiện** | Group CDO-07 (Auditability) |
| **Người phân tích** | Đinh Văn Ty |
| **Thành viên triển khai** | Nguyễn Duy Hoàng |
| **Ngày gửi báo cáo** | 29/07/2026 |

---

# 📌 I. TỔNG QUAN VÀ BỐI CẢNH (CONTEXT)

Trong tuần làm việc cuối cùng, theo yêu cầu của Mentor về việc tập trung toàn bộ log hạ tầng và ứng dụng (**Centralize Log**) nhằm phục vụ công tác giám sát, điều tra sự cố (**Security Forensics**) và đáp ứng yêu cầu tuân thủ (**Compliance**), nhóm đã thực hiện các nội dung sau:

1. Phân tích hiện trạng toàn bộ luồng log đang phân tán trên hệ thống, bao gồm:
   - EKS Control Plane Logs
   - AWS CloudTrail
   - Application Logs
   - AI Tool Call Logs

2. Thiết kế kiến trúc tập trung log với mục tiêu:
   - Tối ưu chi phí vận hành.
   - Đảm bảo tính **Immutable**.
   - Tuân thủ nguyên tắc **Content-Free**.
   - Áp dụng **Zero-Retention** đối với dữ liệu nhạy cảm.

3. Phân tích, bóc tách và phân công công việc (**Task Delegation**) cho từng thành viên nhằm đảm bảo tiến độ triển khai.

---

# 🏗️ II. CHUỖI BẰNG CHỨNG TRIỂN KHAI (EXECUTION EVIDENCE CHAIN)

Quá trình triển khai được thực hiện theo ba giai đoạn chính, mỗi giai đoạn đều có đầy đủ tài liệu, Git Commit hoặc Pull Request làm bằng chứng.

---

## 1. Phân tích hiện trạng & Thiết kế kiến trúc (20/07/2026)

| Nội dung | Thông tin |
|----------|-----------|
| **Thực hiện bởi** | Đinh Văn Ty |
| **Git Commit / Tài liệu** | https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/audit/tickets/AUDIT-016-solutions-centrailize-log.md |

### Kết quả đạt được

- Thống nhất kiến trúc tập trung toàn bộ log về **S3 Audit Lake** với **Object Lock (WORM)**.
- Sử dụng **CloudWatch Logs Subscription Filter** kết hợp **Amazon Kinesis Data Firehose** để vận chuyển log.
- Thiết kế cơ chế lọc log ngay tại nguồn (Filter Pattern cho EKS Audit Logs), giúp giảm khoảng **70–80%** dung lượng lưu trữ.
- Lựa chọn **AWS Athena** làm **Serverless Query Engine** phục vụ điều tra pháp y thay cho ELK, OpenSearch, Loki hoặc Datadog nhằm tối ưu chi phí.

---

## 2. Triển khai Athena Forensic Security Analytics & Tối ưu chi phí

| Nội dung | Thông tin |
|----------|-----------|
| **Thực hiện bởi** | Nguyễn Duy Hoàng |
| **Bằng chứng** | https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/evidence/mandate-04-forensic/B%C3%A1o%20c%C3%A1o%20tri%E1%BB%83n%20khai%20v%C3%A0%20chi%20ph%C3%AD%20Athena%20Forensic%20Security%20Analytics.md |

### Kết quả đạt được

- Xây dựng thành công **AWS Glue Data Catalog** và các bảng dữ liệu cho:
  - AWS CloudTrail
  - EKS Control Plane Logs
  - AI Tool Call Logs
- Tối ưu chi phí truy vấn Athena bằng:
  - Partition theo ngày, giờ và loại sự kiện.
  - Lưu trữ dữ liệu ở định dạng **Parquet/GZIP**.

---

## 3. Mở rộng Centralize Log cho AI Tool Call Logs

| Nội dung | Thông tin |
|----------|-----------|
| **Thực hiện bởi** | Nguyễn Duy Hoàng |
| **Pull Request** | https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/714 |

### Kết quả đạt được

- Tích hợp thành công nguồn **AI Tool Calls / LLM Traces** vào pipeline tập trung log.
- Kết nối Athena với các partition của AI Logs trên Amazon S3.
- Đảm bảo tuân thủ tiêu chuẩn:
  - **Content-Free Logging**
  - **W3C Trace Context**
- Chỉ lưu các metadata cần thiết như:
  - Trace ID
  - Token Cost
  - Latency
- Không lưu:
  - Raw Prompt
  - Raw Response
  - Dữ liệu PII

Theo đúng định hướng của **ADR-024**.

---

# 📊 III. BẢNG TỔNG HỢP KIẾN TRÚC LOG TẬP TRUNG (CENTRALIZED LOG ARCHITECTURE MATRIX)

| Nguồn Log | Luồng vận chuyển | Lưu trữ dài hạn | Công cụ truy vấn / Phân tích |
|------------|------------------|-----------------|------------------------------|
| **AWS CloudTrail** | CloudWatch Logs | S3 Audit Bucket (Object Lock) | AWS Athena / CloudWatch Logs Insights |
| **EKS Control Plane** | CloudWatch Logs → Kinesis Data Firehose | S3 Audit Bucket (Filtered `/healthz`) | AWS Athena / CloudWatch Logs Insights |
| **Application & Microservices** | OpenTelemetry / Fluent Bit → Firehose | S3 Audit Bucket | AWS Athena |
| **AI Tool Calls / LLM Spans** | OpenTelemetry (W3C Trace Context) → Firehose | S3 Audit Bucket (Content-Free) | AWS Athena / Jaeger (Trace ID) |

---

# 🎯 IV. KẾT LUẬN & TRẠNG THÁI NGHIỆM THU

## 1. Tiến độ triển khai

- ✅ Hoàn thành **100%** Task **Centralize Log** đúng kế hoạch trong tuần cuối của dự án.
- ✅ Hoàn thiện đầy đủ tài liệu thiết kế, tài liệu triển khai và bằng chứng Git/Pull Request.

---

## 2. Kết quả về tối ưu chi phí và bảo mật

Nhóm đã đạt được các mục tiêu sau:

- Giảm đáng kể chi phí lưu trữ bằng cơ chế lọc log ngay tại nguồn trước khi ghi xuống S3.
- Đảm bảo tính **Non-repudiation** và **Immutable Audit Trail** thông qua Object Lock.
- Xây dựng nền tảng điều tra pháp y tập trung, cho phép truy vấn nhanh bằng SQL trên AWS Athena.
- Mở rộng thành công khả năng thu thập log cho AI Tool Calls mà vẫn đáp ứng nguyên tắc **Content-Free Logging** và bảo vệ dữ liệu nhạy cảm.

---

## Kiến nghị

Kính trình **Mentor** xem xét báo cáo, đánh giá kết quả triển khai và cho ý kiến chỉ đạo hoặc nghiệm thu đối với Task **Centralize Log & Forensic Security Analytics**.

---

# XÁC NHẬN BỞI TEAM LEAD / AUDIT OWNER

**Đinh Văn Ty**  
**Group CDO-07 – Auditability**

