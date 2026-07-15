# CDO08 REL-03B — Valkey PVC/AOF verification evidence

## Execution record

- Date: 2026-07-15 (Asia/Saigon)
- Context: `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`
- Namespace: `techx-tf4`
- Decision: CDO04 VK-A
- Topology: one `valkey-cart` Deployment replica; no Sentinel/operator or
  ElastiCache

## PVC baseline and StorageClass deviation

```text
NAME              STATUS   CAPACITY   ACCESS MODES   STORAGECLASS   VOLUMEMODE
valkey-cart-pvc   Bound    5Gi        RWO            gp2            Filesystem
```

PVC persistence is active and the claim remained `Bound` throughout the drill.
However, runtime and current chart values use `gp2`, while the CDO04 decision
expected `gp3`. This task does not mutate or replace the existing claim because
`storageClassName` is immutable. Moving `gp2` to `gp3` requires a separate
approved migration task with data transfer and rollback proof.

## Runtime AOF proof

The proof reads effective Valkey runtime configuration rather than relying only
on Helm values:

```text
appendonly=yes
dir=/data
aof_enabled=1
aof_last_write_status=ok
aof_current_size=6151377
```

Result: **PASS** — AOF is enabled, points at the PVC mount, and the last write
status is healthy.

## Application cart smoke before recreation

An isolated user/cart was created through the real application path:

`load-generator → frontend POST /api/cart → cart → Valkey`

```text
userId: rel03b-20260715T075501Z
productId: OLJCESPC7Z
quantity: 3
```

The POST response contained the item, so the initial add-cart operation passed.

## Pod recreation and persistence proof

After the cart existed, only the Valkey pod was deleted:

```text
pod "valkey-cart-dd686478b-ms8m8" deleted
deployment "valkey-cart" successfully rolled out

Old pod UID: 13ed021e-902a-4606-bc72-38e21da32d56
New pod UID: 60417ef1-512e-49d8-96c8-d15e341d581c
```

The verification command completed in approximately 76 seconds including
preflight, API calls, pod deletion, rollout wait, AOF recheck, and final cart
read. This is an observed test-command duration, not a formal RTO measurement.

After the new pod became available:

```text
AOF: appendonly=yes dir=/data enabled=1 lastWrite=ok
GET /api/cart:
userId: rel03b-20260715T075501Z
productId: OLJCESPC7Z
quantity: 3
```

Result: **PASS** — the same application cart remained readable after Valkey pod
replacement.

Final pod state:

```text
valkey-cart-dd686478b-97hdp   1/1   Running   0
```

The isolated smoke-test cart was removed through `DELETE /api/cart`, which
returned HTTP `204`.

## Rollback boundary and remaining risk

- `valkey-cart-pvc` must not be deleted as rollback.
- Do not disable AOF after accepting new cart writes without explicitly
  accepting loss of those writes.
- Do not change topology or `VALKEY_ADDR` in REL-03B.
- VK-A remains single-pod persistence, not HA. Restart, node, or EBS attachment
  failures can cause downtime.
- VK-B Sentinel/operator and VK-C ElastiCache remain rejected for this phase.

## Conclusion

VK-A application-level persistence proof passed: the PVC is bound, effective
AOF is healthy, add/view cart works, and the same cart survived a real Valkey
pod recreation. The only decision mismatch is the existing `gp2` StorageClass;
it is documented and deferred to a separate migration task rather than changed
unsafely in place.
