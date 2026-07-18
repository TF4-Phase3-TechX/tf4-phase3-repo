# [REVIEW REQUEST] CDO04 — Cost Review cho CDO08-MANDATE-08

| Thông tin | Giá trị |
|---|---|
| Từ | CDO08 |
| Đến | CDO04 (Cost) |
| Backlog | `CDO08-MANDATE-08` — Managed Services Migration |
| Ngày gửi | 2026-07-18 |
| Deadline | Trước khi tiến hành di trú thực tế trên Production |
| Review result | **PENDING** |

---

## 1. Thay đổi đề xuất

MANDATE-08 yêu cầu chuyển đổi 3 dịch vụ dữ liệu tự vận hành trên EKS (PostgreSQL, Valkey, Kafka Kraft) sang các dịch vụ quản trị (Managed Services) của AWS để bảo đảm tính ổn định, bảo mật và khả năng phục hồi thảm họa.

CDO08 đề xuất cấu hình di trú cụ thể như sau:
1. **PostgreSQL:** Chuyển sang **Amazon RDS PostgreSQL** (Multi-AZ, `db.t4g.micro`, 20 GiB gp3).
2. **Valkey:** Chuyển sang **Amazon ElastiCache for Valkey** (2-node Multi-AZ, `cache.t4g.micro`).
3. **Kafka:** Chuyển sang **Amazon MSK Provisioned** (2-node Multi-AZ, `kafka.t3.small`, 10 GiB EBS/node).
4. **Hạ tầng di trú trung gian:** Sử dụng **AWS DMS** (`dms.t3.medium`) chạy trong tối đa 24 giờ (1 ngày) để di trú PostgreSQL và tự dọn dẹp sau đó. Chạy **MirrorMaker 2** trên cụm EKS hiện tại (Incremental cost = `$0`) để di trú Kafka.

---

## 2. Cost assumptions

CDO08 tính toán chi phí bằng bảng giá public của AWS tại khu vực `us-east-1` (2026):

| Thành phần hạ tầng | Đơn giá AWS Public | Ghi chú |
| :--- | :---: | :--- |
| **RDS Postgres Instance `db.t4g.micro` (Multi-AZ)** | `$0.0320/giờ` | Chạy 24x7 (gồm 1 Primary và 1 Standby sync) |
| **RDS gp3 Storage (Multi-AZ)** | `$0.2300/GiB-tháng` | Cấu hình 20 GiB (giá gấp đôi Single-AZ `$0.115/GiB-tháng`) |
| **ElastiCache Valkey `cache.t4g.micro`** | `$0.0128/giờ/node` | Chạy 24x7, cần 2 nodes cho Multi-AZ (Rẻ hơn 20% so với Redis OSS) |
| **MSK Broker `kafka.t3.small`** | `$0.0456/giờ/node` | Chạy 24x7, cần 2 brokers cho cấu hình Multi-AZ |
| **MSK gp3 Storage** | `$0.0800/GiB-tháng` | Cấu hình 10 GiB cho mỗi broker (Tổng cộng 20 GiB) |
| **DMS Replication Instance `dms.t3.medium`** | `$0.0500/giờ` | Chỉ bật On-Demand trong 24 giờ để di trú PostgreSQL |
| **MirrorMaker 2 on EKS** | `$0.00/giờ` | Deploy pod trên cụm EKS hiện có (Sử dụng compute/NAT nhàn rỗi) |

### Công thức tính toán chi phí hàng tuần (Weekly cost formulas):
```text
Weekly Cost = (Hourly Rate × 168 giờ) + (Storage Size × Storage Rate × 12 tháng / 52 tuần)
```

### Chi tiết tính toán chi phí định kỳ hàng tuần (Weekly Fixed Cost):

