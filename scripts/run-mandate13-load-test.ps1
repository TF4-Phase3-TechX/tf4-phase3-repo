# run-mandate13-load-test.ps1
# Automate Mandate 13 Task 1 load test, scaling monitor, and evidence collection

. C:\Users\ADMIN\.gemini\antigravity-ide\brain\d5478d4c-b635-432e-bad3-da40f8b0bd05\scratch\set_aws_env.ps1

$timestamp = Get-Date -Format "yyyyMMddTHHmmssZ"
$evidenceDir = "docs/evidence/mandate13-compute-cost-optimization/runtime/optimized-$timestamp"
New-Item -ItemType Directory -Force -Path $evidenceDir
New-Item -ItemType Directory -Force -Path "$evidenceDir/locust"

$logFile = "$evidenceDir/scaling-monitor.log"
$timelineFile = "$evidenceDir/timeline.csv"

Write-Host "Creating log files..."
"timestamp_utc,elapsed_minutes,node_count,spot_nodes,ondemand_nodes,checkout_replicas,frontend_replicas" | Out-File -FilePath $timelineFile -Encoding utf8
"=== Scaling Monitor Log started at $(Get-Date) ===" | Out-File -FilePath $logFile -Encoding utf8

# Function to log metrics
function Log-Metrics($elapsedMins) {
    $dateUtc = [System.DateTime]::UtcNow.ToString("yyyy-MM-dd HH:mm:ss")
    
    # Nodes details
    $nodes = kubectl get nodes -o json | ConvertFrom-Json
    $nodeCount = $nodes.items.Count
    
    $spotCount = 0
    foreach ($node in $nodes.items) {
        $labels = $node.metadata.labels
        if ($labels -and $labels.'karpenter.sh/capacity-type' -eq 'spot') {
            $spotCount++
        }
    }
    $odCount = $nodeCount - $spotCount
    
    # HPA / Pod replicas
    $checkoutReplicas = (kubectl get deployment checkout -n techx-tf4 -o jsonpath='{.spec.replicas}')
    $frontendReplicas = (kubectl get deployment frontend -n techx-tf4 -o jsonpath='{.spec.replicas}')
    
    $logMsg = "[$dateUtc] Elapsed: $elapsedMins Min | Nodes: $nodeCount (Spot: $spotCount, On-Demand: $odCount) | Checkout Replicas: $checkoutReplicas | Frontend Replicas: $frontendReplicas"
    Write-Host $logMsg
    $logMsg | Out-File -FilePath $logFile -Append -Encoding utf8
    
    "$dateUtc,$elapsedMins,$nodeCount,$spotCount,$odCount,$checkoutReplicas,$frontendReplicas" | Out-File -FilePath $timelineFile -Append -Encoding utf8
}

# Pre-flight checkpoint
Write-Host "Recording pre-flight checkpoint..."
kubectl get nodes -L karpenter.sh/capacity-type, kubernetes.io/arch, node.kubernetes.io/instance-type > "$evidenceDir/preflight-nodes.txt"
kubectl get deployments -n techx-tf4 > "$evidenceDir/preflight-deployments.txt"
kubectl get hpa -n techx-tf4 > "$evidenceDir/preflight-hpa.txt"
kubectl get pods -n techx-tf4 -o wide > "$evidenceDir/preflight-pods.txt"

# 1. Start locust headless load test in background
Write-Host "Starting Locust headless test in the pod..."
$locustJob = Start-Process powershell -ArgumentList '-NoProfile -Command ". C:\Users\ADMIN\.gemini\antigravity-ide\brain\d5478d4c-b635-432e-bad3-da40f8b0bd05\scratch\set_aws_env.ps1; kubectl exec -n techx-tf4 deploy/load-generator -- env LOCUST_LOAD_SHAPE=mandate13 LOCUST_AUTOSTART=false locust --headless --users 200 --spawn-rate 5 --run-time 60m --host http://frontend-proxy:8080 -f /tmp/locustfile_mandate13.py --csv /tmp/mandate13-results --html /tmp/mandate13-report.html --only-summary"' -PassThru -NoNewWindow

Write-Host "Locust test started. Running 60 minutes monitor loop..."

# Monitor loop for 60 minutes (60 cycles of 1 minute)
for ($i = 0; $i -le 60; $i++) {
    Log-Metrics $i
    if ($i -lt 60) {
        Start-Sleep -Seconds 60
    }
}

Write-Host "60 minutes load test complete. Waiting 10 seconds for Locust output to write..."
Start-Sleep -Seconds 10

# 2. Copy evidence files back
Write-Host "Copying Locust reports from the pod..."
$podName = (kubectl get pods -n techx-tf4 -l app.kubernetes.io/name=load-generator -o jsonpath='{.items[0].metadata.name}')
kubectl cp "techx-tf4/${podName}:/tmp/mandate13-results_stats.csv" "$evidenceDir/locust/mandate13-results_stats.csv"
kubectl cp "techx-tf4/${podName}:/tmp/mandate13-results_stats_history.csv" "$evidenceDir/locust/mandate13-results_stats_history.csv"
kubectl cp "techx-tf4/${podName}:/tmp/mandate13-results_failures.csv" "$evidenceDir/locust/mandate13-results_failures.csv"
kubectl cp "techx-tf4/${podName}:/tmp/mandate13-results_exceptions.csv" "$evidenceDir/locust/mandate13-results_exceptions.csv"
kubectl cp "techx-tf4/${podName}:/tmp/mandate13-report.html" "$evidenceDir/locust/mandate13-report.html"
# Post-run check
Write-Host "Recording post-run checkpoint..."
kubectl get nodes -L karpenter.sh/capacity-type, kubernetes.io/arch, node.kubernetes.io/instance-type > "$evidenceDir/postrun-nodes.txt"
kubectl get deployments -n techx-tf4 > "$evidenceDir/postrun-deployments.txt"
kubectl get pods -n techx-tf4 -o wide > "$evidenceDir/postrun-pods.txt"

Write-Host "Finished! All artifacts saved to $evidenceDir."
