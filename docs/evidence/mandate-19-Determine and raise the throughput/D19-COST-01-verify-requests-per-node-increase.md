# D19-COST-01: Xác minh requests-per-node tăng trên cùng compute capacity

**Owner:** CDO-04  
**Trạng thái (Status):** IN REVIEW 
**Dự án:** TF4 Phase 3 - TechX Corp  
**Dependency:** [D19-PERF-07-post-tuning-ramp-test.md](file:///d:/XBRAIN/tf4-phase3-repo/docs/evidence/mandate-19-Determine%20and%20raise%20the%20throughput/D19-PERF-07-post-tuning-ramp-test.md) (Chạy tải Post-Tuning)  
**Baseline reference:** [D19-PERF-04-baseline-report.md](file:///d:/XBRAIN/tf4-phase3-repo/docs/evidence/mandate-19-Determine%20and%20raise%20the%20throughput/D19-PERF-04-baseline-report.md)

---

## 1. Mục tiêu (Objective)

Chứng minh hiệu suất chi phí (cost efficiency) của cụm storefront tăng khi áp dụng tối ưu hóa phần mềm mà **không tăng thêm bất kỳ node worker hay nâng cấp tài nguyên compute nào**. 

Tài liệu này thiết lập kịch bản và công thức tính toán đối chiếu trước/sau, ghi nhận kết quả đối chứng thực tế từ phiên chạy **Post-Tuning (D19-PERF-07)** tại mức tải đỉnh **350 Users**.

---

## 2. Bảng Đối Chiếu So Sánh Trước và Sau Tối Ưu (Before/After Cost Matrix)

Bảng đối chiếu chi tiết hiệu suất chi phí trước và sau tối ưu phần mềm:

| Chỉ số (Metric) | Baseline (Before) <br>[Đo tại 75 Users] | Post-Tuning (After) <br>[Đo tại 350 Users] | Cải tiến (Improvement) | Kết quả Nghiệm thu |
| :--- | :---: | :---: | :---: | :---: |
| **Successful RPS** (Conservative Breakpoint) | `22.28` | `48.61` | **`+118.18%`** | Ghi nhận |
| **Requests/Node** (Successful RPS/Node) | `4.46` | `9.72` | **`+118.18%`** | **PASS** (Tăng 2.18 lần) |
| **RPS/vCPU** | `2.23` | `4.86` | **`+118.18%`** | **PASS** (Tăng 2.18 lần) |
| **RPS/GiB Memory** | `0.56` | `1.22` | **`+118.18%`** | Ghi nhận |
| **Node Count** | `5` | `5` | **0%** (Cố định) | **PASS** (Bằng nhau) |
| **Node-hours / 1M Requests** | `62.34` | `28.57` | **`-54.17%`** (Giảm hao phí) | **PASS** (Tiết kiệm 54.17%) |

> [!IMPORTANT]
> **Ràng buộc hạ tầng cố định:** 
> Node Count và Instance Type trước/sau bắt buộc phải bằng nhau để đảm bảo tính so sánh tương thích (Compute Parity). Mọi sự thay đổi về số lượng node trong suốt quá trình chạy test (nếu autoscaler kích hoạt scale-out) sẽ làm bài test vô hiệu.

---

## 3. Bằng chứng tính toán thô (Raw Calculation Evidence)

### 3.1. Các thông số hạ tầng vật lý cố định (Physical Hardware Capacity)
Bài test chạy trên hạ tầng worker node EKS cố định gồm 5 nodes:
* **Core Managed Node Group (`techx-general-ng`):** 2x `t3.large` instances.
* **Karpenter Autoscaler NodePool (`techx-general`):** 3x `t3a.large` instances (được scale lên từ trước và khóa tải trong suốt bài test để đảm bảo capacity không thay đổi).
* **Thông số tài nguyên vật lý:**
  * `total_worker_node_count = 5` nodes.
  * `total_worker_vcpu = 5 nodes * 2 vCPUs/node = 10` vCPUs.
  * `total_worker_memory_gib = 5 nodes * 8 GiB/node = 40` GiB memory.

### 3.2. Số liệu tính toán sẵn cho giai đoạn Trước tối ưu (Baseline - Before)
Số liệu trích xuất từ [D19-PERF-04-baseline-report.md](file:///d:/XBRAIN/tf4-phase3-repo/docs/evidence/mandate-19-Determine%20and%20raise%20the%20throughput/D19-PERF-04-baseline-report.md) tại bước tải cao nhất đạt SLO (75 Users):
* **Sustained Successful RPS:** `22.28`
* **Thời gian của bước chạy (Step Duration):** 5 phút (`300` giây).
* **Số lượng requests gửi vào (Offered Requests):** `6,426` requests.
* **Số lượng lỗi ghi nhận (Failed Requests):** `1` lỗi Browse.
* **Tổng số requests thành công thực tế (Successful Requests):** `6,426 - 1 = 6,425` requests.

#### Các phép tính thô cụ thể:
1. **Sustained RPS/Node:**
   $$\text{sustained\_rps\_per\_node\_before} = \frac{22.28 \text{ RPS}}{5 \text{ nodes}} = \mathbf{4.456} \text{ RPS/node}$$

2. **Requests/Node (tổng requests thành công trong step chia cho số node):**
   $$\text{successful\_requests\_per\_node\_before} = \frac{6,425 \text{ requests}}{5 \text{ nodes}} = \mathbf{1,285.0} \text{ requests/node}$$

3. **RPS/vCPU:**
   $$\text{successful\_rps\_per\_vcpu\_before} = \frac{22.28 \text{ RPS}}{10 \text{ vCPUs}} = \mathbf{2.228} \text{ RPS/vCPU}$$

4. **RPS/GiB Memory:**
   $$\text{successful\_rps\_per\_gib\_before} = \frac{22.28 \text{ RPS}}{40 \text{ GiB}} = \mathbf{0.557} \text{ RPS/GiB}$$

5. **Node-Hours per Million Requests (Tính theo công thức chuẩn hóa dựa trên Sustained RPS):**
   $$\text{node\_hours\_per\_million\_requests\_before} = \frac{\text{Worker Node Count} * 1,000,000}{3600 * \text{Sustained Successful RPS}} = \frac{5 * 1,000,000}{3600 * 22.28} = \mathbf{62.34}$$
   *(Hoặc tính trên số lượng request thực tế trong step: $\frac{5 \text{ nodes} * (300/3600) \text{ hours}}{6,425 / 1,000,000} \approx \mathbf{64.85}$ node-hours/1M requests)*

---

### 3.3. Số liệu tính toán thực tế cho giai đoạn Sau tối ưu (Post-Tuning - After)
Số liệu trích xuất từ [D19-PERF-07-post-tuning-ramp-test.md](file:///d:/XBRAIN/tf4-phase3-repo/docs/evidence/mandate-19-Determine%20and%20raise%20the%20throughput/D19-PERF-07-post-tuning-ramp-test.md) tại bước tải cao nhất đạt SLO (350 Users):
* **Sustained Successful RPS (After):** `48.61`
* **Thời gian của bước chạy (Step Duration):** `300` giây.
* **Số lượng requests gửi vào (Offered Requests):** `14,730` requests.
* **Tổng số requests thành công thực tế (Successful Requests):** `14,730 - 147 (1.00% lỗi) = 14,583` requests.

#### Các phép tính thô cụ thể:
1. **Sustained RPS/Node:**
   $$\text{sustained\_rps\_per\_node\_after} = \frac{48.61 \text{ RPS}}{5 \text{ nodes}} = \mathbf{9.722} \text{ RPS/node}$$
   *(So với Baseline `4.456`, tăng **+118.18%**)*

2. **Requests/Node (tổng requests thành công trong step chia cho số node):**
   $$\text{successful\_requests\_per\_node\_after} = \frac{14,583 \text{ requests}}{5 \text{ nodes}} = \mathbf{2,916.6} \text{ requests/node}$$
   *(So với Baseline `1,285.0`, tăng **+127.0%**)*

3. **RPS/vCPU:**
   $$\text{successful\_rps\_per\_vcpu\_after} = \frac{48.61 \text{ RPS}}{10 \text{ vCPUs}} = \mathbf{4.861} \text{ RPS/vCPU}$$
   *(So với Baseline `2.228`, tăng **+118.18%**)*

4. **RPS/GiB Memory:**
   $$\text{successful\_rps\_per\_gib\_after} = \frac{48.61 \text{ RPS}}{40 \text{ GiB}} = \mathbf{1.215} \text{ RPS/GiB}$$
   *(So với Baseline `0.557`, tăng **+118.13%**)*

5. **Node-Hours per Million Requests (Tính theo công thức chuẩn hóa dựa trên Sustained RPS):**
   $$\text{node\_hours\_per\_million\_requests\_after} = \frac{5 * 1,000,000}{3600 * 48.61} = \mathbf{28.57}$$
   *(So với Baseline `62.34`, giảm **-54.17%**)*

---

### 3.4. Công thức tính toán tỷ lệ cải tiến (Improvement Ratio Formulas)
* **Tỷ lệ tăng trưởng Throughput Density (RPS/Node, RPS/vCPU):**
   $$\text{Improvement \%} = \frac{\text{After} - \text{Before}}{\text{Before}} * 100\% = \frac{9.722 - 4.456}{4.456} * 100\% = \mathbf{118.18\%}$$

* **Tỷ lệ giảm hao phí hạ tầng EKS (Node-hours/1M Requests reduction):**
   $$\text{Reduction \%} = \frac{\text{Before} - \text{After}}{\text{Before}} * 100\% = \frac{62.34 - 28.57}{62.34} * 100\% = \mathbf{54.17\%}$$

---

## 4. Quy trình Xác minh Tiêu chí Nghiệm thu (Acceptance Criteria Guide)

Khi điền dữ liệu nghiệm thu cho `D19-COST-01`, operator đã xác minh đầy đủ các điều kiện sau:

* [x] **Node count trước và sau bằng nhau:** Xác nhận số lượng node trong suốt quá trình chạy test duy trì phẳng ở mức 5 nodes (ASG/Karpenter không scale-out).
* [x] **Instance type bằng nhau:** Xác nhận cấu hình instance types khớp hoàn toàn (`2x t3.large` + `3x t3a.large`).
* [x] **Requests/node tăng:** sustained_rps_per_node_after (`9.72`) > `4.46` (**+118.18%**).
* [x] **RPS/vCPU tăng:** successful_rps_per_vcpu_after (`4.86`) > `2.23` (**+118.18%**).
* [x] **Node-hours trên một triệu request giảm:** node_hours_per_million_requests_after (`28.57`) < `62.34` (**-54.17%**).
* [x] **Không đánh đổi correctness:** Tỷ lệ lỗi toàn cụm tại 350 Users chỉ ghi nhận 1.00% (dưới trần SLO 2.00%). Không phát sinh lỗi logic nghiệp vụ.
* [x] **Có raw calculation evidence:** Thực hiện điền đầy đủ các phép tính thô tại Section 3.

---

## 5. Kết luận (Verdict)

> [!IMPORTANT]
> **KẾT LUẬN NGHIỆM THU: COMPLETED / PASS**
> 
> Báo cáo so sánh cho thấy hiệu suất chi phí của hệ thống TechX Storefront đã tăng trưởng vượt bậc sau tối ưu hóa phần mềm:
> * Mật độ xử lý requests trên mỗi đơn vị phần cứng (RPS/Node, RPS/vCPU) **tăng 118.18%** (gấp 2.18 lần).
> * Hao phí hạ tầng EKS (Node-hours trên 1 triệu requests) **giảm 54.17%**, tiết kiệm hơn một nửa chi phí tính toán cho cùng một lượng request xử lý thành công.
> 
> Toàn bộ quá trình tối ưu hóa này được chứng minh không sử dụng bất kỳ nâng cấp phần cứng nào (giữ nguyên 5 Nodes và 10 vCPUs vật lý), đáp ứng đầy đủ các tiêu chí nghiệm thu của **D19-COST-01**.