#### 1. Amazon RDS PostgreSQL
* **Compute:** `168 giờ × $0.0320 = $5.376 / tuần`
* **Storage (20 GiB gp3 Multi-AZ):** `20 GiB × $0.2300 × 12 / 52 = $1.062 / tuần`
* **Tổng cộng RDS:** `$5.376 + $1.062 = $6.438 / tuần` *(~$28.00 / tháng)*

#### 2. Amazon ElastiCache for Valkey
* **Compute (2 nodes `cache.t4g.micro`):** `2 nodes × 168 giờ × $0.0128 = $4.301 / tuần`
* **Storage:** Valkey chạy hoàn toàn trên RAM $\rightarrow$ `$0.00 / tuần`
* **Tổng cộng Valkey:** **`$4.301 / tuần`** *(~$18.69 / tháng)*

#### 3. Amazon MSK (Kafka)
* **Compute (2 brokers `kafka.t3.small`):** `2 brokers × 168 giờ × $0.0456 = $15.322 / tuần`
* **Storage (2 brokers × 10 GiB gp3 = 20 GiB):** `20 GiB × $0.0800 × 12 / 52 = $0.369 / tuần`
* **Storage Auto-Scaling (Tính năng co giãn ổ đĩa tự động):** 
  - Kích hoạt tính năng Auto-Scaling cho đĩa EBS của MSK là **miễn phí hoàn toàn** (AWS không tính phí cấu hình/vận hành tính năng này).
  - Chi phí thực tế chỉ tăng tuyến tính theo **dung lượng đĩa tăng thêm thực tế** khi cụm tự động scale-up (đơn giá cố định `$0.08 / GiB-tháng`).
  - *Ví dụ cụ thể:* Nếu cụm tự động scale-up thêm 10 GiB cho mỗi broker (Tổng cộng tăng thêm 20 GiB):
    - Chi phí tăng thêm hàng tháng: `20 GiB × $0.0800 = $1.60 / tháng`
    - Chi phí tăng thêm hàng tuần: `20 GiB × $0.0800 × 12 / 52 = $0.369 / tuần`
* **Tổng cộng MSK:** `$15.322 + $0.369 = $15.691 / tuần` *(~$68.18 / tháng)*

#### 4. Tổng chi phí định kỳ chạy cụm Multi-AZ (Postgres + Valkey + Kafka)
* **Weekly Total:** `$6.438 + $4.301 + $15.691 = $26.430 / tuần` *(~$114.87 / tháng)*

### Chi tiết chi phí một lần & Phân bổ tài nguyên di trú (One-Time Migration Cost & Resource Allocation):
* **AWS DMS Instance (`dms.t3.medium`):** `24 giờ (1 ngày) × $0.0500 = $1.20` (Chi phí dịch vụ AWS trực tiếp).
* **AWS Network Load Balancer (NLB - Tạm thời):** `24 giờ (1 ngày) × $0.0225 = $0.54` (Dùng làm cầu nối đồng bộ Valkey, xóa ngay sau cutover).
* **Chi phí truyền dữ liệu qua mạng (Data Transfer Cost - Ước tính):**
  - Đồng bộ EKS PostgreSQL (10GB) $\rightarrow$ RDS: `10 GB × $0.01 / GB (cross-AZ) = $0.10`
  - Đồng bộ EKS Valkey (5GB) $\rightarrow$ ElastiCache: `5 GB × $0.01 / GB (cross-AZ) = $0.05`
  - Đồng bộ EKS Kafka (10GB) $\rightarrow$ MSK: `10 GB × $0.01 / GB (cross-AZ) = $0.10`
  - *Tổng chi phí truyền dữ liệu di trú một lần:* **`~$0.25`** (Rất nhỏ, được bù đắp bởi budget cap).
