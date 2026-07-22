# Ma trận xác định workload phù hợp với Spot / Graviton / ARM64

> **Thời điểm chụp trạng thái:** 2026-07-18 UTC · `techx-tf4-cluster` · `us-east-1`  
> **Mục tiêu:** Đánh giá tất cả application service và observability workload hiện có cho hai hướng: Spot và Graviton/ARM64.

## Trạng thái cluster hiện tại

| Hạng mục | Trạng thái thực tế |
|---|---|
| Worker capacity | 2 × `t3.large` Managed Node Group + 2 × `t3a.large` Karpenter node |
| Capacity type | Cả bốn worker đều là On-Demand |
| Architecture | Cả bốn worker đều là AMD64/x86_64 |
| Karpenter NodePool | `techx-general`: chỉ AMD64 + On-Demand |
| Spot node / NodeClaim | Chưa có |
| ARM64 / Graviton node | Chưa có |

## Application service

| Workload | Replica đang chạy | Khả năng Spot | Kết quả Graviton / ARM64 | Ghi chú |
|---|---:|---|---|---|
| `accounting` | 1/1 | Cần bổ sung điều kiện | Build local ARM64 đạt | Cần replica/PDB/probe; phụ thuộc Kafka/PostgreSQL |
| `ad` | 1/1 | Cần bổ sung điều kiện | Build local ARM64 đạt | Cần replica/PDB/probe |
| `cart` | 2/2 | Có thể cân nhắc | Build local ARM64 đạt; chạy Compose đạt | Có PDB, readiness/liveness, topology spread; phụ thuộc Valkey |
| `checkout` | 2/2 (HPA 2–3) | Có thể cân nhắc | Build local ARM64 đạt; chạy Compose đạt | Có PDB, readiness/liveness, topology spread; luồng doanh thu |
| `currency` | 2/2 (HPA 2–3) | Có thể cân nhắc | Build local ARM64 đạt; chạy Compose đạt | Có PDB, readiness/liveness, topology spread |
| `email` | 1/1 | Cần bổ sung điều kiện | Build local ARM64 đạt | Cần replica/PDB/probe |
| `flagd` | 1/1 | Cần bổ sung điều kiện | Image public có `linux/arm64` | Cần replica/PDB/probe |
| `fraud-detection` | 1/1 | Cần bổ sung điều kiện | Build local ARM64 đạt | Cần replica/PDB/probe; phụ thuộc Kafka |
| `frontend` | 2/2 (HPA 2–3) | Có thể cân nhắc | Build local ARM64 đạt; chạy Compose đạt | Có PDB, readiness/liveness, topology spread; luồng khách hàng |
| `frontend-proxy` | 2/2 | Có thể cân nhắc | Build local ARM64 đạt; chạy Compose đạt; HTTP 200 | Có PDB, readiness/liveness, topology spread |
| `image-provider` | 1/1 | Cần bổ sung điều kiện | Build local ARM64 đạt | Cần replica/PDB/probe |
| `kafka` | 1/1 + PVC 10Gi | Không phù hợp | Build local ARM64 đạt | Stateful; hướng phù hợp là Amazon MSK |
| `llm` | 1/1 | Cần bổ sung điều kiện | Build local ARM64 đạt | Cần replica/PDB/probe |
| `load-generator` | 1/1 | Không xét Spot | Build local ARM64 đạt | Workload kiểm thử, không phục vụ khách hàng |
| `payment` | 2/2 | Có thể cân nhắc | Build local ARM64 đạt; chạy Compose đạt | Có PDB, readiness/liveness, topology spread; luồng doanh thu |
| `postgresql` | 1/1 + PVC 10Gi | Không phù hợp | Image public có `linux/arm64` | Stateful; hướng phù hợp là RDS/Aurora |
| `product-catalog` | 2/2 | Có thể cân nhắc | Build local ARM64 đạt | Có PDB, readiness/liveness, topology spread; phụ thuộc PostgreSQL |
| `product-reviews` | 1/1 | Cần bổ sung điều kiện | Build local ARM64 đạt | Cần replica/PDB/probe; phụ thuộc Bedrock/PostgreSQL |
| `quote` | 2/2 | Có thể cân nhắc | Build local ARM64 đạt; chạy Compose đạt | Có PDB, readiness/liveness, topology spread |
| `recommendation` | 1/1 | Cần bổ sung điều kiện | Build local ARM64 đạt | Cần replica/PDB/probe |
| `shipping` | 2/2 | Có thể cân nhắc | Build local ARM64 đạt; chạy Compose đạt | Có PDB, readiness/liveness, topology spread |
| `valkey-cart` | 1/1 + PVC 5Gi | Không phù hợp | Image public có `linux/arm64` | Stateful; hướng phù hợp là ElastiCache for Valkey |

