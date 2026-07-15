# CDO08 REL-03C — Kafka PVC/event verification runbook

## Scope

This task implements CDO04 option KF-A only: one Kafka KRaft broker/controller
and its existing PVC. It does not introduce three brokers, replication, or MSK.

## Safety and rollback boundary

- Never delete or replace `kafka-pvc` during verification or rollback.
- Use a unique temporary `rel03c-pvc-proof-*` topic; do not publish synthetic
  payloads into the business `orders` topic.
- Pod recreation causes a Kafka outage and requires explicit confirmation.
- A StorageClass change needs a separately approved PVC migration.

## Verify event flow before recreation

Runtime currently has a documented `gp2` deviation from the approved `gp3`
target, so acknowledge it without mutating the PVC:

```bash
ALLOW_CURRENT_STORAGE_CLASS=gp2 \
  ./scripts/kafka-pvc-event-proof.sh verify
```

The script verifies the PVC and mounted `KAFKA_LOG_DIRS`, creates a temporary
topic, produces and consumes a unique marker, and records Accounting and Fraud
Detection consumer-group state on the real `orders` topic. The temporary topic
is deleted through an exit trap.

## Prove persistence through pod recreation

Run during an approved short maintenance window:

```bash
ALLOW_CURRENT_STORAGE_CLASS=gp2 \
CONFIRM_RECREATE=techx-tf4/kafka \
  ./scripts/kafka-pvc-event-proof.sh recreate-proof
```

The script produces and consumes a marker, recreates only the Kafka pod, waits
for both Kubernetes rollout and the Kafka API to become ready, consumes the same
marker again, then verifies Accounting and Fraud Detection groups reconnect and
reports their offsets/lag. A failed run retains its temporary topic for
forensics; a passing run deletes it.

## Evidence checklist

- Context, broker pod, PVC state, size, mode, and actual StorageClass.
- Effective `KAFKA_LOG_DIRS` and directory existence.
- Temporary topic and unique marker before/after recreation.
- Old/new Kafka pod UID and observed command duration.
- Accounting and Fraud Detection offsets and lag before/after.
- Broker, Accounting, and Fraud Detection errors during the test window.
- Explicit `gp2` deviation and separate `gp3` migration requirement.

## Event gap and duplicate risk

- A marker surviving this drill proves broker log persistence through ordinary
  pod recreation; it does not prove HA against node/AZ/EBS loss.
- The single broker is unavailable during restart, so producers can fail or
  buffer depending on their acknowledgement/retry behavior.
- Consumer offsets persist in Kafka on the same PVC. At-least-once processing
  can still redeliver a record after a consumer crash between side effect and
  offset commit; Accounting/Fraud handlers should remain idempotent.
- REL-07 owns checkout producer acknowledgement/retry/outbox behavior. This
  task records consumer state but does not change producer semantics.

## Failure handling

- If initial produce/consume fails, do not recreate the broker.
- If rollout fails, retain the PVC and inspect pod events, EBS attachment, and
  Kafka metadata/log recovery; do not create an empty replacement claim.
- If consumer lag does not return to its pre-test level, preserve logs and stop
  further checkout tests until Accounting/Fraud owners review the gap.

## Remaining risk

KF-A is persistent single-broker Kafka, not HA. KF-B remains rejected for node
pressure/operational cost, and KF-C MSK remains deferred pending business need
and cost/technical approval.
