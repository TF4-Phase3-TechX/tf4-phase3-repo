param(
    [string]$Profile = "cdo07-tf4-auditreadonly",
    [string]$Region = "us-east-1",
    [string]$TraceId = "5c54c4a617cfd2dc8f5f2472d47ddd54",
    [datetime]$StartTimeUtc = [datetime]"2026-07-28T07:00:00Z",
    [datetime]$EndTimeUtc = [datetime]"2026-07-28T08:00:00Z",
    [string]$S3ObjectKey = "mandate-14/ai-tool-audit/year=2026/month=07/day=28/hour=07/tf4-ai-audit-logs-1-2026-07-28-07-04-40-c5d15f77-a121-4cea-820a-30ca6dc6ca95.gz"
)

$ErrorActionPreference = "Stop"

function Invoke-AwsCli {
    param([string[]]$Arguments)

    $output = & aws @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }

    return ($output -join [Environment]::NewLine)
}

function Convert-ToUnixSeconds {
    param([datetime]$Value)

    return [DateTimeOffset]::new($Value.ToUniversalTime()).ToUnixTimeSeconds()
}

$identity = Invoke-AwsCli -Arguments @(
    "sts", "get-caller-identity",
    "--profile", $Profile,
    "--region", $Region,
    "--output", "json"
) | ConvertFrom-Json

$accountId = $identity.Account
$bucketName = "tf4-ai-audit-logs-$accountId"
$resultBucket = "s3://tf4-athena-query-results-$accountId/results/"
$partitionTime = $StartTimeUtc.ToUniversalTime()
$partitionYear = $partitionTime.ToString("yyyy")
$partitionMonth = $partitionTime.ToString("MM")
$partitionDay = $partitionTime.ToString("dd")
$partitionHour = $partitionTime.ToString("HH")

Write-Host "AWS identity: $($identity.Arn)"
Write-Host "Trace ID: $TraceId"

$logsQuery = "fields @timestamp, @logStream, @message | filter @message like /$TraceId/ | sort @timestamp asc | limit 20"
$logsStart = Invoke-AwsCli -Arguments @(
    "logs", "start-query",
    "--log-group-name", "/aws/eks/techx-tf4/ai-audit",
    "--start-time", (Convert-ToUnixSeconds $StartTimeUtc),
    "--end-time", (Convert-ToUnixSeconds $EndTimeUtc),
    "--query-string", $logsQuery,
    "--profile", $Profile,
    "--region", $Region,
    "--output", "json"
) | ConvertFrom-Json

do {
    Start-Sleep -Seconds 1
    $logsResult = Invoke-AwsCli -Arguments @(
        "logs", "get-query-results",
        "--query-id", $logsStart.queryId,
        "--profile", $Profile,
        "--region", $Region,
        "--output", "json"
    ) | ConvertFrom-Json
} while ($logsResult.status -in @("Scheduled", "Running"))

if ($logsResult.status -ne "Complete" -or $logsResult.results.Count -eq 0) {
    throw "Khong tim thay trace trong CloudWatch Logs. Status: $($logsResult.status)"
}

Write-Host "CloudWatch Logs: PASS ($($logsResult.results.Count) record)"

$firehose = Invoke-AwsCli -Arguments @(
    "firehose", "describe-delivery-stream",
    "--delivery-stream-name", "tf4-ai-audit-logs",
    "--profile", $Profile,
    "--region", $Region,
    "--output", "json"
) | ConvertFrom-Json

if ($firehose.DeliveryStreamDescription.DeliveryStreamStatus -ne "ACTIVE") {
    throw "Firehose khong ACTIVE."
}

Write-Host "Firehose: PASS (ACTIVE)"

$objectMetadata = Invoke-AwsCli -Arguments @(
    "s3api", "head-object",
    "--bucket", $bucketName,
    "--key", $S3ObjectKey,
    "--profile", $Profile,
    "--region", $Region,
    "--output", "json"
) | ConvertFrom-Json

if ($objectMetadata.ObjectLockMode -ne "COMPLIANCE") {
    throw "S3 object khong duoc khoa o COMPLIANCE mode."
}

Write-Host "S3 WORM: PASS (COMPLIANCE until $($objectMetadata.ObjectLockRetainUntilDate))"

$athenaSql = @"
SELECT year, month, day, hour, trace_id
FROM tf4_audit_forensics.ai_tool_audit_events
WHERE year = '$partitionYear'
  AND month = '$partitionMonth'
  AND day = '$partitionDay'
  AND hour = '$partitionHour'
  AND trace_id = '$TraceId'
LIMIT 10
"@

$athenaStart = Invoke-AwsCli -Arguments @(
    "athena", "start-query-execution",
    "--query-string", $athenaSql,
    "--work-group", "tf4-audit-forensics",
    "--result-configuration", "OutputLocation=$resultBucket",
    "--profile", $Profile,
    "--region", $Region,
    "--output", "json"
) | ConvertFrom-Json

do {
    Start-Sleep -Seconds 1
    $athenaExecution = Invoke-AwsCli -Arguments @(
        "athena", "get-query-execution",
        "--query-execution-id", $athenaStart.QueryExecutionId,
        "--profile", $Profile,
        "--region", $Region,
        "--output", "json"
    ) | ConvertFrom-Json
    $athenaState = $athenaExecution.QueryExecution.Status.State
} while ($athenaState -in @("QUEUED", "RUNNING"))

if ($athenaState -ne "SUCCEEDED") {
    throw "Athena query that bai: $($athenaExecution.QueryExecution.Status.StateChangeReason)"
}

$athenaResult = Invoke-AwsCli -Arguments @(
    "athena", "get-query-results",
    "--query-execution-id", $athenaStart.QueryExecutionId,
    "--profile", $Profile,
    "--region", $Region,
    "--output", "json"
) | ConvertFrom-Json

if ($athenaResult.ResultSet.Rows.Count -lt 2) {
    throw "Athena khong tra ve trace can tim."
}

Write-Host "Athena: PASS (query $($athenaStart.QueryExecutionId))"
Write-Host "E2E verification: PASS"
