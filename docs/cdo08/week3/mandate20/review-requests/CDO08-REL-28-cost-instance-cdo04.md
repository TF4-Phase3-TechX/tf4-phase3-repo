# [REVIEW REQUEST] CDO04 - Cost Review cho CDO08-REL-XX

| Thông tin     | Giá trị                                                        |
| ------------- | -------------------------------------------------------------- |
| Từ            | CDO08                                                          |
| Đến           | CDO04 (Cost/Infra)                                             |
| Backlog       | `CDO08-REL-28` - MSK Broker Upgrade for Firehose Compatibility |
| Ngày gửi      | 2026-07-25                                                     |
| Deadline      | \_\_\_, trước khi implement Terraform broker upgrade           |
| Review result | \_\_\_                                                         |

---

# 1. Thay Đổi Đề Xuất

Trong `CDO08-REL-28`, Tech Lead đã chọn **Amazon Kinesis Data Firehose (MSK native source)** để thay thế AWS MSK Connect nhằm archive topic `orders` sang S3.

Để Firehose có thể đọc dữ liệu từ Amazon MSK, cluster cần bật:

- IAM Authentication (dual-auth cùng SCRAM hiện tại)
- Multi-VPC Private Connectivity
- Cluster Resource Policy cho Firehose

Trong quá trình Terraform apply, AWS trả về lỗi:

```text
BadRequestException:
Multi-VPC private connectivity is not supported on the broker instance type of the MSK cluster.
```

Sau khi đối chiếu tài liệu AWS, nguyên nhân được xác định là:

- Broker hiện tại sử dụng `kafka.t3.small`.
- AWS **không hỗ trợ Multi-VPC Private Connectivity trên broker type `kafka.t3.small`**.
- Theo tài liệu chính thức của Amazon MSK, **`kafka.m5.large` là broker instance nhỏ nhất hỗ trợ Multi-VPC Private Connectivity**.

Do đây là giới hạn của dịch vụ AWS, không có workaround bằng Terraform hay IAM policy.

Đề xuất:

- Giữ nguyên số broker.
- Giữ nguyên storage.
- Chỉ nâng broker instance:

```text
kafka.t3.small
        ↓
kafka.m5.large
```

Không thay đổi:

- Topic
- Partition
- Replication factor
- Application
- Authentication flow
- Networking ngoài phần Multi-VPC bắt buộc.

---

# 2. Cost Assumptions

| Assumption                                       |                                      Giá dùng để tính |
| ------------------------------------------------ | ----------------------------------------------------: |
| Region                                           |                                           `us-east-1` |
| Broker hiện tại                                  |                                  `2 x kafka.t3.small` |
| Broker đề xuất                                   |                                  `2 x kafka.m5.large` |
| Broker hours                                     |                                       `730 giờ/tháng` |
| Storage                                          |                                     `10 GiB / broker` |
| MSK Storage                                      |                                   `$0.10 / GiB-month` |
| Firehose ingest                                  |                                         `$0.055 / GB` |
| Multi-VPC private connectivity (fixed)           | `$0.0225 / connectivity-hour / authentication scheme` |
| Multi-VPC private connectivity (data processing) |                                         `$0.006 / GB` |
| Traffic orders (7 ngày gần nhất)                 |                  `97,352,246.52 bytes = 0.090666 GiB` |
| Estimate traffic tháng                           |                                     `~0.417 GB/tháng` |

---

## Chi phí hiện tại (2 x kafka.t3.small)

| Thành phần       |         Cost/tháng |
| ---------------- | -----------------: |
| Broker compute   |           `$66.58` |
| Storage (20 GiB) |            `$2.00` |
| **Tổng**         | **`$68.58/tháng`** |

---

## Chi phí sau khi nâng (2 x kafka.m5.large)

| Thành phần       |          Cost/tháng |
| ---------------- | ------------------: |
| Broker compute   |           `$306.60` |
| Storage (20 GiB) |             `$2.00` |
| **Tổng**         | **`$308.60/tháng`** |

---

## Chi phí Firehose + Multi-VPC

Theo traffic thực tế 7 ngày gần nhất:

| Thành phần                |         Cost/tháng |
| ------------------------- | -----------------: |
| Firehose ingest           |            `$0.02` |
| Multi-VPC fixed           |           `$16.43` |
| Multi-VPC data processing |            `$0.00` |
| **Tổng**                  | **`$16.45/tháng`** |

---

## Tổng Cost Sau Thay Đổi

| Thành phần           |          Cost/tháng |
| -------------------- | ------------------: |
| MSK broker + storage |           `$308.60` |
| Firehose + Multi-VPC |            `$16.45` |
| **Tổng**             | **`$325.05/tháng`** |

---

## Cost Increase

| So sánh                        |                 Cost |
| ------------------------------ | -------------------: |
| Chi phí hiện tại               |       `$68.58/tháng` |
| Sau khi nâng broker + Firehose |      `$325.05/tháng` |
| **Recurring increase**         | **`+$256.47/tháng`** |

Trong đó:

| Thành phần      |        Increase |
| --------------- | --------------: |
| Broker upgrade  | `$240.02/tháng` |
| Multi-VPC fixed |  `$16.43/tháng` |
| Firehose ingest |   `$0.02/tháng` |

---

# 3. Trade-off

| Phương án                    |          Chi phí | Nhận xét                                                                          |
| ---------------------------- | ---------------: | --------------------------------------------------------------------------------- |
| Giữ `kafka.t3.small`         |       Không tăng | Không thể bật Multi-VPC; Terraform bị AWS từ chối; Firehose không triển khai được |
| Upgrade lên `kafka.m5.large` | `~$325.05/tháng` | Đáp ứng đầy đủ yêu cầu Firehose; broker nhỏ nhất AWS hỗ trợ Multi-VPC             |
| Tạo cluster MSK mới          |          Cao hơn | Không cần thiết; tăng rủi ro migration và cutover                                 |

Quyết định:

> Upgrade broker instance là thay đổi bắt buộc để triển khai Firehose. Đây là yêu cầu kỹ thuật của dịch vụ AWS, không phải lựa chọn tối ưu hóa hiệu năng.

---

# 4. CDO04 Review Result

Decision: \_\_\_

Điều kiện bắt buộc trước implementation:

- [ ] Approve recurring cost increase khoảng `$256.47/tháng`.
- [ ] Xác nhận `kafka.m5.large` là broker instance nhỏ nhất đáp ứng yêu cầu Multi-VPC.
- [ ] Chấp nhận rolling broker update trong maintenance window.
- [ ] Xác nhận Firehose vẫn là phương án được lựa chọn thay AWS MSK Connect.

---

## CDO04 Approval Record

| Thông tin                | Giá trị                                                |
| ------------------------ | ------------------------------------------------------ |
| Decision                 | \_\_\_                                                 |
| Selected design          | Upgrade MSK Broker `kafka.t3.small` → `kafka.m5.large` |
| Current recurring cost   | `$68.58/tháng`                                         |
| Projected recurring cost | `$325.05/tháng`                                        |
| Recurring increase       | `$256.47/tháng`                                        |
| Ngày duyệt               | \_\_\_                                                 |
| Người duyệt              | \_\_\_                                                 |
| Comment/Evidence link    | \_\_\_                                                 |

---

# 5. Nguồn Tham Chiếu

- AWS Amazon MSK Pricing (Broker instance pricing, storage pricing, Multi-VPC Private Connectivity pricing, pricing examples)
  https://aws.amazon.com/msk/pricing/

- AWS Amazon MSK Developer Guide – Multi-VPC Private Connectivity
  (Xác nhận `kafka.t3.small` không hỗ trợ Multi-VPC Private Connectivity và mô tả tính năng)
  https://docs.aws.amazon.com/msk/latest/developerguide/aws-access-mult-vpc.html

- AWS Amazon Data Firehose Pricing
  (MSK as a Source ingestion pricing)
  https://aws.amazon.com/firehose/pricing/

- AWS Amazon Data Firehose Developer Guide – Using Amazon MSK as a Source
  (Kiến trúc Firehose đọc dữ liệu trực tiếp từ Amazon MSK)
  https://docs.aws.amazon.com/firehose/latest/dev/writing-with-msk.html
