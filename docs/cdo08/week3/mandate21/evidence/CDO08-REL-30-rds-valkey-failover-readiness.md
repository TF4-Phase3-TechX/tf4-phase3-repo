# CDO08-REL-30 — RDS and Valkey Multi-AZ failover readiness

| Field | Value |
|---|---|
| Task | `[CDO08-REL-30][P0][Data] Verify RDS and Valkey Multi-AZ failover readiness` |
| Owner | Phương |
| Directive | #21 — survive an unannounced single-AZ loss under load |
| Evidence captured | 2026-07-28 (Asia/Saigon) |
| Scope | Readiness/configuration and final-drill validation procedure; this document is **not** evidence that the surprise failover drill has passed |
| Status | **PASS / failover readiness verified** — AWS control-plane configuration and live Kubernetes wiring verified. The surprise failover drill itself remains owned by the combined Directive 21 drill/REL35. |

## 1. Decision summary

- The live applications use managed-service **DNS names from External Secrets**, not an IP address, node address, or AZ-specific hostname.
- `accounting` and `product-catalog` consume `rds-postgres-secret`; `cart` consumes `elasticache-valkey-secret`, including TLS and AUTH inputs.
- Live AWS control-plane output confirms RDS Multi-AZ and a two-node, cross-AZ Valkey replication group with automatic failover/Multi-AZ.
- The Valkey client has reconnect behavior in code. RDS uses the stable RDS DNS endpoint, but automatic recovery and order correctness still need to be demonstrated by the surprise drill; endpoint correctness alone is not proof of reconnect or RPO.
- The authoritative business RPO claim is for durable order/accounting records: expected RPO `0`. Cart is TTL/cache state and reconstructable; **no RPO=0 claim is made for cart contents**.

## 2. RDS PostgreSQL readiness

### 2.1 Required AWS control-plane capture

Run from an approved read-only identity in account `511825856493`, region `us-east-1`. Preserve the complete JSON output with the drill evidence; do not substitute Terraform output.

```bash
CAPTURED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "captured_at=${CAPTURED_AT}"
aws sts get-caller-identity

aws rds describe-db-instances \
  --region us-east-1 \
  --db-instance-identifier techx-tf4-postgresql \
  --query 'DBInstances[0].{
    Identifier:DBInstanceIdentifier,
    Status:DBInstanceStatus,
    Engine:Engine,
    EngineVersion:EngineVersion,
    MultiAZ:MultiAZ,
    PrimaryAZ:AvailabilityZone,
    SecondaryAZ:SecondaryAvailabilityZone,
    Endpoint:Endpoint.Address,
    Port:Endpoint.Port,
    PubliclyAccessible:PubliclyAccessible,
    BackupRetentionDays:BackupRetentionPeriod,
    LatestRestorableTime:LatestRestorableTime,
    StorageEncrypted:StorageEncrypted,
    DeletionProtection:DeletionProtection
  }' \
  --output json
```

Acceptance:

- `Status == "available"`
- `MultiAZ == true`
- `PrimaryAZ` and `SecondaryAZ` are both non-empty and different
- `Endpoint` ends in `.rds.amazonaws.com`; it is a DNS name, not an IP
- `PubliclyAccessible == false`
- `BackupRetentionDays >= 7`, `StorageEncrypted == true`, and `DeletionProtection == true`

Live control-plane result captured at `2026-07-28T09:41:55Z` with the
`TF4-SecurityIAMSSOManager` identity in account `511825856493`. The more
appropriate `TF4-SecReliabilityReadOnlyAudit` role was tried first but lacked
`rds:DescribeDBInstances`; only read-only `describe` calls were made with the
IAM-manager profile.

```json
{
  "Identifier": "techx-tf4-postgresql",
  "Status": "available",
  "Engine": "postgres",
  "EngineVersion": "17.9",
  "MultiAZ": true,
  "PrimaryAZ": "us-east-1a",
  "SecondaryAZ": "us-east-1b",
  "Endpoint": "techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com",
  "Port": 5432,
  "PubliclyAccessible": false,
  "BackupRetentionDays": 7,
  "LatestRestorableTime": "2026-07-28T09:37:27+00:00",
  "StorageEncrypted": true,
  "DeletionProtection": true
}
```

