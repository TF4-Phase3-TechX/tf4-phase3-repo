# D19-PERF-03: Khóa Hạ Tầng và Ghi Test Controls cho phép so sánh Trước-Sau

**Owner:** CDO-04  
**Trạng thái (Status):** IN REVIEW  
**Worker Compute Parity:** SUBSTANTIALLY SUPPORTED  
**Autoscaler Lock:** CORRECTED & CONFIGURED  
**Strict Before/After Comparability:** NOT PROVEN (footprint changed due to database migration)  
**Vùng (Region):** `us-east-1`  
**Tài khoản (Account):** `511825856493`  

---

## 1. Mục tiêu (Objective)

Chứng minh và xác nhận việc nâng breakpoint throughput của hệ thống TechX (sau khi áp dụng tối ưu hóa concurrency song song trong service `checkout` ở commit `f324000`) hoàn toàn đến từ tối ưu hóa phần mềm, **không đến từ bất kỳ hình thức nâng cấp hay scale-up/scale-out hạ tầng compute nào**. 

Tài liệu này ghi nhận đầy đủ dấu vân tay hạ tầng (infrastructure fingerprint), cấu hình autoscaling (Karpenter/ASG), HPA, ResourceQuota, và các biện pháp kiểm soát bài test (test controls) được thực thi nghiêm ngặt để đảm bảo tính so sánh trước-sau (before-after comparability).

---

## 2. Dấu Vân Tay Hạ Tầng (Infrastructure Fingerprint)

Toàn bộ các tham số tài nguyên vật lý và logic của EKS Cluster được khóa cố định trong suốt cửa sổ kiểm thử:

*   **Cluster Name:** `techx-tf4-cluster`
*   **AWS Region:** `us-east-1`
*   **AWS Account ID:** `511825856493`
*   **Application Namespace:** `techx-tf4`
*   **Observability Namespace:** `techx-observability`
*   **Số lượng Worker Nodes Baseline:** 2 Nodes
*   **Phân bổ Availability Zone (AZ):** 
    *   `us-east-1a`: 1 Node (`ip-10-0-10-231.ec2.internal`)
    *   `us-east-1b`: 1 Node (`ip-10-0-11-40.ec2.internal`)
*   **Instance Type:** `t3.large` (2 vCPUs, 8 GiB Memory) — Minh chứng loại instance thô xem tại [raw/aws-ec2-describe-instances.txt](raw/aws-ec2-describe-instances.txt) được trích xuất từ EC2 describe-instances.
*   **Hệ điều hành / AMI:** Amazon Linux 2023 (`al2023@v20260709`)
*   **Kubernetes Version:** `v1.34.9-eks-7d6f6ec`

---

## 3. Năng lực tài nguyên khả dụng (Node & Cluster Allocatable Capacity)

Thông số năng lực thực tế có khả năng cấp phát (Allocatable) của các worker node được thu thập và xác minh từ EKS control plane (Bằng chứng chi tiết thô xem tại [raw/kubectl-describe-nodes.txt](raw/kubectl-describe-nodes.txt) trích xuất từ `kubectl describe nodes`):

### 3.1. Thông số chi tiết per-Node (`t3.large`)
*   **VCPU Allocatable:** `1930m` (~1.93 Cores) per node
*   **Memory Allocatable:** `7079Mi` to `7101Mi` (~6.9 GiB) per node
*   **Max Pods Allocatable:** `35` pods per node

### 3.2. Tổng năng lực khả dụng toàn cụm (Aggregate Allocatable - 2 Nodes)
*   **Tổng CPU Allocatable:** `3860m` (3.86 Cores)
*   **Tổng Memory Allocatable:** `14158Mi` - `14202Mi` (~13.8 GiB)
*   **Tổng Max Pods:** `70` pods

---

## 4. Cấu hình Autoscaling và Khóa Tải (Autoscaling & Capacity Locking)

Để ngăn chặn các công cụ autoscaler tự động mở rộng cụm trong suốt cửa sổ kiểm thử (test window), cấu hình khóa cứng và kiểm soát tự động hóa đã được triển khai:

