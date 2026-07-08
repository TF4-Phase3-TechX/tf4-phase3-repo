# TF4 — TechX Corp Service Takeover

**TF4:** AIO-01 + CDO-04, CDO-07, CDO-08.

## Phân công Pillar (Trụ)

Mỗi nhóm chịu trách nhiệm chính (Primary owner) các pillar sau, theo RULES.md Section 4:


| Nhóm       | Pillar(s) phụ trách                        | Trách nhiệm chính                                                                                                                            |
| ---------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **AIO-01** | AI Safety &amp; Quality                    | AI guardrails, eval, fallback, cost tracking, prompt/content safety                                                                          |
| **CDO-04** | Performance Efficiency + Cost Optimization | Right-sizing, scaling, latency, bottleneck removal; Budget guardrails, spot instances, waste elimination                                     |
| **CDO-07** | Auditability                               | K8s audit, CloudTrail, change management, log integrity, evidence collection — **backstop toàn bộ evidence của TF4**                         |
| **CDO-08** | Security + Reliability                     | Hardening, least-privilege, credentials, access control, container security; Fault tolerance, self-healing, SLO enforcement, data durability |


**Operational Excellence** (on-call, ADR, Ops Review) là trách nhiệm chung toàn TF4, không nhóm nào sở hữu riêng.

## Cấu trúc repo

```
.
├── .github/
│   └── CODEOWNERS              # PR approval: tf4-leads review required
├── deploy/                     # Script build/push image + Helm values mẫu
├── docs/
│   ├── requirements/
│   │   ├── RULES.md            # Thể lệ Phase 3 (bắt buộc đọc)
│   │   ├── GETTING_STARTED.md  # Hướng dẫn build → deploy → verify
│   │   ├── onboarding/         # Kiến trúc, SLO, ngân sách, lịch sử sự cố, pitch guide
│   │   └── mandates/           # Directive bắt buộc từ BTC (trống lúc đầu)
│   └── notes/                  # Ghi chú khảo sát hệ thống
├── techx-corp-chart/           # Helm chart — templates, dashboards, datasources, flagd, postgres
└── techx-corp-platform/        # Source code — 27 microservices
    ├── src/accounting/
    ├── src/ad/
    ├── src/cart/
    ├── src/checkout/
    ├── src/currency/
    ├── src/email/
    ├── src/flagd/
    ├── src/flagd-ui/
    ├── src/fraud-detection/
    ├── src/frontend/
    ├── src/frontend-proxy/
    ├── src/grafana/
    ├── src/image-provider/
    ├── src/jaeger/
    ├── src/kafka/
    ├── src/llm/
    ├── src/load-generator/
    ├── src/opensearch/
    ├── src/otel-collector/
    ├── src/payment/
    ├── src/postgresql/
    ├── src/product-catalog/
    ├── src/product-reviews/
    ├── src/prometheus/
    ├── src/quote/
    ├── src/recommendation/
    ├── src/shipping/
    ├── docker-compose.yml
    ├── Makefile
    └── pb/                     # Protobuf definitions
```

## Bắt đầu

Đọc [GETTING_STARTED.md](docs/requirements/GETTING_STARTED.md) để build, push image và deploy hệ thống lên Kubernetes.

## Ownership

Mọi PR cần ít nhất một thành viên [@TF4-Phase3-TechX/tf4-leads](.github/CODEOWNERS) approve.