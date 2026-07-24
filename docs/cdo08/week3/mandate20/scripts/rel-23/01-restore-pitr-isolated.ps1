# CDO08-REL-23 Subtask 2 - Restore-to-point-in-time ra 1 instance tam, cach ly.
# Xem docs/cdo08/week3/mandate20/implementation/CDO08-REL-23-accounting-rds-isolation-plan.md §5.
#
# Vi du:
#   .\01-restore-pitr-isolated.ps1 -RestoreTime 2026-07-20T10:00:00Z

param(
    [Parameter(Mandatory)][string]$RestoreTime,
    [string]$Region = 'us-east-1',
    [string]$SourceId = 'techx-tf4-postgresql',
    [string]$SubnetGroup = 'techx-tf4-postgresql-private',
    [string]$ParamGroup = 'techx-tf4-postgresql17-dms',
    [string]$SourceSgId = 'sg-0fbc6edd9ae2742d1',
    [string]$RunId
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

if (-not $RunId) { $RunId = New-RunId }
$targetId = "rel23-accounting-pitr-$RunId"

Write-Host "[INFO] t_restore_request=$(Get-UtcNowIso)"

# 0) Guard: RestoreTime phai nam trong cua so kha dung cua nguon
$window = aws rds describe-db-instances --region $Region --db-instance-identifier $SourceId `
    --query 'DBInstances[0].{Earliest:EarliestRestorableTime,Latest:LatestRestorableTime}' --output json | ConvertFrom-Json
Assert-LastExitCode 'aws rds describe-db-instances (restorable window)'

$restoreDt  = [datetimeoffset]::Parse($RestoreTime)
$earliestDt = [datetimeoffset]::Parse($window.Earliest)
$latestDt   = [datetimeoffset]::Parse($window.Latest)
if ($restoreDt -lt $earliestDt -or $restoreDt -gt $latestDt) {
    throw "RestoreTime=$RestoreTime ngoai cua so kha dung [$($window.Earliest), $($window.Latest)]"
}

# 1) SG tam, ingress 5432 tu dung node SG ma production dang tin cay - doc THANG tu rule 5432 dang co
#    tren SG nguon (khong doan qua tag EKS, vi tag cluster-name/cluster-resource-controller da xac
#    nhan KHONG khop SG nao trong account nay - xem plan doc §9).
$vpcId = aws ec2 describe-security-groups --region $Region --group-ids $SourceSgId --query 'SecurityGroups[0].VpcId' --output text
Assert-LastExitCode 'aws ec2 describe-security-groups (source SG)'

$nodeSgId = aws ec2 describe-security-groups --region $Region --group-ids $SourceSgId `
    --query 'SecurityGroups[0].IpPermissions[?FromPort==`5432`].UserIdGroupPairs[0].GroupId | [0]' --output text
Assert-LastExitCode 'aws ec2 describe-security-groups (node SG tu rule 5432 cua nguon)'
if ([string]::IsNullOrWhiteSpace($nodeSgId) -or $nodeSgId -eq 'None') {
    throw 'Khong tim thay dung 1 node SG qua tag filter - kiem tra lai thu cong (aws eks describe-cluster / describe-nodegroup).'
}

$tmpSgId = aws ec2 create-security-group --region $Region `
    --group-name "rel23-pitr-tmp-$RunId" --vpc-id $vpcId `
    --description 'Temp SG for REL-23 isolated PITR - delete after use' `
    --query 'GroupId' --output text
Assert-LastExitCode 'aws ec2 create-security-group'

aws ec2 authorize-security-group-ingress --region $Region `
    --group-id $tmpSgId --protocol tcp --port 5432 --source-group $nodeSgId | Out-Null
Assert-LastExitCode 'aws ec2 authorize-security-group-ingress'

# 2) Restore-to-point-in-time (mirror parameter group cua nguon - restore mac dinh khong ke thua)
aws rds restore-db-instance-to-point-in-time --region $Region `
    --source-db-instance-identifier $SourceId `
    --target-db-instance-identifier $targetId `
    --restore-time $RestoreTime `
    --no-publicly-accessible `
    --db-subnet-group-name $SubnetGroup `
    --db-parameter-group-name $ParamGroup `
    --vpc-security-group-ids $tmpSgId `
    --manage-master-user-password `
    --db-instance-class db.t4g.micro `
    --tags Key=Task,Value=CDO08-REL-23 Key=Ephemeral,Value=true | Out-Null
Assert-LastExitCode 'aws rds restore-db-instance-to-point-in-time'

Write-Host "[INFO] Waiting for $targetId available..."
aws rds wait db-instance-available --region $Region --db-instance-identifier $targetId
Assert-LastExitCode 'aws rds wait db-instance-available'
Write-Host "[INFO] t_instance_available=$(Get-UtcNowIso)"

$info = aws rds describe-db-instances --region $Region --db-instance-identifier $targetId `
    --query 'DBInstances[0].{Endpoint:Endpoint.Address,SecretArn:MasterUserSecret.SecretArn}' --output json | ConvertFrom-Json
Assert-LastExitCode 'aws rds describe-db-instances (post-restore info)'

Write-Host "[OK] Isolated PITR instance ready: $targetId"
Write-Host "     Endpoint : $($info.Endpoint)"
Write-Host "     SecretArn: $($info.SecretArn)"
Write-Host "     TmpSgId  : $tmpSgId"
Write-Host '[NOTE] KHONG cap nhat production endpoint o buoc nay.'
Write-Host "[NOTE] Cleanup: .\02-cleanup-pitr-isolated.ps1 -TargetId $targetId -TmpSgId $tmpSgId"

$outFile = ".\rel23-pitr-$RunId.json"
[pscustomobject]@{
    RunId     = $RunId
    TargetId  = $targetId
    Endpoint  = $info.Endpoint
    TmpSgId   = $tmpSgId
    RestoreTime = $RestoreTime
} | ConvertTo-Json | Set-Content -Path $outFile -Encoding utf8
Write-Host "[INFO] Da luu thong tin instance tam vao $outFile (dung lam input cho 03/06)."