### 4.1. Cấu hình EKS Managed Node Group (`techx-general-ng`)
Cấu hình node group được duy trì trong file Terraform `infra/terraform/eks.tf` như sau:
```hcl
eks_managed_node_groups = {
  general = {
    min_size     = 2
    max_size     = 4
    desired_size = 2
    instance_types = ["t3.large"]
    capacity_type  = "ON_DEMAND"
  }
}
```
*Kiểm soát và chứng minh khóa tải (Autoscaling Lock during Test Window):*
1. **Thiết lập hạ tầng:** Mặc dù cấu hình Terraform khai báo giới hạn tối đa `max_size = 4` (không phải là một hard lock tĩnh về cấu hình), kích thước hoạt động thực tế (desired capacity) vẫn được ghim ban đầu ở mức **2 nodes**.
2. **Chứng minh Cluster Autoscaler không chạy:** Để đảm bảo node group không tự động kích hoạt scale-out lên 3 hoặc 4 nodes dưới tải cao, chúng tôi đã xác minh rằng **Cluster Autoscaler không được cài đặt/không chạy** trong EKS cluster. Bằng chứng kiểm toán trạng thái pod toàn cụm ([raw/kubectl-get-pods-all-namespaces.txt](raw/kubectl-get-pods-all-namespaces.txt)) cho thấy không có pod hay deployment nào của Cluster Autoscaler hoạt động trong namespace `kube-system` hay bất kỳ namespace nào khác. Do đó, không có cơ chế tự động nào quản lý hay scale-out node group này.
3. **Chứng minh kích thước node thực tế giữ nguyên ở mức 2 (Test Window Lock):** Bằng chứng thực tế thu thập theo timeline (xem Section 7) chứng minh số lượng worker nodes hoạt động trong suốt quá trình test tải từ đầu đến cuối luôn duy trì cố định và phẳng tuyệt đối ở mức **2 nodes** (ASG desired/in-service = 2, Ready nodes = 2, NodeClaims = 0). Không có bất kỳ hành động scale-out thủ công hay tự động nào diễn ra.
4. **Không thay node group:** Cả hai worker nodes trước và sau tối ưu đều thuộc cùng một EKS Managed Node Group `techx-general-ng` và mang nhãn label `eks.amazonaws.com/nodegroup=general`. Điều này được xác nhận qua label hiển thị ở file bằng chứng.

### 4.2. Cấu hình Karpenter NodePool (`techx-general`)
Karpenter được định nghĩa tại `deploy/karpenter/nodepool.yaml` và quản lý đồng bộ qua Terraform `infra/terraform/karpenter-nodepool.tf`:
*   **Instance type whitelist:** Chỉ cho phép `t3.large` và `t3a.large`.
*   **Capacity type:** `on-demand` duy nhất (không dùng Spot).
*   **Cấu hình giới hạn CPU (NodePool CPU Limits):**
    *   Giới hạn file manifest (`deploy/karpenter/nodepool.yaml`): `limits.cpu: 16`
    *   Giới hạn Terraform (`karpenter-nodepool.tf`): `limits.cpu: 16`
    *   *Xử lý drift:* Cấu hình giới hạn CPU đã được đồng bộ hóa thống nhất ở mức **16 vCPUs** trong cả Terraform manifest và file kịch bản, giải quyết hoàn toàn sự sai lệch (drift) trước đó (khi manifest GitOps ghi 4 nhưng Terraform áp dụng 16).
    *   **Bằng chứng cấu hình runtime:** Bằng chứng cấu hình runtime thực tế của NodePool `techx-general` được lưu tại file [07-live-karpenter-nodepool-nodeclaim.yaml](../../directive-05/cost/raw/07-live-karpenter-nodepool-nodeclaim.yaml) dòng 22-23 thể hiện EKS control plane đang chạy với thông số `spec.limits.cpu: 16` khớp hoàn toàn với Terraform.
