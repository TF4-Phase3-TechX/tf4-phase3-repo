# Architecture Assumptions

## Assumption 1: Multi-AZ applies to EKS compute layer only

Team triển khai 2 worker nodes across 2 AZs để tăng resilience ở tầng compute.

Không claim:

- Full application HA
- PostgreSQL HA
- Kafka HA
- Valkey HA
- OpenSearch HA
- Prometheus HA

## Assumption 2: Single NAT Gateway for Week 1 cost control

Week 1 dùng Single NAT Gateway để giảm cost.

Known trade-off:

Single NAT Gateway là network dependency risk.

Future option:

NAT Gateway per AZ nếu cần network HA cao hơn.

## Assumption 3: ALB forwards traffic to frontend-proxy

High-level diagram thể hiện user traffic đi vào ALB, sau đó forward vào EKS và `frontend-proxy`.
## Assumption 4: Data & Messaging are in-cluster baseline

PostgreSQL, Valkey và Kafka đang được thể hiện là in-cluster data/messaging layer.

## Assumption 5: Central Flag Configuration is external flag source

Central Flag Configuration là nguồn flag/config bên ngoài EKS.

Không mặc định xem nó là AWS AppConfig nếu chưa có evidence.

flagd là thành phần trong EKS nhận read-only flag sync.

## Assumption 6: AWS Budgets and Cost Explorer are required for cost visibility

Hai thành phần này không nằm trong request path nhưng cần cho cost baseline và budget guardrail của TF4.
