param(
  [string]$AwsProfile = "",
  [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

if ($AwsProfile) {
  $env:AWS_PROFILE = $AwsProfile
  Write-Output "Using AWS Profile: $AwsProfile"
}
$env:AWS_REGION = $Region
Write-Output "Using AWS Region: $Region"

Write-Output "--------------------------------------------------"
Write-Output "Executing [D18-COST-02] Cleanup Action Plan"
Write-Output "Change Ticket: CHG-D18-COST-02-001"
Write-Output "Execution Timestamp (UTC): $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"
Write-Output "--------------------------------------------------"

# 1. Delete EBS volume
Write-Output "1. Deleting orphaned EBS Volume: vol-0ce59bf32f9aea7d5..."
try {
  aws ec2 delete-volume --volume-id vol-0ce59bf32f9aea7d5 --output json
  Write-Output "   Successfully deleted volume vol-0ce59bf32f9aea7d5."
} catch {
  Write-Warning "   Failed to delete volume vol-0ce59bf32f9aea7d5: $_"
}

# 2. Release EIP
Write-Output "2. Releasing orphaned Elastic IP: 32.192.113.119 (allocation-id: eipalloc-02d48563f995b22e7)..."
try {
  aws ec2 release-address --allocation-id eipalloc-02d48563f995b22e7 --output json
  Write-Output "   Successfully released Elastic IP."
} catch {
  Write-Warning "   Failed to release Elastic IP: $_"
}

# 3. Delete Snapshot
Write-Output "3. Deleting orphaned Snapshot: snap-00b810dbb6c60cb24..."
try {
  aws ec2 delete-snapshot --snapshot-id snap-00b810dbb6c60cb24 --output json
  Write-Output "   Successfully deleted snapshot snap-00b810dbb6c60cb24."
} catch {
  Write-Warning "   Failed to delete snapshot snap-00b810dbb6c60cb24: $_"
}

# 4. Tag remaining snapshots
Write-Output "4. Tagging retained active Snapshots..."
$snapshots = @(
  "snap-08fbbd4c5e28e5a52",
  "snap-01d08c626e22d126f",
  "snap-0b9747602cda3a42f",
  "snap-03ab92962492589ac",
  "snap-0bc60477704cf22be",
  "snap-0af63905df3f4edb8",
  "snap-0c11c20be17feec23",
  "snap-0f1c39885a3145560"
)

try {
  aws ec2 create-tags --resources $snapshots --tags Key=Owner,Value=CDO_04 Key=Environment,Value=Phase3 Key=lifecycle,Value=backup --output json
  Write-Output "   Successfully tagged 8 retained snapshots."
} catch {
  Write-Warning "   Failed to tag snapshots: $_"
}

Write-Output "--------------------------------------------------"
Write-Output "Cleanup and tagging operations complete!"
Write-Output "--------------------------------------------------"