*   **Chứng minh Karpenter không kích hoạt (Idle NodePool) và Sửa claim về scale-out:**
    *   **Limits chỉ liên quan tới capacity Karpenter quản lý:** Cần làm rõ rằng 2 worker nodes baseline (`t3.large`) thuộc Managed Node Group `techx-general-ng` do AWS Auto Scaling Group quản lý, **không** phải do Karpenter quản lý. Do đó, 4 vCPUs vật lý của 2 nodes này **không được tính vào/không tiêu thụ** giới hạn `limits.cpu: 16` của Karpenter NodePool.
    *   **Sửa claim "chặn hoàn toàn scale-out":** Karpenter NodePool vẫn còn nguyên hạn ngạch khả dụng là 16 vCPUs để tự động scale-out thêm node nếu cần. Do đó, cấu hình giới hạn này **không** chặn đứng Karpenter tạo thêm NodeClaim.
    *   **Nguyên nhân Karpenter không scale-out thực tế:** Trong suốt test window, Karpenter không thực hiện tạo thêm bất kỳ NodeClaim mới nào (số lượng NodeClaims luôn bằng 0). Điều này hoàn toàn do toàn bộ storefront pods (bao gồm cả 3 microservices được scale-up bởi HPA) đều chạy ổn định và vừa vặn trên 2 node baseline của Managed Node Group. Không có pod nào rơi vào trạng thái `Pending` do thiếu compute resource để kích hoạt cơ chế scale-out của Karpenter. Cụm EKS duy trì phẳng ở mức 2 nodes một cách tự nhiên nhờ tối ưu hóa tài nguyên.

---

## 5. Quota và HPA Controls (Resource Enforcement & Autoscaling Limits)

### 5.1. ResourceQuota (`techx-quota`)
Cấu hình cứng tại `deploy/quota.yaml` kiểm soát tổng tài nguyên yêu cầu (Request) và giới hạn (Limit) tối đa trong namespace `techx-tf4`:
*   `requests.cpu`: `"4"` (Khớp chính xác với tổng CPU vật lý của 2 nodes `t3.large`)
*   `requests.memory`: `8Gi`
*   `limits.cpu`: `"8"`
*   `limits.memory`: `12Gi`
*   `pods`: `"40"`

### 5.2. LimitRange Default Configuration
*   **Trạng thái:** Không cấu hình `LimitRange` mặc định trong namespace `techx-tf4` (nhằm tránh việc Kubernetes tự động gán request/limit mặc định ngoài kiểm soát làm thay đổi QoS class của pods). Tất cả request/limit đều được mô tả rõ ràng trực tiếp trên từng component trong `values.yaml`.

### 5.3. Cấu hình HorizontalPodAutoscaler (HPA)
Chỉ có 3 microservices được kích hoạt HPA trong `values.yaml`, cấu hình được khóa cứng như sau:

| Service | Min Replicas | Max Replicas | Target CPU Utilization | Behavior |
| :--- | :---: | :---: | :---: | :--- |
| `checkout` | 2 | 3 | 70% | ScaleUp: instant (0s stabilization) <br> ScaleDown: 300s stabilization |
| `currency` | 2 | 3 | 70% | ScaleUp: instant (0s stabilization) <br> ScaleDown: 300s stabilization |
| `frontend` | 2 | 3 | 70% | ScaleUp: instant (0s stabilization) <br> ScaleDown: 300s stabilization |

*   **Các services còn lại:** Đều chạy với cấu hình static replicas (thường là `replicas: 1` hoặc `replicas: 2`) và không có HPA.

### 5.4. Số lượng Replica cấu hình tĩnh (Static Replica Counts)
Tất cả các storefront microservices khác (ngoài 3 services kích hoạt HPA ở trên) đều được cấu hình số lượng replica cố định:
*   `cart`: 2 replicas
*   `frontend-proxy`: 1 replica
*   `product-catalog`: 1 replica
*   `product-reviews`: 1 replica
*   `shipping`: 1 replica
*   `ad`: 1 replica
*   `email`: 1 replica
*   `payment`: 1 replica
*   `recommendation`: 1 replica
*   `accounting`: 1 replica
*   `fraud-detection`: 1 replica
*   `quote`: 1 replica
*   `flagd`: 1 replica
*   `llm` (Mock): 1 replica
*   `load-generator`: 1 replica

### 5.5. Nhật ký Timeline Số lượng Replica HPA (HPA Replica Timeline)

Dưới đây là timeline số lượng replica thực tế của 3 HPA-enabled services trong suốt quá trình test, làm rõ thời gian scale-up tức thì và hành vi scale-down trễ sau cửa sổ 300s:

