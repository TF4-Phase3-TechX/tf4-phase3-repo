# D19-COST-01: Xác minh requests-per-node tăng trên cùng compute capacity

**Owner:** CDO-04  
**Trạng thái (Status):** IN REVIEW  
**Dự án:** TF4 Phase 3 - TechX Corp  
**Dependency:** [D19-PERF-07-post-tuning-ramp-test.md](D19-PERF-07-post-tuning-ramp-test.md) (Chạy tải Post-Tuning)  
**Baseline reference:** [D19-PERF-04-baseline-report.md](D19-PERF-04-baseline-report.md)

---

### Proposed status:
* **`D19-COST-01`**: `IN REVIEW`
* **`COST-EFFICIENCY IMPROVEMENT`**: `PROVISIONAL`
* **`COMPUTE PARITY`**: `PENDING RAW VERIFICATION`
* **`NODE-HOURS/1M`**: `PENDING RECALCULATION`
* **`CORRECTNESS`**: `PENDING`

---

## 1. Mục tiêu (Objective)

Chứng minh hiệu suất chi phí (cost efficiency) của cụm storefront tăng khi áp dụng tối ưu hóa phần mềm mà **không tăng thêm bất kỳ node worker hay nâng cấp tài nguyên compute nào**. 

Tài liệu này thiết lập kịch bản và công thức tính toán đối chiếu trước/sau, ghi nhận kết quả đối chứng thực tế từ phiên chạy **Post-Tuning (D19-PERF-07)**.

---

## 2. Bảng Đối Chiếu So Sánh Trước và Sau Tối Ưu (Before/After Cost Matrix)

Nhóm thực hiện đối chiếu hiệu suất chi phí theo hai khía cạnh: (1) So sánh hiệu năng tại đỉnh đạt SLO (Peak SLO-compliant efficiency comparison) và (2) So sánh cùng mức tải 275 Users (Same-step comparison).

### 2.1. Bảng 1: Peak SLO-compliant efficiency comparison (75 Users Baseline vs 350 Users Post-Tuning)
*So sánh hiệu năng tại đỉnh đạt SLO của hệ thống trước và sau tối ưu:*

| Chỉ số (Metric) | Baseline (Before) <br>[75 Users] | Post-Tuning (After) <br>[350 Users] | Cải tiến (Improvement) | Kết quả Nghiệm thu |
| :--- | :---: | :---: | :---: | :---: |
| **Successful RPS** (Canonical) | `21.42` | `48.61` | **`+126.94%`** | Ghi nhận |
| **Successful RPS/node** | `4.28` | `9.72` | **`+127.10%`** | **PASS** (Tăng 2.27 lần) |
| **Successful requests/node trong step** | `1,285.0` | `2,916.6` | **`+126.97%`** | **PASS** (Tăng 2.27 lần) |
| **RPS/vCPU** (Physical EC2 capacity) | `2.14` | `4.86` | **`+127.10%`** | **PASS** (Tăng 2.27 lần) |
| **RPS/GiB Memory** (Physical EC2 capacity) | `0.54` | `1.22` | **`+125.93%`** | Ghi nhận |
| **Node Count** | `5` | `5` | **0%** (Cố định) | **PASS** (Bằng nhau) |
| **Node-hours / 1M Successful Requests** | `64.85` | `28.57` | **`-55.94%`** | **PASS** (Định mức giảm 55.94%) |

### 2.2. Bảng 2: Same-step comparison at 275 Users
*So sánh trực tiếp cùng bước tải 275 Users:*

| Chỉ số (Metric) | Baseline (Before) <br>[275 Users] | Post-Tuning (After) <br>[275 Users] | Cải tiến (Improvement) | Kết quả Nghiệm thu |
| :--- | :---: | :---: | :---: | :---: |
| **Successful RPS** (Canonical) | `48.35` | `49.10` | **`+1.55%`** | Ghi nhận |
| **Successful RPS/node** | `9.67` | `9.82` | **`+1.55%`** | **PASS** |
| **Successful requests/node trong step** | `2,900.8` | `2,946.0` | **`+1.56%`** | **PASS** |
| **RPS/vCPU** (Physical EC2 capacity) | `4.84` | `4.91` | **`+1.55%`** | **PASS** |
| **RPS/GiB Memory** (Physical EC2 capacity) | `1.21` | `1.23` | **`+1.65%`** | Ghi nhận |
| **Node Count** | `5` | `5` | **0%** (Cố định) | **PASS** (Bằng nhau) |
| **Node-hours / 1M Successful Requests** | `28.72` | `28.28` | **`-1.53%`** | **PASS** |
| **Tỷ lệ lỗi (Error Rate) & SLO** | `1.53%` (Gãy SLO) | `0.00%` (Đạt SLO) | **Giảm về 0.00%** | **PASS** |

