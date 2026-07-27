# run-spot-interruption-test.ps1
# Automate Spot Interruption test (terminate a Spot node during peak load) and capture recovery telemetry

. C:\Users\ADMIN\.gemini\antigravity-ide\brain\d5478d4c-b635-432e-bad3-da40f8b0bd05\scratch\set_aws_env.ps1

$timestamp = Get-Date -Format "yyyyMMddTHHmmssZ"
$evidenceDir = "docs/evidence/mandate13-compute-cost-optimization/runtime/spot-rehearsal-$timestamp"
New-Item -ItemType Directory -Force -Path $evidenceDir
New-Item -ItemType Directory -Force -Path "$evidenceDir/locust"

$logFile = "$evidenceDir/interruption-monitor.log"
"=== Spot Interruption Monitor started at $(Get-Date) ===" | Out-File -FilePath $logFile -Encoding utf8

# Function to log cluster state
function Log-State($phase) {
    $dateUtc = [System.DateTime]::UtcNow.ToString("yyyy-MM-dd HH:mm:ss")
    $nodes = kubectl get nodes -L karpenter.sh/capacity-type,kubernetes.io/arch,node.kubernetes.io/instance-type -o wide
    $pods = kubectl get pods -n techx-tf4 -o wide
    
    $header = "`n=========================================`n[$dateUtc] Phase: $phase`n=========================================`n"
    $header | Out-File -FilePath $logFile -Append -Encoding utf8
    
    "--- Nodes ---" | Out-File -FilePath $logFile -Append -Encoding utf8
    $nodes | Out-String | Out-File -FilePath $logFile -Append -Encoding utf8
    
    "--- Pods ---" | Out-File -FilePath $logFile -Append -Encoding utf8
    $pods | Out-String | Out-File -FilePath $logFile -Append -Encoding utf8
}

Write-Host "Recording pre-flight state..."
Log-State "Pre-flight"

# Start the 16-minute load test in background
Write-Host "Starting Locust test (LOCUST_LOAD_SHAPE=task4)..."
$locustJob = Start-Process powershell -ArgumentList '-NoProfile -Command ". C:\Users\ADMIN\.gemini\antigravity-ide\brain\d5478d4c-b635-432e-bad3-da40f8b0bd05\scratch\set_aws_env.ps1; kubectl exec -n techx-tf4 deploy/load-generator -- env LOCUST_LOAD_SHAPE=task4 LOCUST_AUTOSTART=false locust --headless --users 200 --spawn-rate 3.34 --run-time 16m20s --host http://frontend-proxy:8080 -f /tmp/locustfile_mandate13.py --csv /tmp/spot-interruption-results --html /tmp/spot-interruption-report.html --only-summary"' -PassThru -NoNewWindow

Write-Host "Locust test started. Waiting 20 seconds to settle load..."
Start-Sleep -Seconds 20

Write-Host "Peak load reached. Selecting Spot node to terminate..."
# Find an active Spot node
$spotNodes = kubectl get nodes -l karpenter.sh/capacity-type=spot -o json | ConvertFrom-Json
if ($spotNodes.items.Count -eq 0) {
    Write-Host "ERROR: No active Spot nodes found!"
    "ERROR: No active Spot nodes found!" | Out-File -FilePath $logFile -Append -Encoding utf8
    exit 1
}
$targetNode = $spotNodes.items[0]
$nodeName = $targetNode.metadata.name
$providerId = $targetNode.spec.providerID
$instanceId = ($providerId -split '/')[-1]

Write-Host "Target Spot Node: $nodeName (Instance: $instanceId)"
"Target Spot Node: $nodeName (Instance: $instanceId)" | Out-File -FilePath $logFile -Append -Encoding utf8

Log-State "Pre-interruption"

# Terminate the instance!
Write-Host "TERMINATING INSTANCE $instanceId..."
aws ec2 terminate-instances --instance-ids $instanceId | Out-String | Out-File -FilePath $logFile -Append -Encoding utf8

$startTime = Get-Date
# Monitor recovery for 5 minutes (every 10 seconds)
for ($i = 0; $i -le 30; $i++) {
    $elapsed = (Get-Date) - $startTime
    Write-Host "Monitoring recovery: $($elapsed.TotalSeconds)s elapsed..."
    Log-State "Interruption Recovery ($($elapsed.TotalSeconds)s)"
    Start-Sleep -Seconds 10
}

Write-Host "Spot Interruption test monitoring complete. Letting the test finish..."
# Wait for the remaining 8 minutes of the test (180s start + 300s recovery = 480s elapsed, test is 980s total)
Start-Sleep -Seconds 480

Write-Host "Locust test complete. Waiting 10 seconds for stats output to write..."
Start-Sleep -Seconds 10

# Copy evidence files back
Write-Host "Copying Locust reports from the pod..."
$podName = (kubectl get pods -n techx-tf4 -l app.kubernetes.io/name=load-generator -o jsonpath='{.items[0].metadata.name}')
kubectl cp "techx-tf4/${podName}:/tmp/spot-interruption-results_stats.csv" "$evidenceDir/locust/spot-interruption-results_stats.csv"
kubectl cp "techx-tf4/${podName}:/tmp/spot-interruption-results_stats_history.csv" "$evidenceDir/locust/spot-interruption-results_stats_history.csv"
kubectl cp "techx-tf4/${podName}:/tmp/spot-interruption-results_failures.csv" "$evidenceDir/locust/spot-interruption-results_failures.csv"
kubectl cp "techx-tf4/${podName}:/tmp/spot-interruption-results_exceptions.csv" "$evidenceDir/locust/spot-interruption-results_exceptions.csv"
kubectl cp "techx-tf4/${podName}:/tmp/spot-interruption-report.html" "$evidenceDir/locust/spot-interruption-report.html"

# Post-run check
Write-Host "Recording post-run checkpoint..."
Log-State "Post-run Check"

Write-Host "Finished! All artifacts saved to $evidenceDir."
