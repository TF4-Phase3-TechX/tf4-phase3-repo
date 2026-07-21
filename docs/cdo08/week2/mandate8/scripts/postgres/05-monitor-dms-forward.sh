#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-tf4}"
export AWS_PAGER="${AWS_PAGER:-}"
DMS_TASK_ARN="${DMS_TASK_ARN:-arn:aws:dms:us-east-1:511825856493:task:7SDVOIB6RVGXJP3M5WK72BNYKY}"
DMS_TASK_ID="${DMS_TASK_ID:-techx-tf4-postgresql-forward}"
DMS_LOG_GROUP="${DMS_LOG_GROUP:-dms-tasks-techx-tf4-postgresql-dms}"
DMS_LOG_STREAM="${DMS_LOG_STREAM:-dms-task-7SDVOIB6RVGXJP3M5WK72BNYKY}"
SINCE_MINUTES="${SINCE_MINUTES:-30}"

command -v aws >/dev/null 2>&1 || { echo "[ERROR] Missing aws CLI" >&2; exit 1; }

echo "[INFO] DMS task status:"
aws dms describe-replication-tasks \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --filters "Name=replication-task-id,Values=$DMS_TASK_ID" \
  --query 'ReplicationTasks[0].{Id:ReplicationTaskIdentifier,Status:Status,StopReason:StopReason,LastFailureMessage:LastFailureMessage,Progress:ReplicationTaskStats.FullLoadProgressPercent,Loaded:ReplicationTaskStats.TablesLoaded,Loading:ReplicationTaskStats.TablesLoading,Queued:ReplicationTaskStats.TablesQueued,Errored:ReplicationTaskStats.TablesErrored,Elapsed:ReplicationTaskStats.ElapsedTimeMillis}'

echo "[INFO] DMS table statistics:"
aws dms describe-table-statistics \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --replication-task-arn "$DMS_TASK_ARN" \
  --query 'TableStatistics[*].{Table:join(`.`,[SchemaName,TableName]),State:TableState,Rows:FullLoadRows,Validation:ValidationState,Failed:ValidationFailedRecords,LastFailure:LastFailureMessage}'

start_time="$(( ($(date +%s) - SINCE_MINUTES * 60) * 1000 ))"
echo "[INFO] Recent DMS log messages from last $SINCE_MINUTES minutes:"
aws logs filter-log-events \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --log-group-name "$DMS_LOG_GROUP" \
  --log-stream-names "$DMS_LOG_STREAM" \
  --start-time "$start_time" \
  --limit 100 \
  --query 'events[*].message'