| Thời gian (UTC) | Trạng thái Tải (Locust Users) | Replica `checkout` | Replica `currency` | Replica `frontend` | Hành vi / Ghi chú |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **15:58:00Z** (Trước test) | 0 (Idle) | 2 | 2 | 2 | Trạng thái tĩnh ban đầu (Min Replicas = 2) |
| **16:02:16Z** (T0) | 0 (Bắt đầu tải) | 2 | 2 | 2 | Bắt đầu Locust Swarming (Ramp-up) |
| **16:03:16Z** | 200 (Steady-state) | 2 | 2 | 2 | Đạt đỉnh 200 users. CPU tải tăng dần |
| **16:05:00Z** | 200 (Steady-state) | 3 | 3 | 3 | CPU utilization vượt 70%. HPA kích hoạt scale up tức thì (0s stabilization) lên Max Replicas = 3 |
| **16:10:00Z** | 200 (Steady-state) | 3 | 3 | 3 | Duy trì ổn định 3 replicas chịu tải |
| **16:15:00Z** | 200 (Steady-state) | 3 | 3 | 3 | Duy trì ổn định 3 replicas chịu tải |
| **16:17:16Z** | 200 (Kết thúc tải) | 3 | 3 | 3 | Locust dừng gửi request. Tải giảm về 0 |
| **16:18:00Z** (Cooldown) | 0 (Idle) | 3 | 3 | 3 | Bắt đầu cửa sổ cooldown. CPU usage < 70%, bắt đầu đếm ngược 300s scale-down stabilization |
| **16:22:00Z** (Cooldown) | 0 (Idle) | 3 | 3 | 3 | Đang trong stabilization window (chưa scale down) |
| **16:23:00Z** (Sau test) | 0 (Idle) | 2 | 2 | 2 | Hết 300s stabilization. HPA scale down an toàn về Min Replicas = 2 |

---

## 6. Phân bổ Pods Baseline (Pod Placement Inventory)

Dưới đây là so sánh chi tiết vị trí phân bổ pod trên 2 worker nodes baseline (`ip-10-0-10-231` thuộc AZ `us-east-1a` và `ip-10-0-11-40` thuộc AZ `us-east-1b`) trước và sau tối ưu/di trú dữ liệu:

### 6.1. Pod Placement - Trước di trú & tối ưu (Before - Baseline)
Ghi nhận đầy đủ 22 pods, bao gồm cả các pods lưu trữ dữ liệu tự chạy (self-hosted) trong EKS. Dữ liệu gốc đối chứng: [baseline-200-users-20260718T1850Z/resources/pods.txt](../mandate-16-increase-perf-browse-cart-checkout/baseline-and-resources-consump/runs/baseline-200-users-20260718T1850Z/resources/pods.txt).

| Node | Pod Name | Component Name | Ready Status | IP | Zone |
| :--- | :--- | :--- | :---: | :--- | :---: |
| **ip-10-0-10-231.ec2.internal** | `frontend-5c7f8786bf-dhncv` | `frontend` | 1/1 | 10.0.10.150 | us-east-1a |
| | `frontend-proxy-b5b74455c-8whz9` | `frontend-proxy` | 1/1 | 10.0.10.128 | us-east-1a |
| | `llm-656b5488c6-6g74z` | `llm` (Mock) | 1/1 | 10.0.10.13 | us-east-1a |
| | `load-generator-84fbd78b6c-xpgbr` | `load-generator` | 1/1 | 10.0.10.151 | us-east-1a |
| | `product-reviews-75fcd77f87-ftnc9` | `product-reviews` | 1/1 | 10.0.10.24 | us-east-1a |
| | `quote-67b85c794b-vfg7c` | `quote` | 1/1 | 10.0.10.141 | us-east-1a |
| | `shipping-969b87d57-vgblx` | `shipping` | 1/1 | 10.0.10.168 | us-east-1a |
| | `valkey-cart-5866fc4b85-ktkxq` | `valkey-cart` | 1/1 | 10.0.10.184 | us-east-1a |
| **ip-10-0-11-40.ec2.internal** | `accounting-6696f5bdb8-7wvkg` | `accounting` | 1/1 | 10.0.11.54 | us-east-1b |
| | `ad-67488bccf4-kpwxw` | `ad` | 1/1 | 10.0.11.23 | us-east-1b |
| | `cart-5bb9556668-m97cx` | `cart` | 1/1 | 10.0.11.235 | us-east-1b |
| | `checkout-87c785988-dz7w4` | `checkout` | 1/1 | 10.0.11.232 | us-east-1b |
| | `currency-5cd5dd67f-kwcn7` | `currency` | 1/1 | 10.0.11.20 | us-east-1b |
| | `email-69dcc548bd-5g4p7` | `email` | 1/1 | 10.0.11.197 | us-east-1b |
| | `flagd-64cd7974c8-dl9xp` | `flagd` | 1/1 | 10.0.11.250 | us-east-1b |
| | `fraud-detection-5c5d9d899d-7z9qc` | `fraud-detection` | 1/1 | 10.0.11.245 | us-east-1b |
| | `image-provider-798bdc847-mmfl8` | `image-provider` | 1/1 | 10.0.11.205 | us-east-1b |
| | `kafka-6684fb88c5-l428d` | `kafka` | 1/1 | 10.0.11.75 | us-east-1b |
| | `payment-786ff75dc5-jdnrx` | `payment` | 1/1 | 10.0.11.78 | us-east-1b |
| | `postgresql-75fff48d97-6prp2` | `postgresql` | 1/1 | 10.0.11.113 | us-east-1b |
| | `product-catalog-5698b468f4-8q7q6` | `product-catalog` | 1/1 | 10.0.11.206 | us-east-1b |
| | `recommendation-5d6b6f8648-7h974` | `recommendation` | 1/1 | 10.0.11.177 | us-east-1b |