* **Tài nguyên chạy MirrorMaker 2 (Kafka Migration) trên EKS:**
  - MirrorMaker 2 sẽ được chạy dưới dạng một Kubernetes Deployment tạm thời trên cụm EKS hiện có để kéo dữ liệu từ EKS Kafka đẩy sang MSK.
  - **Tài nguyên tiêu thụ ước tính (Workload resource):**
    - `0.25 vCPU` (requests) / `0.5 vCPU` (limits)
    - `512 MiB` RAM (requests) / `1 GiB` RAM (limits)
    - *Đánh giá ảnh hưởng cụm:* Việc này sử dụng năng lực tính toán dư thừa sẵn có của các EKS Worker Nodes hiện tại, **không phát sinh chi phí trực tiếp trên hóa đơn AWS (Incremental cost = $0)**. 
    - *Đặc biệt:* Sau khi di trú hoàn tất, việc xóa Pod `kafka` self-hosted cũ trên EKS (đang chiếm **1.0 vCPU và 1 GiB RAM**) sẽ giải phóng tài nguyên. Do đó, sau di trú, cụm EKS sẽ **tiết kiệm ròng (net-gain) +0.75 vCPU và +512 MiB RAM**, giúp cụm EKS nhẹ tải hơn.
* **Tổng chi phí di trú (Một lần):** **`$1.74`** (chưa bao gồm thuế và ~$0.25 phí truyền dữ liệu).

---

## 3. CHỨNG MINH ĐÁP ỨNG WORKLOAD (WORKLOAD CAPACITY JUSTIFICATION)

Để đảm bảo các cấu hình giá rẻ đề xuất ở trên đáp ứng đầy đủ tài nguyên cho workload hiện tại, dưới đây là bảng đối chiếu tài nguyên (vCPU, RAM, Storage) giữa **Hiện trạng EKS self-hosted** và **Hạ tầng RDS/ElastiCache/MSK đích**:

| Dịch vụ | Tài nguyên hiện tại trên EKS | Tài nguyên đề xuất trên AWS Managed | Phân tích Khả năng đáp ứng Workload (Workload Capacity) |
| :--- | :--- | :--- | :--- |
| **PostgreSQL** | • **Pods:** 1 Pod `postgresql`<br>• **CPU Limit:** 0.5 vCPU<br>• **Memory Limit:** 512 MiB<br>• **Storage:** 10 GiB gp2 | • **Instance:** 2 Nodes `db.t4g.micro` Multi-AZ<br>• **Compute:** 2 vCPUs (burstable), 1 GiB RAM per node<br>• **Storage:** 20 GiB gp3 (Multi-AZ synchronous) | **Dư thừa lớn (Đáp ứng tốt):**<br>- RAM lớn gấp **2 lần** RAM limit hiện tại của pod.<br>- CPU 2 vCPUs khỏe hơn nhiều so với 0.5 vCPU share trên EKS.<br>- Ổ gp3 cung cấp tối thiểu 3,000 IOPS và 125 MB/s throughput, khắc phục hoàn toàn hiện tượng nghẽn IOPS ổ gp2 cũ của EKS khi chạy validation. |
| **Valkey** | • **Pods:** 1 Pod `valkey-cart`<br>• **CPU Limit:** 0.25 vCPU<br>• **Memory Limit:** 64 MiB<br>• **Storage:** 5 GiB gp2 | • **Instance:** 2 Nodes `cache.t4g.micro` Multi-AZ<br>• **Compute:** 2 vCPUs (burstable), 0.5 GiB (512 MiB) RAM per node<br>• **Storage:** N/A (RAM-based) | **Dư thừa lớn (Đáp ứng tốt):**<br>- Bộ nhớ RAM 512 MiB lớn gấp **8 lần** RAM limit của pod trên EKS (64 MiB). Do giỏ hàng có TTL 60 phút nên lượng active keys thực tế chỉ chiếm ~20-50 MiB RAM.<br>- Valkey xử lý đơn luồng (single-thread), 1 core của Graviton2 dư sức đáp ứng >10,000 requests/giây cho service giỏ hàng. |
| **Kafka** | • **Pods:** 1 Pod `kafka` (broker + controller)<br>• **CPU Limit:** 1.0 vCPU<br>• **Memory Limit:** 1 GiB RAM<br>• **Storage:** 10 GiB gp2 | • **Instance:** 2 Brokers `kafka.t3.small` Multi-AZ<br>• **Compute:** 2 vCPUs, 2 GiB RAM per broker<br>• **Storage:** 10 GiB gp3/broker (Tự động scale up) | **Dư thừa lớn (Đáp ứng tốt):**<br>- Cụm MSK cung cấp tổng cộng **4 vCPUs và 4 GiB RAM** chia tải trên 2 brokers, gấp **4 lần** RAM và **4 lần** CPU của single pod cũ.<br>- Network throughput của `t3.small` đạt mức baseline 0.75 Gbps, trong khi băng thông stream `orders` thực tế của storefront luôn dưới 100 KB/s (khoảng vài events/giây). |
| **AWS DMS** | • **Compute:** N/A | • **Instance:** 1 Node `dms.t3.medium`<br>• **Compute:** 2 vCPUs, 4 GiB RAM | **Đầy đủ (Đáp ứng tốt):**<br>- DMS chỉ chạy tạm thời tối đa 24 giờ (1 ngày) trong lúc di trú.<br>- RAM 4 GiB đủ lớn để đệm (buffer) toàn bộ transaction logs/CDC in-memory cho DB 10GB mà không cần ghi đệm xuống đĩa, giúp tăng tốc độ validate dữ liệu giữa EKS và RDS. |

