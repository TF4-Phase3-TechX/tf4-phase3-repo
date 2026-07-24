# BÁO CÁO PHÂN TÍCH & ĐỀ XUẤT GIẢI PHÁP TRUY VẤN AUDIT LOG TỰ ĐỘNG

| Thuộc tính | Giá trị |
|------------|----------|
| **Người thực hiện (Owner)** | Đinh Văn Ty (Group CDO-07 / Auditability) |
| **Dự án** | Task Force 4 — Enterprise Cloud Security & Compliance |
| **Vấn đề cần giải quyết** | Tối ưu hóa quy trình phân tích Audit Logs (CloudTrail, VPC Flow Logs, Application Logs), thay thế phương pháp đọc log thủ công qua S3 Console hoặc CloudWatch Logs Insights vốn tốn thời gian và yêu cầu tải dữ liệu về máy cá nhân. |

---

# 1. HIỆN TRẠNG VÀ THÁCH THỨC (CURRENT PAIN POINTS)

Hiện tại, toàn bộ dữ liệu kiểm toán (**Audit Trail**) được lưu trữ trên:

- Amazon S3 (Object Lock – Compliance Mode)
- Amazon CloudWatch Logs

Mặc dù kiến trúc này đáp ứng yêu cầu về lưu trữ bất biến, quy trình khai thác dữ liệu phục vụ điều tra vẫn còn nhiều hạn chế.

## Hạn chế 1 – Quy trình thủ công và tốn thời gian

Khi cần điều tra sự cố (Incident Response) hoặc thực hiện kiểm toán định kỳ, vận hành viên phải:

1. Truy cập S3 Bucket.
2. Tải từng file `.json.gz`.
3. Giải nén trên máy cá nhân.
4. Dùng các công cụ như `grep`, `jq` hoặc script để phân tích.

Quy trình này mất nhiều thời gian và khó mở rộng khi số lượng log ngày càng lớn.

---

## Hạn chế 2 – Giới hạn của CloudWatch Logs Insights

CloudWatch Logs Insights phù hợp cho truy vấn ngắn hạn nhưng không tối ưu cho lưu trữ log dài hạn.

Các chi phí phát sinh bao gồm:

- **Storage:** khoảng **0.03 USD/GB/tháng**
- **Query:** khoảng **0.005 USD/GB dữ liệu được quét**

Đối với hệ thống Enterprise, đây là khoản chi phí đáng kể.

---

## Hạn chế 3 – Rủi ro an toàn thông tin

Việc tải dữ liệu Audit Logs về máy cá nhân làm tăng đáng kể:

- Attack Surface
- Rủi ro rò rỉ dữ liệu
- Vi phạm nguyên tắc kiểm toán và quản trị chứng cứ số

---

# 2. BẢNG SO SÁNH MA TRẬN GIẢI PHÁP (SOLUTION MATRIX)

Nhóm tiến hành đánh giá bốn giải pháp theo các tiêu chí:

- Khả năng tận dụng S3 hiện có
- Chi phí vận hành
- Độ phức tạp triển khai
- Hiệu năng truy vấn
- Mức độ bảo mật và tuân thủ

| Tiêu chí | **1. AWS Athena** | **2. ELK Stack** | **3. Grafana Loki** | **4. Datadog (SaaS)** |
|----------|-------------------|------------------|---------------------|-----------------------|
| **Tận dụng S3 hiện có** | 🟢 Đọc trực tiếp file `.json.gz` trên S3 | 🟡 Phải ship log sang Elasticsearch | 🟢 Sử dụng S3 làm Object Storage | 🔴 Phải gửi log sang nền tảng SaaS |
| **Chi phí phát sinh** | 🟢 Rất thấp (5 USD/TB dữ liệu quét, không cần hạ tầng) | 🔴 Cao (EC2/EKS + EBS + Elasticsearch) | 🟡 Thấp – Trung bình | 🔴 Rất cao (tính theo lượng log ingest và người dùng) |
| **Độ phức tạp triển khai** | 🟢 Rất thấp (Glue Data Catalog) | 🔴 Cao (Logstash, Elasticsearch, Kibana) | 🟡 Trung bình | 🟢 Rất thấp |
| **Độ trễ truy vấn** | 🟡 Vài giây đến vài chục giây | 🟢 Gần thời gian thực | 🟢 Nhanh | 🟢 Gần thời gian thực |
| **Bảo mật & Tuân thủ** | 🟢 Dữ liệu không rời khỏi S3, quản lý bằng IAM/Lake Formation | 🟡 Phải tự quản trị bảo mật Elasticsearch | 🟢 Dữ liệu vẫn nằm trên S3 | 🔴 Audit Logs bị chuyển ra ngoài AWS của dự án |

---

# 3. PHÂN TÍCH CHI TIẾT CÁC GIẢI PHÁP

## 🔹 Giải pháp 1 – AWS Athena (Serverless SQL Query on S3)

### Cơ chế

Sử dụng **AWS Glue Data Catalog** để định nghĩa schema cho CloudTrail Logs và VPC Flow Logs, sau đó truy vấn trực tiếp dữ liệu trên S3 bằng SQL mà không cần di chuyển hoặc giải nén log.

### Ưu điểm

- Không cần quản trị hạ tầng (Zero Infrastructure).
- Đọc trực tiếp các file `.json.gz` trên S3.
- Chỉ tính phí theo lượng dữ liệu thực tế được quét.
- Nếu partition dữ liệu theo `year/month/day`, chi phí truy vấn gần như bằng **0 USD**.