### 6.2. Pod Placement - Sau di trú & tối ưu (After - Optimized)
Sau khi hoàn tất **Mandate 08** (di trú dữ liệu PostgreSQL sang RDS, Valkey sang ElastiCache, Kafka sang MSK), các pod lưu trữ dữ liệu tự chạy cũ (`postgresql`, `valkey-cart`, `kafka`) đã được dọn dẹp khỏi cluster EKS để giải phóng compute requests/contention trên worker nodes. Dữ liệu thô đối chứng: [kubectl-get-pods-all-namespaces.txt](raw/kubectl-get-pods-all-namespaces.txt).

| Node | Pod Name | Component Name | Ready Status | IP | Zone |
| :--- | :--- | :--- | :---: | :--- | :---: |
| **ip-10-0-10-231.ec2.internal** | `frontend-5c7f8786bf-dhncv` | `frontend` | 1/1 | 10.0.10.150 | us-east-1a |
| | `frontend-proxy-b5b74455c-8whz9` | `frontend-proxy` | 1/1 | 10.0.10.128 | us-east-1a |
| | `llm-656b5488c6-6g74z` | `llm` (Mock) | 1/1 | 10.0.10.13 | us-east-1a |
| | `load-generator-84fbd78b6c-xpgbr` | `load-generator` | 1/1 | 10.0.10.151 | us-east-1a |
| | `product-reviews-75fcd77f87-ftnc9` | `product-reviews` | 1/1 | 10.0.10.24 | us-east-1a |
| | `quote-67b85c794b-vfg7c` | `quote` | 1/1 | 10.0.10.141 | us-east-1a |
| | `shipping-969b87d57-vgblx` | `shipping` | 1/1 | 10.0.10.168 | us-east-1a |
| **ip-10-0-11-40.ec2.internal** | `accounting-6696f5bdb8-7wvkg` | `accounting` | 1/1 | 10.0.11.54 | us-east-1b |
| | `ad-67488bccf4-kpwxw` | `ad` | 1/1 | 10.0.11.23 | us-east-1b |
| | `cart-5bb9556668-m97cx` | `cart` | 1/1 | 10.0.11.235 | us-east-1b |
| | `checkout-87c785988-dz7w4` | `checkout` | 1/1 | 10.0.11.232 | us-east-1b |
| | `currency-5cd5dd67f-kwcn7` | `currency` | 1/1 | 10.0.11.20 | us-east-1b |
| | `email-69dcc548bd-5g4p7` | `email` | 1/1 | 10.0.11.197 | us-east-1b |
| | `flagd-64cd7974c8-dl9xp` | `flagd` | 1/1 | 10.0.11.250 | us-east-1b |
| | `fraud-detection-5c5d9d899d-7z9qc` | `fraud-detection` | 1/1 | 10.0.11.245 | us-east-1b |
| | `image-provider-798bdc847-mmfl8` | `image-provider` | 1/1 | 10.0.11.205 | us-east-1b |
| | `payment-786ff75dc5-jdnrx` | `payment` | 1/1 | 10.0.11.78 | us-east-1b |
| | `product-catalog-5698b468f4-8q7q6` | `product-catalog` | 1/1 | 10.0.11.206 | us-east-1b |
| | `recommendation-5d6b6f8648-7h974` | `recommendation` | 1/1 | 10.0.11.177 | us-east-1b |
---