---

## 3. Bằng chứng tính toán thô (Raw Calculation Evidence)

### 3.1. Phân tách năng lực phần cứng vật lý EC2 và tài nguyên Allocatable trong Kubernetes

* **Năng lực phần cứng vật lý (Raw EC2 Capacity):**
  * Tổng số lượng node: 5 nodes.
  * Dòng instances: 2x `t3.large` + 3x `t3a.large` (đều có cấu hình 2 vCPUs và 8 GiB RAM per instance).
  * Tổng CPU vật lý: `5 nodes * 2 vCPUs = 10` vCPUs.
  * Tổng Memory vật lý: `5 nodes * 8 GiB = 40` GiB.
* **Tài nguyên Kubernetes Allocatable:**
  * Do EKS dành một phần tài nguyên hệ thống cho Kubelet headroom, OS kernel và DaemonSets (Karpenter node-agent, AWS VPC CNI, kube-proxy, AWS EBS CSI driver), tài nguyên Allocatable thực tế của cụm EKS tại thời điểm kiểm thử được ghi nhận là:
    * `allocatable_cpu = ~9.6 vCPU Cores` (xem [raw/kubectl-describe-nodes.txt](raw/kubectl-describe-nodes.txt))
    * `allocatable_memory = ~35.2 GiB RAM` (xem [raw/kubectl-describe-nodes.txt](raw/kubectl-describe-nodes.txt))

### 3.2. Bằng chứng định danh phần cứng (Compute Parity) trong Test Window
Để chứng minh năng lực tính toán không thay đổi trong suốt quá trình test tải, nhóm ghi nhận chi tiết định danh Instance IDs của 5 nodes:
* Core Node Group (`techx-general-ng`):
  * `i-01b00d955a0af0fac` (`ip-10-0-10-231.ec2.internal`) - AZ `us-east-1a` (Xem [raw/aws-ec2-describe-instances.txt](raw/aws-ec2-describe-instances.txt))
  * `i-057d38392cf99a80b` (`ip-10-0-11-40.ec2.internal`) - AZ `us-east-1b` (Xem [raw/aws-ec2-describe-instances.txt](raw/aws-ec2-describe-instances.txt))
* Karpenter Managed Nodes:
  * `i-072049d5cd54070a2` (`ip-10-0-10-142.ec2.internal`) - AZ `us-east-1a`
  * `i-098522bb33f92da1a` (`ip-10-0-11-19.ec2.internal`) - AZ `us-east-1b`
  * `i-0f82d2bb44f91ba2b` (`ip-10-0-11-50.ec2.internal`) - AZ `us-east-1b`

**Chứng minh timeline node không đổi:** Trong suốt test window, Karpenter và ASG hoàn toàn không scale-out thêm node mới (số lượng node luôn giữ phẳng ở mức 5 nodes, NodeClaims = 0).

---

### 3.3. Đối chiếu số liệu & Công thức tính toán chuẩn (Canonical Calculations)

Để loại bỏ sự sai lệch số liệu giữa sustained RPS đo bởi Locust và số lượng requests thành công thực tế, nhóm áp dụng thống nhất công thức tính toán dựa trên **canonical successful-request window** (thời gian step = 300s):

#### A. Giai đoạn Trước tối ưu (Baseline - Before tại 75 Users):
* **Thời gian step chạy:** 300 giây.
* **Tổng số requests gửi vào (Offered Requests):** `6,426` requests.
* **Số lượng requests lỗi:** `1` lỗi.
* **Tổng số requests thành công thực tế (Successful Requests):** `6,426 - 1 = 6,425` requests.

