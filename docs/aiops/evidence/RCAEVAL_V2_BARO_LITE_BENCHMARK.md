# RCAEval-v2 BARO-lite Benchmark Evidence

Generated: `2026-07-17T05:16:32.732597+00:00`

## Result

| Cases | Top-1 | Top-3 | MRR | Failures |
| ---: | ---: | ---: | ---: | ---: |
| 60 | 0.7667 | 0.9333 | 0.8644 | 0 |

## Reproduction

```bash
cd techx-corp-platform/src/aiops
python -m benchmark.run /path/to/RCAEval-v2.zip --max-cases 60 --seed 7 --baseline-seconds 600 --incident-seconds 600 --guard-seconds 30
```

Selection is deterministic and stratified by RCAEval system and fault type.
The scorer compares a pre-injection baseline window with the labeled incident window, ranks metrics, then aggregates the three strongest metric signals per service.

## Per-system

| System | Cases | Top-1 | Top-3 | MRR |
| --- | ---: | ---: | ---: | ---: |
| ob | 22 | 0.9091 | 1.0000 | 0.9545 |
| ss | 19 | 0.6842 | 0.8947 | 0.8158 |
| tt | 19 | 0.6842 | 0.8947 | 0.8088 |

## Per-fault

| Fault | Cases | Top-1 | Top-3 | MRR |
| --- | ---: | ---: | ---: | ---: |
| cpu | 6 | 1.0000 | 1.0000 | 1.0000 |
| delay | 6 | 0.8333 | 1.0000 | 0.9167 |
| disk | 6 | 1.0000 | 1.0000 | 1.0000 |
| f1 | 6 | 0.6667 | 1.0000 | 0.8333 |
| f2 | 6 | 0.6667 | 1.0000 | 0.8333 |
| f3 | 6 | 0.3333 | 0.8333 | 0.6167 |
| f4 | 6 | 0.6667 | 0.6667 | 0.7500 |
| f5 | 2 | 1.0000 | 1.0000 | 1.0000 |
| loss | 6 | 0.5000 | 0.8333 | 0.6944 |
| mem | 6 | 1.0000 | 1.0000 | 1.0000 |
| socket | 4 | 1.0000 | 1.0000 | 1.0000 |

## Miss analysis

| Case | Ground truth | Rank | Top prediction |
| --- | --- | ---: | --- |
| re3ss_orders_f3_1 | orders | 2 | orders-db |
| re3tt_ts-auth-service_f1_4 | ts-auth-service | 2 | ts-order-other-service |
| re3ss_carts_f3_1 | carts | 2 | carts-db |
| re3ss_front-end_f2_2 | front-end | 2 | catalogue |
| re3tt_ts-auth-service_f2_4 | ts-auth-service | 2 | ts-order-service |
| re3tt_ts-route-service_f3_5 | ts-route-service | 5 | ts-route-mongo |
| re3tt_ts-auth-service_f3_3 | ts-auth-service | 2 | ts-admin-basic-info-service |
| re1tt_ts-train-service_loss_1 | ts-train-service | 2 | ts-admin-travel-service |
| re1ss_payment_loss_4 | payment | 2 | orders |
| re3ss_orders_f4_3 | orders | 4 | front-end |
| re2ob_productcatalogservice_delay_2 | productcatalogservice | 2 | recommendationservice |
| re3ob_currencyservice_f1_1 | currencyservice | 2 | frontend |
| re3ss_carts_f4_4 | carts | 4 | carts-db |
| re2tt_ts-order-service_loss_1 | ts-order-service | 6 | ts-preserve-service |

## Scope and limitations

- This run evaluates service localization, not incident detection precision/recall.
- BARO-lite is research-inspired and is not claimed as a reproduction of the BARO paper.
- The current benchmark uses metrics only; runtime TF4 correlation also uses logs and traces.
- RCAEval services and telemetry differ from the TF4 production service set.
- The supplied archive contains data only and no license/readme; do not redistribute it until provenance and licensing are confirmed.

This artifact is offline benchmark evidence for implementation quality. It is not the live E2E alert, precision/recall or lead-time evidence required by Mandate 07b.