Result: **PASS** — primary and standby are in different AZs, and all endpoint,
privacy, backup, encryption, and deletion-protection checks meet acceptance.

### 2.2 Live application/secret wiring — PASS

Read-only cluster observations on 2026-07-28:

```text
ExternalSecret/rds-postgres-secret:
  STATUS=SecretSynced  READY=True

Deployment/accounting:
  DB_CONNECTION_STRING <- rds-postgres-secret/dotnet-conn-string

Deployment/product-catalog:
  DB_CONNECTION_STRING <- rds-postgres-secret/go-conn-string
```

The secret values were inspected only to validate their shape and were not copied into this document:

- host is the stable instance DNS endpoint
  `techx-tf4-postgresql.<opaque>.us-east-1.rds.amazonaws.com`
- port is `5432`
- TLS is required
- no literal IP address and no AZ name occurs in the connection strings

Reproducible, non-secret checks:

```bash
kubectl -n techx-tf4 get externalsecret rds-postgres-secret

kubectl -n techx-tf4 get deploy accounting product-catalog \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{range .spec.template.spec.containers[*].env[?(@.name=="DB_CONNECTION_STRING")]}{.valueFrom.secretKeyRef.name}{"/"}{.valueFrom.secretKeyRef.key}{"\n"}{end}{end}'
```

Do not print or attach the decoded connection string. A reviewer with secret-read approval may validate only the hostname shape locally and record PASS/FAIL.

### 2.3 Reconnect assessment

The endpoint indirection is correct for RDS failover: applications do not pin the old primary IP. However:

- `accounting` configures Npgsql/EF Core with `UseNpgsql(connectionString)`;
- no explicit EF Core `EnableRetryOnFailure` policy is present in the reviewed source;
- a connection or transaction in flight can fail while RDS changes primary and DNS resolves to the replacement.

Therefore this evidence claims **endpoint readiness**, not proven transparent reconnect. The final drill must show that the Kafka order event is retried/reprocessed and committed exactly once at the accounting boundary. If the drill exposes a reconnect gap, add a bounded transient-failure retry around a fresh DB context/transaction; do not blindly retry non-idempotent writes.

## 3. Order/accounting correctness validation for the final drill

Before load starts, create a unique drill marker/prefix in the load generator (example: `m21-20260731T120000Z-`). Capture the set/count of successful checkout order IDs from the load generator or checkout response log. Do not infer RPO from aggregate row-count growth alone.

Run the following read-only SQL through the approved private DB access path. Substitute the real UTC window and marker.

```sql
-- Freeze a common UTC observation window.
SELECT now() AT TIME ZONE 'UTC' AS database_utc_now;

-- Durable order count in the drill namespace.
SELECT count(*) AS durable_orders,
       count(DISTINCT order_id) AS distinct_order_ids
FROM accounting."order"
WHERE order_id LIKE 'm21-20260731T120000Z-%';

-- Duplicate primary IDs should be impossible; this is an explicit audit check.
SELECT order_id, count(*) AS copies
FROM accounting."order"
WHERE order_id LIKE 'm21-20260731T120000Z-%'
GROUP BY order_id
HAVING count(*) <> 1;

-- Every durable order must have at least one item and one shipping record.
SELECT o.order_id,
       count(DISTINCT oi.product_id) AS item_count,
       count(DISTINCT s.shipping_tracking_id) AS shipping_count
FROM accounting."order" o
LEFT JOIN accounting.orderitem oi ON oi.order_id = o.order_id
LEFT JOIN accounting.shipping s ON s.order_id = o.order_id
WHERE o.order_id LIKE 'm21-20260731T120000Z-%'
GROUP BY o.order_id
HAVING count(DISTINCT oi.product_id) = 0
    OR count(DISTINCT s.shipping_tracking_id) = 0;
```

Final reconciliation:

```text
acknowledged_checkout_ids = IDs returned successful to the load generator
durable_order_ids         = matching accounting.order IDs after consumer lag returns to baseline
lost_ids                  = acknowledged_checkout_ids - durable_order_ids
unexpected_ids            = durable_order_ids - acknowledged_checkout_ids

PASS: lost_ids=0, unexpected_ids=0, duplicate query=0 rows,
      incomplete order query=0 rows, and consumer lag has converged.
```

This comparison must be retained as machine-readable ID sets/counts. `RPO=0` is only declared after it passes.

## 4. ElastiCache Valkey readiness

### 4.1 Required AWS control-plane capture

```bash
aws elasticache describe-replication-groups \
  --region us-east-1 \
  --replication-group-id techx-tf4-valkey-cart \
  --query 'ReplicationGroups[0].{
    Identifier:ReplicationGroupId,
    Status:Status,
    Engine:Engine,
    EngineVersion:EngineVersion,
    MultiAZ:MultiAZ,
    AutomaticFailover:AutomaticFailover,
    ClusterEnabled:ClusterEnabled,
    TransitEncryptionEnabled:TransitEncryptionEnabled,
    TransitEncryptionMode:TransitEncryptionMode,
    AtRestEncryptionEnabled:AtRestEncryptionEnabled,
    AuthTokenEnabled:AuthTokenEnabled,
    SnapshotRetentionDays:SnapshotRetentionLimit,
    PrimaryEndpoint:NodeGroups[0].PrimaryEndpoint,
    ReaderEndpoint:NodeGroups[0].ReaderEndpoint,
    Members:NodeGroups[0].NodeGroupMembers[].{
      CacheClusterId:CacheClusterId,
      Role:CurrentRole,
      AZ:PreferredAvailabilityZone,
      Status:ReadEndpoint
    }
  }' \
  --output json

aws elasticache describe-cache-clusters \
  --region us-east-1 \
  --show-cache-node-info \
  --query 'CacheClusters[?ReplicationGroupId==`techx-tf4-valkey-cart`].{
    CacheClusterId:CacheClusterId,
    Status:CacheClusterStatus,
    AZ:PreferredAvailabilityZone,
    Nodes:CacheNodes[].{
      NodeId:CacheNodeId,
      NodeStatus:CacheNodeStatus,
      Endpoint:Endpoint
    }
  }' \
  --output json
```

Acceptance:

- replication-group `Status == "available"`
- `MultiAZ == "enabled"` and `AutomaticFailover == "enabled"`
- one member is primary and at least one is replica
- primary and replica AZs are non-empty and different
- `TransitEncryptionEnabled == true`, `AuthTokenEnabled == true`,
  `AtRestEncryptionEnabled == true`
- `SnapshotRetentionDays >= 7`
- the app uses the replication-group primary/configuration DNS endpoint, never a cache-node endpoint

Live control-plane result captured at `2026-07-28T09:41:55Z`:

```json
{
  "Identifier": "techx-tf4-valkey-cart",
  "Status": "available",
  "MultiAZ": "enabled",
  "AutomaticFailover": "enabled",
  "ClusterEnabled": false,
  "TransitEncryptionEnabled": true,
  "TransitEncryptionMode": "required",
  "AtRestEncryptionEnabled": true,
  "AuthTokenEnabled": true,
  "SnapshotRetentionDays": 7,
  "PrimaryEndpoint": {
    "Address": "master.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com",
    "Port": 6379
  },
  "ReaderEndpoint": {
    "Address": "replica.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com",
    "Port": 6379
  },
  "Members": [
    {
      "CacheClusterId": "techx-tf4-valkey-cart-001",
      "Role": "primary",
      "AZ": "us-east-1b"
    },
    {
      "CacheClusterId": "techx-tf4-valkey-cart-002",
      "Role": "replica",
      "AZ": "us-east-1a"
    }
  ]
}
```

`describe-cache-clusters` independently returned both clusters and nodes
`available`, with `-001` in `us-east-1b` and `-002` in `us-east-1a`.

Result: **PASS** — primary and replica are available in different AZs,
automatic failover/Multi-AZ are enabled, and TLS/AUTH/encryption/snapshot
retention meet acceptance.

