param(
  [string]$AwsProfile = "511825856493_TF4-CostPerfReadOnlyAlerting",
  [string]$Region = "us-east-1",
  [string]$NatGatewayId = "nat-0f57f14c4e6039bf4",
  [int]$Days = 7
)

$ErrorActionPreference = "Stop"
$env:AWS_PROFILE = $AwsProfile
$env:AWS_REGION = $Region

$nowUtc = [DateTimeOffset]::UtcNow
$end = [DateTimeOffset]::new(
  $nowUtc.Year,
  $nowUtc.Month,
  $nowUtc.Day,
  $nowUtc.Hour,
  0,
  0,
  [TimeSpan]::Zero
)
$start = $end.AddDays(-$Days)
$ceStart = $start.ToString("yyyy-MM-dd")
$ceEnd = $end.ToString("yyyy-MM-dd")

Write-Output "CLOUDWATCH_WINDOW_START=$($start.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
Write-Output "CLOUDWATCH_WINDOW_END=$($end.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
Write-Output "CE_WINDOW_START=${ceStart}T00:00:00Z"
Write-Output "CE_WINDOW_END=${ceEnd}T00:00:00Z"
Write-Output "SNAPSHOT_UTC=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"

aws sts get-caller-identity --output json
aws ec2 describe-nat-gateways --filter Name=state,Values=available --output json
aws ec2 describe-flow-logs --output json
aws ec2 describe-vpc-endpoints --output json
aws ec2 describe-route-tables --output json
aws elbv2 describe-load-balancers --output json

foreach ($metric in @(
  "BytesInFromSource",
  "BytesOutToDestination",
  "BytesInFromDestination",
  "BytesOutToSource",
  "PacketsDropCount",
  "ErrorPortAllocation",
  "ActiveConnectionCount"
)) {
  Write-Output "METRIC=$metric"
  aws cloudwatch get-metric-statistics `
    --namespace AWS/NATGateway `
    --metric-name $metric `
    --dimensions Name=NatGatewayId,Value=$NatGatewayId `
    --start-time $start.ToString("yyyy-MM-ddTHH:mm:ssZ") `
    --end-time $end.ToString("yyyy-MM-ddTHH:mm:ssZ") `
    --period ($Days * 86400) `
    --statistics Sum Maximum Average `
    --output json
}

aws ce get-cost-and-usage `
  --time-period Start=$ceStart,End=$ceEnd `
  --granularity DAILY `
  --metrics UsageQuantity `
  --group-by Type=DIMENSION,Key=USAGE_TYPE `
  --output json `
  --query "ResultsByTime[].{Date:TimePeriod.Start,Estimated:Estimated,Groups:Groups[?contains(Keys[0], 'NatGateway') || contains(Keys[0], 'DataTransfer-Regional')].{UsageType:Keys[0],Quantity:Metrics.UsageQuantity.Amount,Unit:Metrics.UsageQuantity.Unit}}"

aws ce get-cost-and-usage `
  --time-period Start=$ceStart,End=$ceEnd `
  --granularity DAILY `
  --metrics UsageQuantity `
  --filter "Dimensions={Key=USAGE_TYPE,Values=DataTransfer-Regional-Bytes}" `
  --group-by Type=DIMENSION,Key=SERVICE `
  --output json

kubectl get nodes `
  -L topology.kubernetes.io/zone,node.kubernetes.io/instance-type `
  -o wide
kubectl get pods -A `
  -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,NODE:.spec.nodeName,POD_IP:.status.podIP,HOST_IP:.status.hostIP,PHASE:.status.phase" `
  --sort-by=.spec.nodeName
kubectl get deploy,statefulset -A `
  -o custom-columns="KIND:.kind,NAMESPACE:.metadata.namespace,NAME:.metadata.name,REPLICAS:.spec.replicas,SPREAD:.spec.template.spec.topologySpreadConstraints,AFFINITY:.spec.template.spec.affinity"
kubectl get svc -A `
  -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,TYPE:.spec.type,EXT_TRAFFIC:.spec.externalTrafficPolicy,INT_TRAFFIC:.spec.internalTrafficPolicy"
kubectl get ingress -A -o yaml