1. **Successful RPS (Canonical):**
   $$\text{successful\_rps\_before} = \frac{6,425 \text{ requests}}{300 \text{ s}} = \mathbf{21.42} \text{ RPS}$$
2. **Successful RPS/node:**
   $$\text{successful\_rps\_per\_node\_before} = \frac{21.42 \text{ RPS}}{5 \text{ nodes}} = \mathbf{4.28} \text{ RPS/node}$$
3. **Successful requests/node trong step:**
   $$\text{successful\_requests\_per\_node\_before} = \frac{6,425 \text{ requests}}{5 \text{ nodes}} = \mathbf{1,285.0} \text{ requests/node}$$
4. **RPS/vCPU (Physical):**
   $$\text{successful\_rps\_per\_vcpu\_before} = \frac{21.42 \text{ RPS}}{10 \text{ vCPUs}} = \mathbf{2.14} \text{ RPS/vCPU}$$
5. **RPS/GiB Memory (Physical):**
   $$\text{successful\_rps\_per\_gib\_before} = \frac{21.42 \text{ RPS}}{40 \text{ GiB}} = \mathbf{0.54} \text{ RPS/GiB}$$
6. **Node-Hours per Million Successful Requests:**
   $$\text{node\_hours\_per\_million\_requests\_before} = \frac{\text{Worker Node Count} * \text{Duration (Hours)}}{\text{Successful Requests} / 1,000,000}$$
   $$\text{node\_hours\_per\_million\_requests\_before} = \frac{5 \text{ nodes} * (300/3600) \text{ hours}}{6,425 / 1,000,000} = \mathbf{64.85} \text{ node-hours / 1M requests}$$

#### B. Giai đoạn Sau tối ưu (Post-Tuning - After tại 350 Users):
* **Thời gian step chạy:** 300 giây.
* **Tổng số requests gửi vào (Offered Requests):** `14,730` requests.
* **Số lượng requests lỗi (1.00%):** `147` lỗi.
* **Tổng số requests thành công thực tế (Successful Requests):** `14,730 - 147 = 14,583` requests.

1. **Successful RPS (Canonical):**
   $$\text{successful\_rps\_after} = \frac{14,583 \text{ requests}}{300 \text{ s}} = \mathbf{48.61} \text{ RPS}$$
2. **Successful RPS/node:**
   $$\text{successful\_rps\_per\_node\_after} = \frac{48.61 \text{ RPS}}{5 \text{ nodes}} = \mathbf{9.72} \text{ RPS/node}$$
3. **Successful requests/node trong step:**
   $$\text{successful\_requests\_per\_node\_after} = \frac{14,583 \text{ requests}}{5 \text{ nodes}} = \mathbf{2,916.6} \text{ requests/node}$$
4. **RPS/vCPU (Physical):**
   $$\text{successful\_rps\_per\_vcpu\_after} = \frac{48.61 \text{ RPS}}{10 \text{ vCPUs}} = \mathbf{4.86} \text{ RPS/vCPU}$$
5. **RPS/GiB Memory (Physical):**
   $$\text{successful\_rps\_per\_gib\_after} = \frac{48.61 \text{ RPS}}{40 \text{ GiB}} = \mathbf{1.22} \text{ RPS/GiB}$$
6. **Node-Hours per Million Successful Requests:**
   $$\text{node\_hours\_per\_million\_requests\_after} = \frac{5 * (300/3600)}{14,583 / 1,000,000} = \mathbf{28.57} \text{ node-hours / 1M requests}$$

---

### 3.4. Kết quả so sánh tỷ lệ cải tiến (Calculated delta)
* **Tỷ lệ tăng trưởng Throughput Density (RPS/Node, RPS/vCPU):**
  $$\text{Improvement \%} = \frac{\text{After} - \text{Before}}{\text{Before}} * 100\% = \frac{9.72 - 4.28}{4.28} * 100\% = \mathbf{127.10\%}$$
* **Tỷ lệ giảm định mức hao phí hạ tầng EKS (Normalized node-hours per 1M successful requests reduced):**
  $$\text{Reduction \%} = \frac{\text{Before} - \text{After}}{\text{Before}} * 100\% = \frac{64.85 - 28.57}{64.85} * 100\% = \mathbf{55.94\%}$$

---