### 4.2 Live application/secret wiring — PASS

```text
ExternalSecret/elasticache-valkey-secret:
  STATUS=SecretSynced  READY=True

Deployment/cart (2/2 Ready):
  VALKEY_ADDR     <- elasticache-valkey-secret/valkey-address
  VALKEY_TLS      <- elasticache-valkey-secret/tls_enabled
  VALKEY_PASSWORD <- elasticache-valkey-secret/password
```

Shape-only inspection confirmed:

- address uses the managed replication-group alias
  `master.techx-tf4-valkey-cart.<opaque>.use1.cache.amazonaws.com:6379`
- TLS flag is enabled
- AUTH material exists
- no cache-node hostname, literal IP, or AZ is pinned

The cart implementation uses StackExchange.Redis `ConnectionMultiplexer`, sets
`ConnectRetry`, and configures an exponential reconnect retry policy
(`techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs`). The final drill must still measure application recovery; code inspection is not runtime proof.

## 5. Cart smoke test for the surprise failover drill

Use a unique user ID so results cannot be confused with normal load:

```text
USER_ID=m21-cart-<UTC timestamp>-<random suffix>
PRODUCT_ID=OLJCESPC7Z
QUANTITY=2
```

Execute through the same public/customer path used by the normal load generator where possible:

1. While baseline load continues, add `PRODUCT_ID` quantity `2` to `USER_ID`.
2. Read the cart and assert exactly that item/quantity.
3. Keep normal add/view operations running; mentor triggers the unannounced AZ loss.
4. During and after failover, record cart success/error rate and latency, plus the first timestamp at which the cart operation returns to SLO.
5. After recovery, add one more unit and assert the cart API is writable/readable.
6. Place one checkout through the public path and retain the returned order ID.
7. Wait for accounting consumer lag to converge, then prove that order ID exists exactly once with item and shipping rows using §3.

Cart assertions:

```text
PASS (availability): add/view recover within the Directive 21 RTO and checkout succeeds.
PASS (durable order): acknowledged checkout ID exists exactly once in accounting.
OBSERVE ONLY (cart contents): whether the pre-failover cart survives.
```

Do **not** fail or pass durable RPO solely on cart contents. Cart keys have TTL and the product decision treats cart as reconstructable. A missing pre-failover cart is customer impact and must be measured/reported, but this task does not claim cart RPO=0.

## 6. Evidence to append during mentor drill

| Evidence | Before | During/after | Pass condition |
|---|---|---|---|
| RDS control plane | §2 JSON with primary/secondary AZ | same query showing healthy service and, if RDS failed over, changed primary AZ | automatic recovery; Multi-AZ remains true |
| Valkey control plane | §4 JSON with primary/replica and AZ | same query showing roles/status after failover | available, roles healthy, cross-AZ replica retained |
| DNS/app wiring | secret reference and shape-only checks | application reconnect timestamps/errors | no IP/node/AZ pinning; recovery within RTO |
| Order RPO | acknowledged checkout ID set | §3 durable ID set and integrity queries | zero lost, unexpected, duplicate, or incomplete orders |
| Cart | unique-user add/view baseline | add/view/checkout after recovery | availability recovers; no cart RPO=0 claim |
| SLO | browse/cart/checkout baseline under continuous load | dip and recovery timestamps | committed RTO met; final task REL35 owns the combined dashboard proof |

## 7. Current gaps and handoff to REL35

1. **Must be proven in drill:** RDS application reconnect plus accounting replay/idempotency behavior. Correct DNS wiring is necessary but not sufficient.
2. REL35 may use the live control-plane/Kubernetes evidence and validation procedures here; REL-30 readiness is `PASS`, while actual failover outcome remains pending the mentor drill.
3. Least-privilege follow-up: add the required RDS/ElastiCache `Describe*` permissions to `TF4-SecReliabilityReadOnlyAudit`, then avoid using the IAM-manager profile for future evidence capture.
4. Secrets were not recorded in this evidence. Any raw terminal capture that accidentally contains decoded credentials must be redacted and the exposed credential rotated according to the security runbook.
