# Hướng dẫn Cài đặt và Chuẩn bị Tiền đề Chung (Common Prerequisites & Gates)
## CDO08-MANDATE-08 — Cài đặt Hạ tầng & Cầu nối Mạng trước Di trú

Tài liệu này định nghĩa các bước chuẩn bị (Prerequisites) và các cổng kiểm duyệt (Gates) chung cho cả 3 quy trình di trú dữ liệu của Mandate 08:
1. **PostgreSQL -> Amazon RDS PostgreSQL**
2. **Valkey -> Amazon ElastiCache for Valkey**
3. **Apache Kafka -> Amazon MSK**

Các bước này bắt buộc phải được hoàn thành và kiểm tra thành công trên cụm trước khi bắt đầu thực hiện bất kỳ bước di trú dữ liệu cụ thể nào.

---

## 1. Xác minh Hiện trạng Hệ thống (Verified Current Constraints)

Qua đánh giá hiện trạng thực tế của cụm Live EKS, chúng tôi xác nhận các ràng buộc kỹ thuật sau:
* **Self-hosted Data Pods:** Cả 3 cơ sở dữ liệu tự vận hành (`postgresql`, `valkey-cart`, `kafka`) đều đang chạy (`1/1 Running`) trong cụm EKS.
* **Network Isolation:** 3 service này hiện tại đều có cấu hình `type: ClusterIP`. AWS DMS (cho Postgres), AWS ElastiCache (cho Valkey Online Migration), và AWS MSK không có cách nào kết nối trực tiếp đến các database này do giới hạn mạng ClusterIP.
* **Thiếu Custom Resource Definitions (CRDs):** 
  * Cụm EKS chưa cài đặt Argo Rollouts Controller (không tồn tại CRD `rollouts.argoproj.io`).
  * Cụm EKS chưa cài đặt Strimzi Kafka Operator (không tồn tại CRD `kafkamirrormakers2.kafka.strimzi.io`).
* **Trạng thái Codebase:** Repo hiện tại **chưa tồn tại** các file cấu hình hạ tầng và kịch bản di trú như: `rds.tf`, `dms.tf`, `elasticache.tf`, `msk.tf`, `mirrormaker2.yaml`, `riot-redis-backfill-job.yaml`, và các bash scripts bổ trợ.
* **Helm Rendering:** File `techx-corp-chart/templates/component.yaml` hiện chưa hỗ trợ xuất ra tài nguyên `kind: Rollout`. File `deploy/values-app-stamp.yaml` chưa khai báo cờ `rollouts.enabled` hoặc cấu hình kết nối tới các dịch vụ AWS Managed Services.

> [!IMPORTANT]
> **Cam kết Triển khai Codebase (Artifact Rule):**
> Tất cả các file cấu hình IaC (`*.tf`), Kubernetes manifests (`mirrormaker2.yaml`, `riot-redis-backfill-job.yaml`), và các kịch bản bash shell **chưa có sẵn** trong repo. Chúng sẽ được phát triển và tích hợp vào **Pull Request (PR) triển khai (Implementation PR) sau khi bản kế hoạch (Migration Plan) này được duyệt**. Tuyệt đối không giả định các tệp này đã tồn tại sẵn trong nhánh `main` hiện tại.

---

## 2. Kế hoạch Thiết lập Tiền đề (Prerequisites Checklist)

### 2.1. Cài đặt Argo Rollouts Controller & Cấp quyền GitOps
Để phục vụ việc chuyển đổi traffic theo mô hình Blue-Green Rollout không gây gián đoạn (hoặc giảm thiểu downtime tối đa), Argo Rollouts Controller cần được cài đặt trên cụm.

- [ ] **Bước P1.1. Cài đặt Argo Rollouts Controller:**
  Sử dụng Helm để cài đặt controller vào namespace `argo-rollouts`:
  ```bash
  helm repo add argo https://argoproj.github.io/argo-helm
  helm repo update
  helm install argo-rollouts argo/argo-rollouts --namespace argo-rollouts --create-namespace
  ```
- [ ] **Bước P1.2. Xác minh CRDs:**
  Đảm bảo CRD của Argo Rollouts đã được đăng ký thành công:
  ```bash
  kubectl get crd | grep rollouts.argoproj.io
  ```
  *Expected Output:* `rollouts.argoproj.io` xuất hiện trong danh sách.
- [ ] **Bước P1.3. Cấp quyền cho ArgoCD (GitOps):**
  Nếu ứng dụng được quản lý qua ArgoCD, đảm bảo ServiceAccount của ArgoCD có đủ quyền `ClusterRole` để `get`, `list`, `watch`, `create`, `update`, `patch`, và `delete` tài nguyên `rollouts.argoproj.io` và `rolloutmanager`.

---

### 2.2. Thiết lập Cầu nối Mạng (Network Bridge) cho ClusterIP Services
DMS Replication Instance và ElastiCache Valkey cần kết nối trực tiếp tới PostgreSQL và Valkey đang chạy trong EKS. Ta cần tạo các cầu nối mạng thông qua AWS Network Load Balancer (NLB) nội bộ.