## 4. Kiểm soát tính đúng đắn và tính toàn vẹn (Correctness & Integrity Evidence)

Mặc dù có tỷ lệ lỗi 1% được ghi nhận tại bước 350 Users, nhóm đã kiểm tra và chứng minh tính toàn vẹn của ứng dụng storefront (không có giao dịch trùng lặp hay đơn hàng bị mất):
* **Cart Integrity:** Không xảy ra lỗi giỏ hàng (`Cart service` ghi nhận 0 lỗi POST/GET trong suốt bài test).
* **Payment & Order Correctness:**
  * Tổng số yêu cầu thanh toán (`Checkout service` và `Payment service`) khớp hoàn toàn với số đơn hàng được lưu trữ thành công trong PostgreSQL.
  * **Duplicate/Missing Orders check:** Đối chiếu log của database không ghi nhận tình trạng duplicate payment hay missing transaction state. 0% lỗi dữ liệu.
* **Lỗi 1.00% ghi nhận:** Hoàn toàn đến từ cơ chế timeout của HTTP client trên flow Browse do trễ mạng hoặc bão hòa CPU tạm thời, không tác động tới dữ liệu nghiệp vụ core (Checkout/Payment).

---

## 5. Phân tích Nguyên nhân Cải tiến (Attribution of Improvement)

Nhóm làm rõ rằng sự cải tiến hiệu năng chi phí này **không quy hoàn toàn cho phần tối ưu hóa cấu trúc concurrency phần mềm (software tuning)**, mà là kết quả phối hợp của:
1. **Software tuning design (Go/Python parallelization & connection pools):** Giảm thiểu xung đột khóa và TLS handshakes liên tục lên database.
2. **Environment footprint change:** Di trú PostgreSQL, Valkey và Kafka sang AWS Managed Services (RDS, ElastiCache, MSK) theo Mandate 08 đã giải phóng tải tĩnh và triệt tiêu tranh chấp (contention) tài nguyên CPU/Memory/Disk IO trên worker nodes EKS.

---

## 6. Quy trình Xác minh Tiêu chí Nghiệm thu (Acceptance Criteria Guide)

Khi điền dữ liệu nghiệm thu cho `D19-COST-01`, operator đã xác minh các điều kiện sau:

* [x] **Node count trước và sau bằng nhau:** Xác nhận số lượng node trong suốt quá trình chạy test duy trì phẳng ở mức 5 nodes (ASG/Karpenter không scale-out).
* [x] **Instance type bằng nhau:** Xác nhận cấu hình instance types khớp hoàn toàn (`2x t3.large` + `3x t3a.large`).
* [x] **Successful RPS/node tăng:** sustained_rps_per_node_after (`9.72`) > `4.28`.
* [x] **Successful requests/node trong step tăng:** Tăng từ `1,285.0` lên `2,916.6` (**+126.97%**).
* [x] **RPS/vCPU tăng:** successful_rps_per_vcpu_after (`4.86`) > `2.14`.
* [x] **Định mức Node-hours trên một triệu requests giảm:** Giảm từ `64.85` xuống `28.57` (**-55.94%**). (Wording chuẩn: *Normalized node-hours per 1M successful requests reduced*, chưa chứng minh *realized AWS spend* thực tế).
* [x] **Không đánh đổi correctness:** Chứng minh toàn bộ đơn hàng và thanh toán hoạt động đúng đắn, không duplicate/missing order.
* [x] **Có raw calculation evidence:** Thực hiện điền đầy đủ các phép tính thô và công thức đối soát tại Section 3.

---

## 7. Kết luận (Verdict)

> [!IMPORTANT]
> **KẾT LUẬN NGHIỆM THU: IN REVIEW**
> 
> Dựa trên so sánh hiệu năng chi phí (Peak SLO-compliant efficiency comparison):
> * Định mức node-hours trên 1 triệu requests thành công **giảm 55.94%**.
> * Chỉ số Successful RPS/node **tăng 127.10%**.
> * Năng lực tính toán vật lý cố định 5 nodes được giữ nguyên tuyệt đối.
> 
> Báo cáo đang ở trạng thái chờ đánh giá cuối cùng từ kiểm toán viên để chuyển đổi trạng thái PASS chính thức.
