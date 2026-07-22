param(
  [string]$AwsProfile = "",
  [string]$Region = "us-east-1",
  [string]$OutputDir = "docs/evidence/directive-18/D18-COST-02-orphaned-resources/raw/before"
)

$ErrorActionPreference = "Stop"

if ($AwsProfile) {
  $env:AWS_PROFILE = $AwsProfile
  Write-Output "Using AWS Profile: $AwsProfile"
}
$env:AWS_REGION = $Region
Write-Output "Using AWS Region: $Region"

if (!(Test-Path $OutputDir)) {
  New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
  Write-Output "Created output directory: $OutputDir"
}

Write-Output "Collecting AWS Caller Identity..."
aws sts get-caller-identity --output json > "$OutputDir/caller-identity.json"

Write-Output "Collecting EBS Volumes..."
aws ec2 describe-volumes --output json > "$OutputDir/volumes.json"

Write-Output "Collecting Elastic IPs..."
aws ec2 describe-addresses --output json > "$OutputDir/addresses.json"

Write-Output "Collecting Snapshots (self)..."
# To speed up, we only describe snapshots owned by the account
$caller = Get-Content "$OutputDir/caller-identity.json" | ConvertFrom-Json
$accountId = $caller.Account
Write-Output "Detected Account ID: $accountId"
aws ec2 describe-snapshots --owner-ids self --output json > "$OutputDir/snapshots.json"

Write-Output "Collecting AMIs (self)..."
aws ec2 describe-images --owners self --output json > "$OutputDir/images.json"

Write-Output "Collecting Load Balancers..."
aws elbv2 describe-load-balancers --output json > "$OutputDir/load-balancers.json"

Write-Output "Collecting Target Groups..."
aws elbv2 describe-target-groups --output json > "$OutputDir/target-groups.json"

Write-Output "Collecting Target Health for each Target Group..."
$targetGroups = Get-Content "$OutputDir/target-groups.json" | ConvertFrom-Json
$healthResults = @()

if ($targetGroups.TargetGroups) {
  foreach ($tg in $targetGroups.TargetGroups) {
    $arn = $tg.TargetGroupArn
    $name = $tg.TargetGroupName
    Write-Output "  Querying health for target group: $name"
    
    # Run command and catch any errors (e.g. if TG is being deleted)
    try {
      $healthJson = aws elbv2 describe-target-health --target-group-arn $arn --output json | ConvertFrom-Json
      $healthResults += [PSCustomObject]@{
        TargetGroupArn = $arn
        TargetGroupName = $name
        TargetHealthDescriptions = $healthJson.TargetHealthDescriptions
      }
    } catch {
      Write-Warning "Failed to query target health for $($name): $_"
    }
  }
}

$healthResults | ConvertTo-Json -Depth 5 > "$OutputDir/target-health.json"

Write-Output "Data collection complete! Files saved to $OutputDir"
