#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-tf4}"
export AWS_PAGER="${AWS_PAGER:-}"
DMS_TASK_ARN="${DMS_TASK_ARN:-arn:aws:dms:us-east-1:511825856493:task:7SDVOIB6RVGXJP3M5WK72BNYKY}"
START_TYPE="${START_TYPE:-reload-target}"
CONFIRM_START_DMS="${CONFIRM_START_DMS:-}"

if [[ "${1:-}" == "--yes" ]]; then
  CONFIRM_START_DMS="YES"
fi

command -v aws >/dev/null 2>&1 || { echo "[ERROR] Missing aws CLI" >&2; exit 1; }

if [[ "$CONFIRM_START_DMS" != "YES" ]]; then
  echo "[ERROR] This is a live DMS migration action. Re-run with CONFIRM_START_DMS=YES or pass --yes." >&2
  echo "[INFO] START_TYPE defaults to reload-target. Use START_TYPE=start-replication only for the first start."
  exit 1
fi

echo "[INFO] Current task status:"
aws dms describe-replication-tasks \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --filters "Name=replication-task-arn,Values=$DMS_TASK_ARN" \
  --query 'ReplicationTasks[0].{Id:ReplicationTaskIdentifier,Status:Status,StopReason:StopReason,Progress:ReplicationTaskStats.FullLoadProgressPercent}'

echo "[INFO] Starting DMS task with type: $START_TYPE"
aws dms start-replication-task \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --replication-task-arn "$DMS_TASK_ARN" \
  --start-replication-task-type "$START_TYPE"

echo "[OK] DMS start command submitted. Run 05-monitor-dms-forward.sh next."
