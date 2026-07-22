param(
  [string]$AwsProfile = "",
  [string]$Region = "us-east-1",
  [string]$InputDir = "docs/evidence/directive-18/D18-COST-02-orphaned-resources/raw/before"
)

$ErrorActionPreference = "Stop"

if ($AwsProfile) {
  $env:AWS_PROFILE = $AwsProfile
}
$env:AWS_REGION = $Region

$lbFile = "$InputDir/load-balancers.json"
if (!(Test-Path $lbFile)) {
  Write-Error "Load balancers file not found at $lbFile"
}

$lbs = Get-Content $lbFile | ConvertFrom-Json
$referencedTgs = @()

foreach ($lb in $lbs.LoadBalancers) {
  $arn = $lb.LoadBalancerArn
  $name = $lb.LoadBalancerName
  Write-Output "Querying listeners for load balancer: $name"
  
  try {
    $listenersJson = aws elbv2 describe-listeners --load-balancer-arn $arn --output json | ConvertFrom-Json
    foreach ($listener in $listenersJson.Listeners) {
      $listenerArn = $listener.ListenerArn
      Write-Output "  Querying rules for listener: $listenerArn"
      
      # Check default actions
      foreach ($action in $listener.DefaultActions) {
        if ($action.TargetGroupArn) {
          $referencedTgs += $action.TargetGroupArn
        }
        if ($action.ForwardConfig -and $action.ForwardConfig.TargetGroups) {
          foreach ($tgTuple in $action.ForwardConfig.TargetGroups) {
            $referencedTgs += $tgTuple.TargetGroupArn
          }
        }
      }
      
      # Query rules
      try {
        $rulesJson = aws elbv2 describe-rules --listener-arn $listenerArn --output json | ConvertFrom-Json
        foreach ($rule in $rulesJson.Rules) {
          foreach ($action in $rule.Actions) {
            if ($action.TargetGroupArn) {
              $referencedTgs += $action.TargetGroupArn
            }
            if ($action.ForwardConfig -and $action.ForwardConfig.TargetGroups) {
              foreach ($tgTuple in $action.ForwardConfig.TargetGroups) {
                $referencedTgs += $tgTuple.TargetGroupArn
              }
            }
          }
        }
      } catch {
        Write-Warning "    Failed to query rules for listener $($listenerArn): $_"
      }
    }
  } catch {
    Write-Warning "  Failed to query listeners for load balancer $($name): $_"
  }
}

$referencedTgs = $referencedTgs | Select-Object -Unique
Write-Output "`nReferenced Target Groups found:"
foreach ($tg in $referencedTgs) {
  Write-Output "  $tg"
}

$referencedTgs | ConvertTo-Json > "$InputDir/referenced-target-groups.json"
Write-Output "Saved referenced target groups to $InputDir/referenced-target-groups.json"
