# CDO08 REL-03C — Kafka PVC/event verification evidence

## Execution record

- Date: 2026-07-15 (Asia/Saigon)
- Context: `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`
- Namespace: `techx-tf4`
- Decision: CDO04 KF-A
- Topology: one Kafka KRaft broker/controller; no multi-broker replication or
  MSK

## PVC and broker-log baseline

```text
NAME        STATUS   CAPACITY   ACCESS MODES   STORAGECLASS   VOLUMEMODE
kafka-pvc   Bound    10Gi       RWO            gp2            Filesystem

KAFKA_LOG_DIRS=/tmp/kafka-data/kraft-combined-logs
```

The effective log directory exists on the mounted PVC. Runtime/current chart
use `gp2`, while the CDO04 decision expected `gp3`. The proof does not mutate an
existing immutable claim. A `gp2` to `gp3` change requires a separate data
migration and rollback task.

## Isolated event proof before recreation

The script created a non-business topic and did not write synthetic data into
`orders`:

```text
Topic:  rel03c-pvc-proof-20260715t081719z
Marker: rel03c-event-20260715T081719Z

Produced marker: topic=rel03c-pvc-proof-20260715t081719z
rel03c-event-20260715T081719Z
Processed a total of 1 messages
```

Result: **PASS** — produce and consume worked before recreation.

Business consumer baseline before recreation:

```text
GROUP             TOPIC    PARTITION   CURRENT-OFFSET   LOG-END-OFFSET   LAG
accounting        orders   0           2699             2699             0
fraud-detection   orders   0           2699             2699             0
```

## Pod recreation and persisted marker

```text
pod "kafka-6f9ff79c54-qzc7j" deleted
deployment "kafka" successfully rolled out
Kafka API ready after restart (attempt 2).

rel03c-event-20260715T081719Z
Processed a total of 1 messages

Old pod UID: 774394c7-79cf-48d2-a8c6-cb23626ed9ec
New pod UID: 7ddefe18-b3b8-44be-b76b-2f789cb8ee36
Kafka recreation proof passed: marker and consumer groups survived pod replacement.
```

Kafka logs independently show the topic partition loaded from the PVC with
`logEndOffset=1` before the post-restart consumer read:

```text
LogLoader partition=rel03c-pvc-proof-20260715t081719z-0
dir=/tmp/kafka-data/kraft-combined-logs
logEndOffset=1
Kafka Server started
```

The complete verification command took approximately 271 seconds, including
multiple Java CLI startups, consumer-group queries, pod replacement, Kafka API
recovery, post-restart consume, and cleanup. This is not a formal broker RTO.

## Accounting and Fraud Detection recovery

After Kafka API recovery, both consumer groups returned to their original
offset and zero lag:

```text
GROUP             TOPIC    PARTITION   CURRENT-OFFSET   LOG-END-OFFSET   LAG
accounting        orders   0           2699             2699             0
fraud-detection   orders   0           2699             2699             0
```

Accounting logs recorded expected connection-refused, broker-down, and session
timeout messages while the single broker was unavailable, then the consumer
rejoined with a new consumer ID. Fraud Detection also rejoined according to the
broker group-coordinator logs. No business event was published during this
maintenance test, so unchanged offset `2699` is expected.

This demonstrates reconnect and offset persistence, not checkout producer
delivery semantics. REL-07 remains responsible for producer acknowledgement,
retry, failure visibility, and outbox decisions.

## Readiness finding

The first drill exposed that Kubernetes reported the Deployment rollout as
successful before the Kafka API accepted connections. A post-rollout consumer
timed out while the broker was still recovering. The proof script was corrected
to require a successful Kafka API call after rollout before testing event
recovery.

This is evidence that a `Running/Available` pod is not a sufficient Kafka
readiness signal and should be addressed under the probe/readiness backlog,
without changing topology in REL-03C.

## Cleanup and final state

The passing run deleted the temporary proof topic. Broker logs confirm its
partition was renamed with the `-delete` suffix and scheduled for deletion.

```text
kafka-6f9ff79c54-v45cb   1/1   Running   0
kafka-pvc                Bound  10Gi     RWO   gp2
```

## Event-gap and duplicate risk

- The marker survived ordinary pod recreation, proving persistence on the
  current PVC. Single-broker Kafka is still unavailable during restart.
- Producer requests during downtime can fail, buffer, or be lost depending on
  acknowledgements and retries; KF-A alone does not solve this REL-07 risk.
- Consumer offsets persisted, but at-least-once delivery can replay a record if
  a consumer performs a side effect and crashes before committing its offset.
- Accounting and Fraud Detection should use idempotency/deduplication for
  business effects. This drill did not claim exactly-once processing.
- Node, Availability Zone, or EBS failure remains outside this proof because
  there is no second broker or replica.

## Conclusion

KF-A persistence proof passed: Kafka loaded the test partition from the PVC,
the exact marker was readable after a real pod replacement, and Accounting and
Fraud Detection consumer groups recovered at lag zero. Kafka remains non-HA,
and the `gp2` deviation plus API-readiness gap are explicitly documented for
separate work.
