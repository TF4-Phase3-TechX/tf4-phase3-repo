# CDO08 REL-03A — PostgreSQL backup/restore proof

## Execution record

- Date: 2026-07-15 (Asia/Saigon)
- Target context: `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`
- Namespace: `techx-tf4`
- Architecture decision: CDO04 PG-A

## Read-only runtime baseline

The current operator identity successfully verified the Deployment and PVC:

```text
NAME         READY   UP-TO-DATE   AVAILABLE   AGE
postgresql   1/1     1            1           7d12h

NAME             STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
postgresql-pvc   Bound    pvc-e0600223-7b8a-4bc6-ab58-bdb77e9653e0   10Gi       RWO            gp2            40h
```

This confirms that REL-03A retains the existing single PostgreSQL Deployment
and existing `postgresql-pvc`; no topology, RDS, operator, or StorageClass
change was made.

## Backup proof

After the namespace RBAC update, an actual `kubectl exec` and the backup command
completed successfully. The successful operation is authoritative even though
an earlier `kubectl auth can-i create pods/exec` check returned `no`.

```text
deployment "postgresql" successfully rolled out
Creating a plain-SQL backup from techx-tf4/postgresql:otel
Backup validated: artifacts/rel-03a-postgresql/otel-20260715T074207Z.sql
```

Local artifact metadata:

```text
Name:             otel-20260715T074207Z.sql
Size:             3,850,924 bytes
LastWriteTimeUtc: 2026-07-15 07:42:19Z
```

The artifact is intentionally ignored by Git because it contains database
content.

## Restore proof

The SQL backup was restored into temporary database `rel03_restore_verify` in a
single transaction. Restore results included:

```text
COPY 12750
COPY 23242
COPY 12750
COPY 10
COPY 50

Source schema signature:
accounting:3
catalog:1
reviews:1
Restored schema signature:
accounting:3
catalog:1
reviews:1
Restore proof passed in temporary database: rel03_restore_verify
```

The exit cleanup force-dropped the temporary database. The live `otel` database
was never overwritten.

## Pod recreation proof

The original pod `postgresql-5b49658ddf-xqblg` was deleted after a valid backup
and restore proof existed. The Deployment recovered successfully in about 39
seconds as observed by the verification command, and schema signatures remained
unchanged.

```text
pod "postgresql-5b49658ddf-xqblg" deleted from techx-tf4 namespace
deployment "postgresql" successfully rolled out
Pod recreation proof passed: UID changed and schema signature persisted.
```

Final runtime state:

```text
postgresql-5b49658ddf-b4p2m   1/1   Running   0   59s
postgresql-pvc   Bound   10Gi   RWO   gp2
```

Result: **PASS** — backup validation, isolated restore, pod recreation, and PVC
persistence proof all completed successfully.

## Delivered verification workflow

`scripts/postgresql-backup-restore-proof.sh` provides three guarded operations:

- `backup`: produces a portable plain-SQL dump and validates its header and
  completion marker;
- `verify`: restores only into `rel03_restore_verify`, compares application
  schema signatures, and cleans up the temporary database;
- `recreate-proof`: requires an explicit confirmation, recreates only the pod,
  and verifies a changed pod UID plus an unchanged schema signature.

Backup artifacts are excluded from Git because they may contain sensitive
business data.

## Remaining review gate

Technical review approval must still be linked before merge.

PG-A remains persistence with short accepted downtime, not High Availability.