---

## 4. PHÂN TÍCH TRADE-OFFS CHI TIẾT THEO TỪNG DỊCH VỤ (PER-SERVICE COST TRADEOFFS)

Dưới đây là bảng phân tích trade-offs chi tiết cho từng dịch vụ để trình CDO04 phê duyệt:

### A. Dịch vụ PostgreSQL (Database Layer)
| Phương án | Chi phí ước tính | Trade-offs (Đánh đổi Ưu/Nhược điểm) | Đánh giá & Khuyến nghị |
| :--- | :---: | :--- | :--- |
| **RDS Multi-AZ `db.t4g.micro` (gp3 20GB)** | **`$6.44 / tuần`**<br>*(~$28.00 / tháng)* | **Ưu điểm:** Đồng bộ 100% dữ liệu sang node standby. Tự động failover khi lỗi AZ (RTO < 60s, RPO = 0).<br>**Nhược điểm:** Chi phí gấp đôi so với Single-AZ. | **ĐỀ XUẤT CHỌN:** Bắt buộc để bảo vệ dữ liệu giao dịch đơn hàng cốt lõi. |
| **RDS Single-AZ `db.t4g.micro` (gp3 20GB)** | **`$3.22 / tuần`**<br>*(~$14.15 / tháng)* | **Ưu điểm:** Tiết kiệm 50% chi phí.<br>**Nhược điểm:** Không có node dự phòng. Khi sập AZ, dữ liệu có thể bị mất và RTO khôi phục từ snapshot mất nhiều giờ. | **LOẠI BỎ:** Rủi ro mất dữ liệu tài chính không đáng để tiết kiệm $3.22/tuần. |

### B. Dịch vụ Valkey (Caching Layer)
| Phương án | Chi phí ước tính | Trade-offs (Đánh đổi Ưu/Nhược điểm) | Đánh giá & Khuyến nghị |
| :--- | :---: | :--- | :--- |
| **ElastiCache Multi-AZ `cache.t4g.micro`** | **`$4.30 / tuần`**<br>*(~$18.69 / tháng)* | **Ưu điểm:** Có node replica dự phòng, tự động failover, đảm bảo tính sẵn sàng của storefront.<br>**Nhược điểm:** Tốn thêm chi phí cho node thứ hai. | **ĐỀ XUẤT CHỌN:** Giỏ hàng nằm trên critical path, sập Valkey là sập checkout storefront. |
| **ElastiCache Single-Node `cache.t4g.micro`** | **`$2.15 / tuần`**<br>*(~$9.34 / tháng)* | **Ưu điểm:** Tiết kiệm một nửa chi phí.<br>**Nhược điểm:** Không có failover. Khi node lỗi, toàn bộ giỏ hàng và luồng checkout bị tê liệt. | **LOẠI BỎ:** Tiết kiệm $2.15/tuần không đáng để đánh đổi tính ổn định của storefront. |

