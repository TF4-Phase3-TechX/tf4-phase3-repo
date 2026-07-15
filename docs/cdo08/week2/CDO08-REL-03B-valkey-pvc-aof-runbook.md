# CDO08 REL-03B — Valkey PVC/AOF verification runbook

## Scope

This task implements CDO04 option VK-A only: one Valkey pod, one existing PVC,
and AOF. It does not introduce Sentinel, an operator, replicas, or ElastiCache.

## Safety boundary

- Never delete or replace `valkey-cart-pvc` during this proof.
- Pod recreation causes a short cart outage and requires explicit confirmation.
- The smoke test uses an isolated user ID prefixed `rel03b-`.
- An existing PVC StorageClass is immutable. A `gp2` to `gp3` correction must
  use a separately approved backup/migration/rollback task.

## Verify PVC, AOF, and application cart flow

The approved target is `gp3`. If runtime still uses the known `gp2` deviation,
the script refuses by default. Record and explicitly acknowledge it without
mutating the PVC:

```bash
ALLOW_CURRENT_STORAGE_CLASS=gp2 \
  ./scripts/valkey-pvc-aof-proof.sh verify
```

The command verifies:

- PVC status is `Bound`;
- runtime `appendonly=yes`;
- runtime directory is `/data`;
- `aof_enabled=1` and `aof_last_write_status=ok`;
- `POST /api/cart` and `GET /api/cart` work through frontend → cart → Valkey.

## Prove persistence through pod recreation

Run in an approved short maintenance window:

```bash
ALLOW_CURRENT_STORAGE_CLASS=gp2 \
CONFIRM_RECREATE=techx-tf4/valkey-cart \
  ./scripts/valkey-pvc-aof-proof.sh recreate-proof
```

The test adds an isolated cart, deletes only the Valkey pod, waits for the
Deployment, confirms the pod UID changed, rechecks AOF, and reads the same cart
through the application API.

## Rollback and failure handling

- If the initial smoke fails, do not recreate the pod; inspect frontend, cart,
  and Valkey logs.
- If recreation recovery fails, retain the PVC and inspect events and EBS
  attachment. Do not delete the claim.
- Do not disable AOF as rollback after new cart writes without accepting loss of
  those writes.
- Do not change `VALKEY_ADDR` or topology in this task.

## Evidence checklist

- Context, Deployment and pod state.
- PVC name, status, size, access mode, and actual StorageClass.
- AOF runtime configuration and persistence status.
- Add/view cart output before recreation.
- Old/new pod UID, rollout duration, and cart output after recreation.
- Explicit `gp2` deviation and separate `gp3` migration requirement.
- CDO04 approval and technical-review link.

## Remaining risk

VK-A is persistence, not HA. The single pod can cause downtime during restart,
node failure, or EBS attachment. Cart is temporary business state, so CDO04
accepted this trade-off and rejected Sentinel/operator and ElastiCache for this
phase.
