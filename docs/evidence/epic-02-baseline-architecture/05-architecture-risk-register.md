# Architecture Risk Register

| Risk ID | Risk | Impact | Likelihood | Owner | Mitigation / Follow-up |
|---|---|---|---|---|---|
| ARCH-RISK-01 | Multi-AZ chỉ áp dụng cho EKS compute layer | Có thể bị hiểu nhầm là full HA toàn hệ thống | Medium | Architecture/PM | Ghi rõ note trên diagram và pitch |
| ARCH-RISK-02 | Stateful workload HA chưa được verify | PostgreSQL/Kafka/Valkey restart có thể mất data nếu không có PVC/replication | High | Platform/Reliability | Runtime validation PVC/PV/StatefulSet |
| ARCH-RISK-03 | Single NAT Gateway là dependency risk | Nếu NAT có vấn đề, outbound từ private subnet bị ảnh hưởng | Medium | Infra/Cost | Ghi trade-off, future option NAT per AZ |
| ARCH-RISK-04 | ALB/Ingress implementation chưa verify runtime | Diagram có thể lệch với cluster thực tế | Medium | Platform | Verify `kubectl get ingress,svc` sau deploy |
| ARCH-RISK-05 | Central Flag Configuration không được bypass | Nếu bypass flagd, team vi phạm incident/fault-injection mechanism | High | Reliability/Security | Giữ `values-flagd-sync.yaml`, verify flagd |
| ARCH-RISK-06 | Cost tăng sau load test/observability | Có thể vượt budget nếu logs/traces/load-generator chạy nhiều | Medium | Cost/Performance | AWS Budget, Cost Explorer, right-size |
| ARCH-RISK-07 | SG rules chưa được verify runtime | Có thể expose service nội bộ hoặc block traffic hợp lệ | Medium | Security/Infra | Verify SG-ALB, SG-EKS-Nodes sau deploy |