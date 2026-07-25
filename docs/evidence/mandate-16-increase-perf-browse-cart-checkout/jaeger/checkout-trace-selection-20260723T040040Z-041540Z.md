# Checkout trace selection — 2026-07-23

## Run provenance

- Locust report: [`../locust/Locust-20260723T040040Z-041540Z.html`](../locust/Locust-20260723T040040Z-041540Z.html)
- Locust run: `2026-07-23T04:00:40Z`–`2026-07-23T04:15:40Z` (15 minutes)
- Report SHA-256: `6bb44957a89015961057cdc693cbd4df472640050de6d714a6b53956abe63559`
- Jaeger query: `service=checkout`, `operation=oteldemo.CheckoutService/PlaceOrder`, same UTC bounds, `limit=100`
- Bulk result: [`checkout-traces-20260723T040040Z-041540Z.json`](checkout-traces-20260723T040040Z-041540Z.json)

## Selected successful traces

| Role | Trace | Start UTC | Frontend `POST /api/checkout` | Checkout `PlaceOrder` | Preparation | Status | Selection |
|---|---|---|---:|---:|---:|---|---|
| Slow | [`72708ed65492c14ff800826e3857eadf`](checkout-slow-72708ed65492c14ff800826e3857eadf.json) | `2026-07-23T04:15:15.393Z` | 1,086.296ms | 979.617ms | 949.506ms | HTTP 200; gRPC 0 | Slow successful checkout with preparation occupying 96.9% of `PlaceOrder`. |
| Representative | [`94c68de4ca5269a7a092129a71ed4be9`](checkout-representative-94c68de4ca5269a7a092129a71ed4be9.json) | `2026-07-23T04:15:29.633Z` | 46.849ms | 36.483ms | 12.700ms | HTTP 200; gRPC 0 | Successful checkout from the same run window with low end-to-end latency. |

The slow trace has this parent/child path:

```text
frontend POST /api/checkout (1,086.296ms, HTTP 200)
└─ checkout PlaceOrder server (979.617ms, gRPC 0)
   └─ prepareOrderItemsAndShippingQuoteFromCart (949.506ms)
```

This establishes the trace-level timing relationship in the selected slow successful checkout. It does not, by itself, identify why the preparation span was slow or prove that every checkout in the run had the same critical path.