### Nhược điểm

- Người dùng cần biết SQL.
- Muốn có Dashboard trực quan cần kết hợp thêm QuickSight hoặc Grafana.

---

## 🔹 Giải pháp 2 – ELK Stack (Elasticsearch/OpenSearch + Logstash + Kibana)

### Cơ chế

Logstash hoặc Lambda đọc log từ S3, parse dữ liệu và tạo Index trong Elasticsearch để Kibana truy vấn.

### Ưu điểm

- Tìm kiếm Full-text rất nhanh.
- Dashboard trực quan và mạnh.

### Nhược điểm

- Phát sinh Double Storage Cost (S3 + Elasticsearch).
- Chi phí duy trì Cluster cao.
- Phải quản trị Elasticsearch 24/7.

---

## 🔹 Giải pháp 3 – Grafana Loki

### Cơ chế

Loki chỉ Index Labels, còn toàn bộ nội dung log được lưu dưới dạng Chunks trên S3.

### Ưu điểm

- Tận dụng S3 làm Object Storage.
- Chi phí lưu trữ thấp hơn ELK.
- Tích hợp tốt với Grafana hiện có.

### Nhược điểm

- Cần triển khai và vận hành Loki Query Engine trên EC2 hoặc EKS.

---

## 🔹 Giải pháp 4 – Datadog (SaaS)

### Cơ chế

Forward trực tiếp log từ CloudWatch hoặc S3 lên nền tảng SaaS.

### Ưu điểm

- Không cần quản trị hạ tầng.
- Giao diện trực quan.
- Triển khai nhanh.

### Nhược điểm

- Chi phí ingest log rất cao.
- Audit Logs rời khỏi hạ tầng AWS của dự án.
- Có thể phát sinh rủi ro về Compliance và Data Residency.

---

# 4. ĐỀ XUẤT CỦA NHÓM AUDITABILITY (RECOMMENDATION)

Dựa trên các tiêu chí:

- Zero-Cost Idle
- Tận dụng tối đa hạ tầng S3 hiện có
- Đảm bảo bảo mật và tuân thủ

Nhóm **CDO-07**, do **Đinh Văn Ty** làm Owner, đề xuất triển khai theo mô hình **Hybrid** gồm hai giai đoạn.

## Kiến trúc đề xuất

```text
                              ┌───────────────────────────────────────────────┐
                              │ Giai đoạn 1                                   │
                              │ AWS Athena                                    │
                              │ Truy vấn trực tiếp bằng SQL trên S3           │
                              └───────────────────────────────────────────────┘
                                            ▲
                                            │
[CloudTrail Logs] ─────► [Amazon S3 Bucket] ─┤
                                            │
                                            ▼
                              ┌───────────────────────────────────────────────┐
                              │ Giai đoạn 2                                   │
                              │ Grafana + Athena Datasource Plugin            │
                              │ Dashboard trực quan sử dụng Athena Engine     │
                              └───────────────────────────────────────────────┘
```

---

## 🎯 Giai đoạn 1 – Triển khai ngay (Terraform + Athena + Glue)

### Mục tiêu

Khắc phục ngay quy trình truy vấn log thủ công mà không phát sinh chi phí duy trì hạ tầng.

### Phương án

Triển khai bằng Terraform:

- AWS Glue Database
- AWS Glue Table
- Partition theo ngày/tháng/năm
- Schema chuẩn cho:
  - CloudTrail Logs
  - VPC Flow Logs

### Kết quả

Khi cần kiểm toán hoặc điều tra sự cố, vận hành viên chỉ cần:

1. Mở Athena Console.
2. Thực hiện truy vấn SQL.
3. Nhận kết quả trong khoảng **2–5 giây**.

Ví dụ:

- Ai đã gọi `StopLogging`?
- Ai đã gọi `GetSecretValue` trong 24 giờ qua?
- Có IAM User nào tạo Access Key mới?

Toàn bộ quá trình diễn ra mà **không cần tải bất kỳ file log nào về máy cá nhân**.

---

## 🎯 Giai đoạn 2 – Nâng cao trải nghiệm (Tùy chọn)

### Grafana Athena Datasource

Kết nối Grafana hiện có với AWS Athena thông qua **Grafana Athena Datasource Plugin**.

### Lợi ích

- Dashboard trực quan.
- Vẫn sử dụng Athena làm Query Engine.
- Không cần nhân bản dữ liệu sang Elasticsearch.
- Tiếp tục khai thác trực tiếp dữ liệu trên S3.

---

# 5. KẾT LUẬN

Nhóm Auditability đánh giá **AWS Athena** là giải pháp phù hợp nhất trong giai đoạn hiện tại nhờ khả năng:

- Truy vấn trực tiếp dữ liệu trên S3.
- Không phát sinh chi phí duy trì hạ tầng.
- Không cần nhân bản dữ liệu.
- Đảm bảo dữ liệu kiểm toán không rời khỏi môi trường AWS.
- Dễ triển khai bằng Terraform và mở rộng tích hợp với Grafana trong tương lai.

Mô hình **Athena + Glue** kết hợp **Grafana Athena Datasource** ở giai đoạn sau giúp cân bằng giữa hiệu năng, chi phí, khả năng mở rộng và yêu cầu tuân thủ của dự án Enterprise Cloud Security & Compliance.