### C. Dịch vụ Kafka (Message Broker Layer)
| Phương án | Chi phí ước tính | Trade-offs (Đánh đổi Ưu/Nhược điểm) | Đánh giá & Khuyến nghị |
| :--- | :---: | :--- | :--- |
| **MSK Provisioned `kafka.t3.small` (Multi-AZ)** | **`$15.69 / tuần`**<br>*(~$68.18 / tháng)* | **Ưu điểm:** Được AWS quản trị hoàn toàn, Multi-AZ HA, chi phí rẻ và nằm trong tầm kiểm soát. Hỗ trợ tự động scale đĩa EBS.<br>**Nhược điểm:** Không hỗ trợ công cụ AWS MSK Replicator (MSK Replicator yêu cầu m5.large trở lên), bắt buộc phải chạy MirrorMaker 2 trên EKS để di trú. | **ĐỀ XUẤT CHỌN:** Chi phí tối ưu nhất để đạt chuẩn managed service của Mandate 8. |
| **MSK Serverless (Multi-AZ)** | **`$126.75 / tuần`**<br>*(~$550.00 / tháng)* | **Ưu điểm:** Tự động co giãn hoàn toàn cả compute và storage.<br>**Nhược điểm:** Base cost quá đắt ($0.75/giờ cluster charge + phí partition/data), gây lãng phí lớn đối với tải thấp của dự án. | **LOẠI BỎ:** Chi phí vượt trần ngân sách cho phép của nhóm. |
| **Waiver (Giữ EKS Kafka Kraft cũ)** | **`$0 / tuần`** | **Ưu điểm:** Không phát sinh thêm chi phí trên hóa đơn AWS.<br>**Nhược điểm:** Vi phạm mục tiêu Mandate 8. Tự vận hành cụm đơn lẻ không có tính sẵn sàng cao, rủi ro sập do đầy đĩa PVC. | **LOẠI BỎ:** Đi ngược lại định hướng di trú của dự án. |

---

## 5. CDO04 review result

**Decision: `PENDING`**

CDO04 phê duyệt phương án ngân sách di trú dữ liệu của CDO08 với các điều kiện ràng buộc:

- [ ] Chọn phương án MSK Provisioned với instance `kafka.t3.small` thay vì MSK Serverless để tối ưu chi phí.
- [ ] Chọn phương án RDS Postgres `db.t4g.micro` Multi-AZ để bảo toàn dữ liệu tài chính.
- [ ] Bật tính năng Storage Auto-Scaling cho MSK để tự động co giãn đĩa từ 10GB lên tối đa 100GB khi đạt 80% dung lượng.
- [ ] Tắt máy chủ AWS DMS (`dms.t3.medium`) và xóa Replication Slot ngay sau khi cutover thành công để tránh phát sinh chi phí phát sinh.
- [ ] Deploy MirrorMaker 2 trên EKS để tận dụng tài nguyên compute có sẵn, không tạo mới AWS MSK Replicator.
- [ ] Đảm bảo tổng chi phí định kỳ thực tế sau triển khai của TF vẫn nằm trong giới hạn `<= $300 / tuần`.

---

## 6. Nguồn tham chiếu

- [Amazon RDS PostgreSQL Pricing](https://aws.amazon.com/rds/postgresql/pricing/)
- [Amazon ElastiCache for Valkey Pricing](https://aws.amazon.com/elasticache/pricing/)
- [Amazon MSK Pricing](https://aws.amazon.com/msk/pricing/)
- [AWS Database Migration Service Pricing](https://aws.amazon.com/dms/pricing/)