#### A. Cầu nối PostgreSQL (EKS Postgres -> AWS DMS)
Vì PostgreSQL hiện tại chỉ có Service `ClusterIP` và nằm sâu trong mạng overlay của EKS, AWS DMS không thể quét dữ liệu.
* **Giải pháp:** Tạo một Service phụ dạng `LoadBalancer` trỏ tới các label của Pod PostgreSQL hiện tại.
* **Cấu hình Manifest mẫu (sẽ tạo ở PR triển khai):**
  ```yaml
  apiVersion: v1
  kind: Service
  metadata:
    name: postgresql-migration-bridge
    namespace: default
    annotations:
      service.beta.kubernetes.io/aws-load-balancer-type: "external"
      service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
      service.beta.kubernetes.io/aws-load-balancer-scheme: "internal"
      service.beta.kubernetes.io/aws-load-balancer-private-ipv4-addresses: "true"
  spec:
    type: LoadBalancer
    ports:
    - port: 5432
      targetPort: 5432
      protocol: TCP
    selector:
      app.kubernetes.io/name: postgresql
  ```
* **Gate bảo mật:** Security Group của EKS Worker Nodes / NLB này chỉ được phép mở inbound port `5432` cho IP của **AWS DMS Replication Instance** (hoặc Security Group của nó).

#### B. Cầu nối Valkey (EKS Valkey -> AWS ElastiCache)
ElastiCache Valkey sử dụng cơ chế Online Migration để thiết lập kênh replicate dữ liệu thời gian thực từ nguồn. Cụm ElastiCache đích cần gọi trực tiếp tới endpoint nguồn.
* **Giải pháp:** Chuyển đổi tạm thời service `valkey-cart` hiện tại hoặc tạo một service phụ dạng `LoadBalancer` trỏ tới Pod Valkey hiện tại.
* **Cấu hình Manifest mẫu (sẽ tạo ở PR triển khai):**
  ```yaml
  apiVersion: v1
  kind: Service
  metadata:
    name: valkey-migration-bridge
    namespace: default
    annotations:
      service.beta.kubernetes.io/aws-load-balancer-type: "external"
      service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
      service.beta.kubernetes.io/aws-load-balancer-scheme: "internal"
  spec:
    type: LoadBalancer
    ports:
    - port: 6379
      targetPort: 6379
      protocol: TCP
    selector:
      app.kubernetes.io/name: valkey-cart
  ```
* **Gate bảo mật:** Thiết lập Security Group chỉ cho phép dải IP Subnets của **ElastiCache Valkey** kết nối tới NLB này trên port `6379`.

#### C. Đối với Kafka (EKS Kafka -> AWS MSK)
* **Phân tích:** Khác với PostgreSQL và Valkey, công cụ di trú **MirrorMaker 2 (MM2)** sẽ được deploy trực tiếp dưới dạng Pods **bên trong cụm EKS**. 
* **Giải pháp:** Do MM2 chạy trực tiếp trong EKS, nó có thể kết nối tới EKS Kafka nguồn thông qua Service ClusterIP nội bộ (`kafka:9092`). Vì vậy, **không cần tạo NLB/Cầu nối mạng bên ngoài cho EKS Kafka**.
* **Yêu cầu mạng duy nhất:** EKS Worker Nodes phải có quyền định tuyến mạng (Outbound) và Security Group của AWS MSK phải cho phép cổng `9094` (SASL_SSL) từ EKS Worker Nodes để MM2 có thể đẩy tin nhắn sang MSK.

---

### 2.3. Cài đặt Strimzi Kafka Operator (Lựa chọn chính thức)
Đội ngũ triển khai đã thống nhất chốt lựa chọn **Phương án A: Sử dụng Strimzi Kafka Operator** để quản lý vòng đời của MirrorMaker 2 thông qua Custom Resource `KafkaMirrorMaker2`.

* **Cách cài đặt:**
  ```bash
  helm repo add strimzi https://strimzi.io/charts/
  helm repo update
  helm install strimzi-operator strimzi/strimzi-kafka-operator --namespace kafka-operator --create-namespace
  ```
* **Xác minh CRDs:** Đảm bảo Custom Resource Definition (CRD) `kafkamirrormakers2.kafka.strimzi.io` đã sẵn sàng trên cụm.
* **Lý do lựa chọn:** Khai báo cấu hình đồng bộ trực quan bằng YAML GitOps, tự động phục hồi và giám sát tốt thông qua CRD, tích hợp sẵn các chỉ số giám sát (monitoring metrics) qua JMX Prometheus và quản lý credentials kết nối an toàn.
* **Phương án dự phòng (Standalone MM2) - BỊ LOẠI BỎ:** Không sử dụng phương án tự viết manifest Deployment/Job standalone do khó cấu hình bảo mật kết nối và thiếu cơ chế tự phục hồi, giám sát lag tự động.