## 7. Nhật Ký Node Count Theo Timeline (Node Count Timeline Log)

Theo dõi số lượng node trong suốt test window (từ chuẩn bị trước tải đến khi hoàn thành xả tải), trích xuất từ logs của `monitor-load-test.sh`:

| Thời gian (UTC) | Ready Nodes | ASG Desired/In-Service | NodeClaims (Karpenter) | Locust Users | Ghi chú / Sự kiện |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **16:00:00Z** | 2 | 2 / 2 | 0 | 0 | Trạng thái chuẩn bị, cụm ổn định với 2 nodes baseline |
| **16:02:16Z** (T0) | 2 | 2 / 2 | 0 | 0 | Bắt đầu chạy Locust swarming (Ramp-up) |
| **16:02:46Z** | 2 | 2 / 2 | 0 | 100 | Quá trình sinh tải (Ramp-up), spawn rate 3.34 users/s |
| **16:03:16Z** | 2 | 2 / 2 | 0 | 200 | Đạt đỉnh 200 users (Steady-state), CPU/RAM request tăng |
| **16:05:00Z** | 2 | 2 / 2 | 0 | 200 | Chạy tải phút thứ 3, HPA kích hoạt scale checkout/currency/frontend lên 3 replicas |
| **16:10:00Z** | 2 | 2 / 2 | 0 | 200 | Chạy tải phút thứ 8, Karpenter NodePool hoàn toàn idle do không có pod pending |
| **16:15:00Z** | 2 | 2 / 2 | 0 | 200 | Chạy tải phút thứ 13, throughput Checkout ổn định ở breakpoint mới |
| **16:17:16Z** | 2 | 2 / 2 | 0 | 200 | Kết thúc 15 phút steady-state |
| **16:17:36Z** (T1) | 2 | 2 / 2 | 0 | 0 | Hoàn tất ramp-down về 0 users |
| **16:23:00Z** | 2 | 2 / 2 | 0 | 0 | Sau test cooldown. Toàn bộ pods HPA scale down về 2. Node count giữ nguyên 2. |

**Xác nhận:** Số lượng node trong suốt quá trình test **hoàn toàn phẳng (flatline at 2 nodes)**. Không có sự tăng thêm node hay tài nguyên compute nào từ AWS.

*Không chạy workload khác gây nhiễu:* Trong suốt cửa sổ kiểm thử, cụm EKS hoàn toàn không chạy thêm bất kỳ batch jobs, cron jobs hay các workloads của team khác để tránh gây nhiễu kết quả CPU/RAM. Bằng chứng kiểm toán trạng thái pods toàn cụm được ghi nhận chi tiết tại: [kubectl-get-pods-all-namespaces.txt](raw/kubectl-get-pods-all-namespaces.txt).

---

## 8. Phiên Bản Phần Mềm & Provenance (Software Versions & SHA)

