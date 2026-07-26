#!/usr/bin/env bash
set -euo pipefail

for variable in AWS_REGION TARGET_MASTER_SECRET_ARN RESTORE_ENDPOINT \
  ACCOUNTING_SOURCE_DB ACCOUNTING_TARGET_DB; do
  [[ -n "${!variable:-}" ]] || {
    echo "Missing remote variable $variable" >&2
    exit 1
  }
done

umask 077
DUMP=/tmp/rel25-accounting.dump
trap 'rm -f "$DUMP"' EXIT

SECRET_JSON="$(aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$TARGET_MASTER_SECRET_ARN" \
  --query SecretString --output text)"
PGUSER="$(printf '%s' "$SECRET_JSON" | jq -r .username)"
PGPASSWORD="$(printf '%s' "$SECRET_JSON" | jq -r .password)"
export PGUSER PGPASSWORD PGSSLMODE=require
unset SECRET_JSON

pg_isready -h "$RESTORE_ENDPOINT" -p 5432 -d "$ACCOUNTING_SOURCE_DB" -t 10
psql -h "$RESTORE_ENDPOINT" -d postgres -v ON_ERROR_STOP=1 \
  -c "drop database if exists $ACCOUNTING_TARGET_DB;"
psql -h "$RESTORE_ENDPOINT" -d postgres -v ON_ERROR_STOP=1 \
  -c "create database $ACCOUNTING_TARGET_DB;"

pg_dump -h "$RESTORE_ENDPOINT" -d "$ACCOUNTING_SOURCE_DB" \
  --format=custom --no-owner --no-privileges --schema=accounting --file="$DUMP"
test -s "$DUMP"

psql -h "$RESTORE_ENDPOINT" -d "$ACCOUNTING_TARGET_DB" \
  -v ON_ERROR_STOP=1 -c 'create schema accounting;'
pg_restore -h "$RESTORE_ENDPOINT" -d "$ACCOUNTING_TARGET_DB" \
  --no-owner --no-privileges --schema=accounting --exit-on-error "$DUMP"

SOURCE_COUNTS="$(psql -h "$RESTORE_ENDPOINT" -d "$ACCOUNTING_SOURCE_DB" \
  -At -F, -v ON_ERROR_STOP=1 -c \
  'select
     (select count(*) from accounting."order"),
     (select count(*) from accounting.shipping),
     (select count(*) from accounting.orderitem);')"
TARGET_COUNTS="$(psql -h "$RESTORE_ENDPOINT" -d "$ACCOUNTING_TARGET_DB" \
  -At -F, -v ON_ERROR_STOP=1 -c \
  'select
     (select count(*) from accounting."order"),
     (select count(*) from accounting.shipping),
     (select count(*) from accounting.orderitem);')"
test "$SOURCE_COUNTS" = "$TARGET_COUNTS"

read -r DUPLICATES SHIPPING_ORPHANS ITEM_ORPHANS UNEXPECTED_SCHEMAS <<<"$(
  psql -h "$RESTORE_ENDPOINT" -d "$ACCOUNTING_TARGET_DB" \
    -At -F' ' -v ON_ERROR_STOP=1 -c \
    "select
       (select count(*) from (
          select order_id from accounting.\"order\"
          group by order_id having count(*) > 1
        ) d),
       (select count(*) from accounting.shipping s
          left join accounting.\"order\" o on o.order_id=s.order_id
          where o.order_id is null),
       (select count(*) from accounting.orderitem i
          left join accounting.\"order\" o on o.order_id=i.order_id
          where o.order_id is null),
       (select count(*) from information_schema.schemata
          where schema_name in ('catalog','reviews'));"
)"

test "$DUPLICATES" = 0
test "$SHIPPING_ORPHANS" = 0
test "$ITEM_ORPHANS" = 0
test "$UNEXPECTED_SCHEMAS" = 0

SEQUENCE_COUNT="$(psql -h "$RESTORE_ENDPOINT" -d "$ACCOUNTING_TARGET_DB" \
  -At -v ON_ERROR_STOP=1 -c \
  "select count(*) from information_schema.sequences
   where sequence_schema='accounting';")"

echo "validation=PASS source_counts=$SOURCE_COUNTS target_counts=$TARGET_COUNTS duplicates=$DUPLICATES shipping_orphans=$SHIPPING_ORPHANS item_orphans=$ITEM_ORPHANS unexpected_schemas=$UNEXPECTED_SCHEMAS sequence_count=$SEQUENCE_COUNT"
