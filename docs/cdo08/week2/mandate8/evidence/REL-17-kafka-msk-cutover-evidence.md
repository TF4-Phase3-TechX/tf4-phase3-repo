# REL-17 Kafka -> MSK Cutover Evidence

## Scope

This evidence records the runtime cutover of the checkout event flow from self-hosted Kafka to Amazon MSK.

Components in scope:

- Producer: `checkout`
- Consumers: `accounting`, `fraud-detection`
- Migration bridge: `KafkaMirrorMaker2/orders-mirrormaker2`
- Namespace: `techx-tf4`

Time window:

- Runtime checks and promote were executed on 2026-07-22 ICT.

## Pre-Cutover State

`checkout` was paused in blue/green mode before promotion.

```text
kubectl argo rollouts get rollout checkout -n techx-tf4
```

Observed state:

```text
Rollout: checkout
Status: Paused
Message: BlueGreenPause
Desired replicas: 2
Current replicas: 4
Updated replicas: 2
Ready replicas: 2

revision 7: checkout-6bfcbcdb7d, Healthy, preview
revision 6: checkout-54ff8fcc6c, Healthy, stable, active
```

Service selectors before cutover:

```text
kubectl -n techx-tf4 get svc checkout checkout-preview -o jsonpath='{range .items[*]}{.metadata.name}{" selector="}{.spec.selector}{"\n"}{end}'
```

Result:

```text
checkout selector={"opentelemetry.io/name":"checkout","rollouts-pod-template-hash":"54ff8fcc6c"}
checkout-preview selector={"opentelemetry.io/name":"checkout","rollouts-pod-template-hash":"6bfcbcdb7d"}
```

`checkout` active revision still used self-hosted Kafka:

```text
checkout-54ff8fcc6c
KAFKA_ADDR=kafka:9092
```

`checkout` preview revision used MSK secret-backed config:

```text
checkout-6bfcbcdb7d
KAFKA_ADDR=msk-kafka-secret:kafka-address
KAFKA_SECURITY_PROTOCOL=msk-kafka-secret:security-protocol
KAFKA_SASL_MECHANISM=msk-kafka-secret:sasl-mechanism
KAFKA_USERNAME=msk-kafka-secret:username
KAFKA_PASSWORD=msk-kafka-secret:password
```

Consumers were already on MSK-backed config:

```text
accounting ready=1/1
KAFKA_ADDR=msk-kafka-secret:kafka-address
KAFKA_SECURITY_PROTOCOL=msk-kafka-secret:security-protocol
KAFKA_SASL_MECHANISM=msk-kafka-secret:sasl-mechanism
KAFKA_USERNAME=msk-kafka-secret:username
KAFKA_PASSWORD=msk-kafka-secret:password

fraud-detection ready=1/1
KAFKA_ADDR=msk-kafka-secret:kafka-address
KAFKA_SECURITY_PROTOCOL=msk-kafka-secret:security-protocol
KAFKA_SASL_MECHANISM=msk-kafka-secret:sasl-mechanism
KAFKA_USERNAME=msk-kafka-secret:username
KAFKA_PASSWORD=msk-kafka-secret:password
```

MirrorMaker2 was ready:

```text
kubectl -n techx-tf4 get kafkamirrormaker2 orders-mirrormaker2 -o jsonpath='{.metadata.name}{" conditions="}{range .status.conditions[*]}{.type}{":"}{.status}{" "}{end}{"\n"}'
```

Result:

```text
orders-mirrormaker2 conditions=Ready:True
```

## Cutover Action

The checkout producer was promoted from the active self-hosted Kafka revision to the MSK revision.

```text
kubectl argo rollouts promote checkout -n techx-tf4
```

Result:

```text
rollout 'checkout' promoted
```

## Post-Cutover State

`checkout` is now healthy and active on the MSK revision.

```text
kubectl argo rollouts get rollout checkout -n techx-tf4
```

Observed state:

```text
Rollout: checkout
Status: Healthy
Desired replicas: 2
Current replicas: 2
Updated replicas: 2
Ready replicas: 2
Available replicas: 2

revision 7: checkout-6bfcbcdb7d, Healthy, stable, active
revision 6: checkout-54ff8fcc6c, ScaledDown
```

Service selectors after cutover:

```text
checkout selector={"opentelemetry.io/name":"checkout","rollouts-pod-template-hash":"6bfcbcdb7d"}
checkout-preview selector={"opentelemetry.io/name":"checkout","rollouts-pod-template-hash":"6bfcbcdb7d"}
```

## Producer Consumer Evidence

After promote, `accounting` continued consuming order events:

```text
kubectl -n techx-tf4 logs deployment/accounting --since=3m --tail=100
```

Representative result:

```text
Order details: { "orderId": "a9676f24-8575-11f1-bb7a-e6c3e69d57b7", ... }
Order details: { "orderId": "b2463f0d-8575-11f1-bb7a-e6c3e69d57b7", ... }
Order details: { "orderId": "f0815f45-8575-11f1-ab2f-8a2288188d13", ... }
```

After promote, `fraud-detection` continued consuming order events:

```text
kubectl -n techx-tf4 logs deployment/fraud-detection --since=3m --tail=100
```

Representative result:

```text
Consumed record with orderId: a9676f24-8575-11f1-bb7a-e6c3e69d57b7, and updated total count to: 361
Consumed record with orderId: b2463f0d-8575-11f1-bb7a-e6c3e69d57b7, and updated total count to: 363
Consumed record with orderId: f0815f45-8575-11f1-ab2f-8a2288188d13, and updated total count to: 372
```

This confirms the MSK producer/consumer path is active for the post-checkout order event flow.

## Current Status

Runtime cutover status:

```text
PASS
```

What has passed:

- `checkout` active service now targets MSK-backed revision `6bfcbcdb7d`.
- `checkout` rollout is `Healthy`.
- `accounting` is ready and consumes order events through MSK config.
- `fraud-detection` is ready and consumes order events through MSK config.
- `orders-mirrormaker2` remains `Ready=True` during rollback window.

Remaining work before closing Mandate 8:

- Keep self-hosted Kafka and MirrorMaker2 during the approved observation window.
- Capture SLO/dashboard evidence for checkout success, error rate and latency after cutover.
- Run REL-18 cleanup only after PM/owner approval: disable self-hosted PostgreSQL, Valkey, Kafka and temporary migration bridge resources through GitOps.

## Rollback Boundary

If MSK cutover fails during the observation window:

1. Abort or roll back the `checkout` rollout to the previous stable revision.
2. Revert GitOps app values so `checkout`, `accounting` and `fraud-detection` use self-hosted Kafka config.
3. Keep MirrorMaker2 available until rollback data handling is explicitly closed.
4. Do not delete self-hosted Kafka or MirrorMaker2 before REL-18 cleanup approval.