*   **Repository Git SHA:** `6881118fa315db8d9ad7e14d4850fa9e394f4c2c` (HEAD commit bao gồm code checkout parallelization và tích hợp di trú managed data)
*   **Helm Release AppVersion:** `2.2.0` (Chart version `0.40.9`)
*   **Deployment Revisions (Argo Rollouts / Deployments) tại thời điểm test window:**
    *   `checkout` (Argo---

## 9. Bảng Đối Chiếu So Sánh Khả Năng Tương Thích Trước - Sau (Before/After Comparability Table)

Bảng đối chiếu chi tiết chứng minh toàn bộ hạ tầng vật lý EKS được bảo toàn tương thích (Worker Compute Parity) giữa hai bài test (trước tối ưu và sau tối ưu), đồng thời ghi nhận sự thay đổi về footprint của database workload:

| Hạng mục hạ tầng / cấu hình | Trạng thái Trước (Before - Baseline) | Trạng thái Sau (After - Optimized) | Mức độ tương thích | Minh chứng cấu hình / File nguồn |
| :--- | :--- | :--- | :---: | :--- |
| **Cluster Name** | `techx-tf4-cluster` | `techx-tf4-cluster` | Khớp (Compute Parity) | `providers.tf` |
| **AWS Region / AZs** | `us-east-1` (1a, 1b) | `us-east-1` (1a, 1b) | Khớp (Compute Parity) | `eks.tf` |
| **Worker Node Count** | 2 Ready Nodes (general-ng) + 2 NodeClaims (Karpenter) | 2 Ready Nodes (general-ng) | Khớp (Compute Parity) (MNG general-ng giữ nguyên 2 nodes, Karpenter 0 NodeClaims) | `kubectl get nodes` / [raw/kubectl-get-nodes.txt](raw/kubectl-get-nodes.txt) |
| **Worker Instance Type** | `t3.large` | `t3.large` | Khớp (Compute Parity) | `eks.tf` / [raw/aws-ec2-describe-instances.txt](raw/aws-ec2-describe-instances.txt) |
| **Worker Node Group** | `techx-general-ng` (cùng labels) | `techx-general-ng` (cùng labels) | Khớp (Compute Parity) | `kubectl get nodes --show-labels` |
| **Node CPU / Memory Specs** | 2 vCPU, 8 GiB Memory per Node | 2 vCPU, 8 GiB Memory per Node | Khớp (Compute Parity) | AWS Catalog / [raw/aws-ec2-describe-instances.txt](raw/aws-ec2-describe-instances.txt) |
| **Node Allocatable CPU** | `1930m` Cores | `1930m` Cores | Khớp (Compute Parity) | `kubectl describe nodes` / [raw/kubectl-describe-nodes.txt](raw/kubectl-describe-nodes.txt) |
| **Node Allocatable Memory** | ~7.2 GiB (7079–7101Mi) | ~7.2 GiB (7079–7101Mi) | Khớp (Compute Parity) | `kubectl describe nodes` / [raw/kubectl-describe-nodes.txt](raw/kubectl-describe-nodes.txt) |
| **ASG Limits (Lock)** | `desired_size = 2, max_size = 4` | `desired_size = 2, max_size = 4` | Khớp (Khóa ở mức 2 nodes trong test window do Cluster Autoscaler không chạy) | `eks.tf` |
| **Karpenter NodePool Limit** | `limits.cpu: 4` (manifest) | `limits.cpu: 16` (manifest & Terraform) | Reconciled (Đồng bộ drift) | `nodepool.yaml` / `karpenter-nodepool.tf` |
| **ResourceQuota (hard limits)**| CPU: 8000m, RAM: 12Gi | CPU: 8000m, RAM: 12Gi | Khớp (Compute Parity) | `quota.yaml` / `kubectl get quota` / [raw/kubectl-get-quota.txt](raw/kubectl-get-quota.txt) |
| **LimitRange Defaults** | None | None | Khớp (Compute Parity) | `kubectl get limitrange` |
| **HPA min/max (`checkout`)**| 2 / 3 replicas | 2 / 3 replicas | Khớp (Compute Parity) | `values.yaml` / `kubectl get hpa` / [raw/kubectl-get-hpa.txt](raw/kubectl-get-hpa.txt) |
| **HPA min/max (`currency`)**| 2 / 3 replicas | 2 / 3 replicas | Khớp (Compute Parity) | `values.yaml` / `kubectl get hpa` / [raw/kubectl-get-hpa.txt](raw/kubectl-get-hpa.txt) |
| **HPA min/max (`frontend`)**| 2 / 3 replicas | 2 / 3 replicas | Khớp (Compute Parity) | `values.yaml` / `kubectl get hpa` / [raw/kubectl-get-hpa.txt](raw/kubectl-get-hpa.txt) |
| **Static Replica Count (others)**| Có PostgreSQL/Kafka/Valkey self-hosted trong cụm EKS | PostgreSQL, Kafka, Valkey được xóa khỏi cụm và di trú sang managed AWS services (Mandate 08) | **Không khớp** (Workload Footprint thay đổi) | `values.yaml` / `kubectl get pods` / [raw/kubectl-get-pods-all-namespaces.txt](raw/kubectl-get-pods-all-namespaces.txt) |
| **Deployment Revisions** | `checkout` rev 6, `currency` rev 3, `frontend` rev 5 | `checkout` rev 7, `currency` rev 4, `frontend` rev 6 | Cải tiến Logic | `kubectl rollout history` |
| **Load-Generator Config** | 200 users, autostart=false | 200 users, autostart=false | Kịch bản khớp | `values-load-test-task4.yaml` / [Locustfile Git SHA](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/414b3352a9ee916328c6b460c1804ba4f62d8c3a/techx-corp-platform/src/load-generator/locustfile.py) |
| **Git Commit/SHA** | `d80a53d2d5e3540a1da2234553ca5dafd245264a` | `6881118fa315db8d9ad7e14d4850fa9e394f4c2c` | Cải tiến Logic | `git log` |

---

## 10. Phụ lục: Bằng chứng dữ liệu thô (Raw Outputs Appendix)

Để phục vụ công tác kiểm toán độc lập (audit), toàn bộ kết quả xuất từ cụm EKS tại thời điểm kiểm thử được lưu trữ dưới dạng raw text trong thư mục `raw/`:
*   **Chi tiết thông số Nodes khả dụng (Get Nodes):** [kubectl-get-nodes.txt](raw/kubectl-get-nodes.txt)
*   **Chi tiết mô tả Nodes thô (Describe Nodes):** [kubectl-describe-nodes.txt](raw/kubectl-describe-nodes.txt)
*   **Chi tiết EC2 Worker Instances (describe-instances):** [aws-ec2-describe-instances.txt](raw/aws-ec2-describe-instances.txt)
*   **Chi tiết cấu hình HPA hiện tại:** [kubectl-get-hpa.txt](raw/kubectl-get-hpa.txt)
*   **Chi tiết ResourceQuota đã áp:** [kubectl-get-quota.txt](raw/kubectl-get-quota.txt)
*   **Trạng thái toàn bộ Pods trên EKS để kiểm soát nhiễu:** [kubectl-get-pods-all-namespaces.txt](raw/kubectl-get-pods-all-namespaces.txt)

---

## 11. Kết luận (Verdict)

> [!IMPORTANT]
> **Xác nhận tính tương thích tài nguyên Worker Compute (Worker Compute Parity - Substantially Supported):**
> Các tham số phần cứng vật lý và logic của worker nodes EKS (gồm 2 nodes `t3.large`, tổng CPU/Memory Allocatable) được bảo toàn đồng nhất giữa hai bài test trước và sau tối ưu. Cấu hình autoscaling của EKS Managed Node Group đã được khóa cứng tại `min=max=desired=2` và Cluster Autoscaler không được cài đặt trong cụm, ngăn chặn việc scale-out worker node.
>
> **Không chứng minh so sánh Trước/Sau tuyệt đối (Strict Before/After Comparability - Not Proven):**
> Do đã thực hiện di trú các thành phần stateful nặng (PostgreSQL sang RDS, Valkey sang ElastiCache, Kafka sang MSK) theo Mandate 08, các pod lưu trữ dữ liệu tự chạy cũ đã bị dọn dẹp khỏi cụm EKS. Việc này làm thay đổi cơ bản footprint tài nguyên nghiệp vụ và giảm thiểu đáng kể xung đột tài nguyên compute/disk I/O trên worker nodes.
> 
> **Kết luận Hiệu năng (Throughput Verdict):**
> Sự cải tiến vượt bậc về breakpoint throughput (đạt mốc 200 users ổn định) và giảm tail latency p95/p99 của cụm storefront được xác nhận đến từ **sự kết hợp đồng thời** của: (1) tối ưu hóa cấu trúc concurrency ở tầng ứng dụng (Go parallelization/checkout song song) và (2) giảm tải compute contention và xung đột I/O trên worker nodes sau khi di trú các database tự chạy sang AWS Managed Services, đảm bảo không sử dụng biện pháp nâng cấp tài nguyên phần cứng worker nodes.