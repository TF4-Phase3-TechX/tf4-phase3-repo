# CDO08 REL-03A — PostgreSQL backup/restore proof runbook

## Scope and approved architecture

REL-03A implements CDO04 option **PG-A** only: one in-cluster PostgreSQL pod,
the existing `postgresql-pvc`, and repeatable backup/restore and pod-recreation
proof. It does not introduce replication, an operator, RDS, or a storage-class
migration.

Current rollback boundary:

- Never delete or replace `postgresql-pvc` during this procedure.
- Never restore a proof dump over the live `otel` database.
- Restore validation uses the temporary database `rel03_restore_verify` on the
  same PostgreSQL instance and removes it after the check.
- A `gp2` to `gp3` change requires a separate migration task because an existing
  PVC's `storageClassName` is immutable.

## Preconditions

- `kubectl` points to the intended EKS cluster.
- The operator can get pods/PVCs, exec into PostgreSQL, and delete the
  PostgreSQL pod for the recreation drill.
- The `postgresql` Deployment is healthy in namespace `techx-tf4`.
- Run from Git Bash, WSL, or another Bash-compatible shell.

Record the target before any mutation:

```bash
kubectl config current-context
kubectl -n techx-tf4 get deploy postgresql
kubectl -n techx-tf4 get pvc postgresql-pvc
kubectl -n techx-tf4 get pod -l app.kubernetes.io/component=postgresql -o wide
```

Expected PVC baseline: `postgresql-pvc`, `Bound`, `10Gi`, `RWO`, `gp2`.

## 1. Create and validate a backup

```bash
./scripts/postgresql-backup-restore-proof.sh backup
```

The script creates a timestamped plain-SQL dump under
`artifacts/rel-03a-postgresql/`, checks that it is non-empty, and validates the
dump header and completion marker. Plain SQL is used so the proof remains
portable through `kubectl exec` streams on Windows and Unix. Dump files must
not be committed.

To select a different output path:

```bash
BACKUP_FILE=/secure/path/otel.dump \
  ./scripts/postgresql-backup-restore-proof.sh backup
```

## 2. Prove restore without overwriting live data

Use the exact path printed by the backup step:

```bash
BACKUP_FILE=artifacts/rel-03a-postgresql/otel-<timestamp>.dump \
  ./scripts/postgresql-backup-restore-proof.sh verify
```

The script:

1. Creates `rel03_restore_verify`.
2. Restores with `psql`, `ON_ERROR_STOP=1`, and a single transaction.
3. Compares table-count signatures for the `accounting`, `catalog`, and
   `reviews` schemas between source and restored databases.
4. Force-drops the temporary database through an exit trap, including on
   failure.

A passing restore is evidence that the dump is structurally usable. It does
not replace a separate staging disaster-recovery drill for production RPO/RTO.

## 3. Prove persistence through pod recreation

This step causes a short PostgreSQL outage and must run in an approved window:

```bash
CONFIRM_RECREATE=techx-tf4/postgresql \
  ./scripts/postgresql-backup-restore-proof.sh recreate-proof
```

The script records the old pod UID and schema signature, deletes only the pod,
waits for the Deployment, and passes only when the new UID differs and the
schema signature is unchanged. The explicit confirmation variable prevents an
accidental disruption. By default, every command also refuses to run unless the
current Kubernetes context contains `techx-tf4-cluster`; override
`EXPECTED_CONTEXT_PATTERN` only for an approved staging target.

## Evidence to attach to the PR

- UTC execution timestamp and `kubectl config current-context`.
- Deployment, pod, PVC, StorageClass, capacity, and access mode output.
- Backup filename, size, and successful dump validation; do not attach the dump.
- Source/restored schema signatures and `Restore proof passed` output.
- Old/new pod UID and `Pod recreation proof passed` output.
- Observed downtime, failures, and relevant PostgreSQL logs.
- CDO04 cost approval and technical-review links.

## Failure and rollback

- If backup fails, do not recreate the pod; inspect PostgreSQL health and free
  space, then rerun backup.
- If restore validation fails, the exit trap removes only the temporary restore
  database. The live `otel` database and PVC remain unchanged.
- If pod recreation does not recover, retain the PVC, inspect pod events and
  volume-attachment state, then roll back only the chart revision if a chart
  change was part of the deployment.
- Never delete the PVC as a troubleshooting or rollback action without a
  separately approved, verified backup and migration plan.

## Remaining risk

PG-A is persistence, not HA. PostgreSQL remains a single pod with RWO EBS,
therefore restart, reschedule, attachment, node, and Availability Zone failures
can cause downtime. PG-C (RDS Multi-AZ) remains deferred pending business need,
cost approval, and a separate migration/rollback plan.