**Nhóm có thể cân nhắc đầu tiên cho AMD64 Spot:** `cart`, `checkout`, `currency`, `frontend`, `frontend-proxy`, `payment`, `product-catalog`, `quote`, `shipping`.

## Observability workload

| Workload | Trạng thái thực tế | Khả năng Spot | Kết quả Graviton / ARM64 | Ghi chú |
|---|---|---|---|---|
| `grafana` | Deployment 1/1 | Cần bổ sung điều kiện | Tất cả image đang dùng có `linux/arm64` | Cần HA/PDB/probe trước khi cân nhắc Spot |
| `jaeger` | Deployment 1/1 | Cần bổ sung điều kiện | Image public có `linux/arm64` | Cần HA/PDB/probe trước khi cân nhắc Spot |
| `metrics-server` | Deployment 1/1 | Không xét Spot ban đầu | Image public có `linux/arm64` | Platform component, giữ trên protected capacity |
| `prometheus` | Deployment 1/1 + PVC 20Gi | Không phù hợp | Cả Prometheus và config reloader có `linux/arm64` | Persistent singleton |
| `techx-observability-alertmanager` | StatefulSet 1/1 | Không phù hợp | Image public có `linux/arm64` | Stateful singleton |
| `otel-collector-agent` | DaemonSet 4/4 | Không đánh giá độc lập | Image public có `linux/arm64` | Chạy trên mọi node; ARM64 node sẽ chạy collector này |
| `opensearch` | StatefulSet 1/1 + PVC 40Gi | Không phù hợp | Build local ARM64 đạt | Stateful; hướng phù hợp là Amazon OpenSearch Service |

## Kết quả local ARM64

- Đã build local `linux/arm64` với tag `techx-corp-arm64-local:c0g78-arm64-<service>`, không push ECR.
- Build đạt cho toàn bộ custom image đang deploy: `accounting`, `ad`, `cart`, `checkout`, `currency`, `email`, `fraud-detection`, `frontend`, `frontend-proxy`, `image-provider`, `kafka`, `llm`, `load-generator`, `payment`, `product-catalog`, `product-reviews`, `quote`, `recommendation`, `shipping`, `opensearch`.
- Tất cả image local đã build đều là `arm64/linux`.
- Docker Compose ARM64 chạy được `cart`, `checkout`, `currency`, `frontend`, `frontend-proxy`, `payment`, `quote`, `shipping`; `frontend-proxy` trả HTTP `200`.
- `product-catalog` build ARM64 đạt nhưng restart trong compose test tối giản vì thiếu PostgreSQL dependency.
- `flagd-ui` không được deploy hiện tại và local build dừng do thiếu `vendor/heroicons`; đây là lỗi asset source, không phải kết luận về ARM64.
- Public image được kiểm tra bằng `docker manifest inspect`: `flagd`, PostgreSQL, Valkey, Jaeger, Grafana, Grafana sidecar, metrics-server, Prometheus, Prometheus config reloader, Alertmanager và OpenTelemetry Collector đều có `linux/arm64`.

## Ý nghĩa và việc tiếp theo

- **Khả năng Spot** dựa trên tính stateless, số replica, PDB/probe và vai trò workload; ARM64 không quyết định Spot.
- **Khả năng Graviton/ARM64** đã được xác minh bằng local ARM64 build hoặc public image manifest. Image ECR đang deploy vẫn chưa có `linux/arm64`, nên muốn rollout Graviton phải build/push multi-architecture image bằng **tag mới**.
- Các workload stateful vẫn có thể chạy ARM64 nhưng không phù hợp Spot. Hướng đích của chúng là AWS managed service, không phải chuyển worker pool.

**Nguồn:** `infra/terraform/eks.tf`, `infra/terraform/karpenter.tf`, `infra/terraform/karpenter-nodepool.tf`, `techx-corp-chart/values.yaml`, Docker local ARM64 build/Compose test.
