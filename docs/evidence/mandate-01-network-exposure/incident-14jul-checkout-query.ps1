# INCIDENT QUERY SCRIPT — Checkout/Payment loi 14:15-14:30 +07:00 ngay 14/07/2026
# CDO07 — hung.hoangkim
# Chay ngay khi co credentials moi

$INCIDENT_START = "2026-07-14T07:15:00Z"   # 14:15 +07 = 07:15 UTC
$INCIDENT_END   = "2026-07-14T07:30:00Z"   # 14:30 +07 = 07:30 UTC
$NOW            = Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz"

Write-Output "============================================"
Write-Output "INCIDENT INVESTIGATION — $NOW"
Write-Output "Window: $INCIDENT_START — $INCIDENT_END (UTC)"
Write-Output "============================================"

# --- 1. REFRESH KUBECONFIG ---
Write-Output "`n[1] Refresh kubeconfig..."
aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1 2>&1

# --- 2. POD STATUS HIEN TAI ---
Write-Output "`n[2] Pod status hien tai (checkout/payment/cart/frontend-proxy)..."
kubectl -n techx-tf4 get pods | Select-String -Pattern "checkout|payment|cart|frontend-proxy|NAME"

# --- 3. POD EVENTS TRONG WINDOW ---
Write-Output "`n[3] Kubernetes Events (Warning only)..."
kubectl -n techx-tf4 get events --field-selector type=Warning --sort-by='.lastTimestamp' 2>&1 | Select-Object -Last 30

# --- 4. RESTART COUNT ---
Write-Output "`n[4] Restart counts (checkout/payment/cart)..."
kubectl -n techx-tf4 get pods -o custom-columns="NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount,STARTED:.status.startTime" 2>&1 | Select-String -Pattern "checkout|payment|cart|NAME"

# --- 5. CLOUDTRAIL EVENTS trong window ---
Write-Output "`n[5] CloudTrail events trong incident window..."
aws cloudtrail lookup-events `
  --region us-east-1 `
  --start-time $INCIDENT_START `
  --end-time $INCIDENT_END `
  --max-results 20 `
  --query "Events[].{Time:EventTime,Name:EventName,User:Username,Source:EventSource}" `
  --output table 2>&1

# --- 6. JAEGER TRACES checkout/payment trong window ---
Write-Output "`n[6] Jaeger traces checkout/payment (can tunnel)..."
$startUs = [DateTimeOffset]::Parse($INCIDENT_START).ToUnixTimeMilliseconds() * 1000
$endUs   = [DateTimeOffset]::Parse($INCIDENT_END).ToUnixTimeMilliseconds() * 1000

foreach ($svc in @("checkout", "payment", "cart")) {
    try {
        $r = Invoke-RestMethod "http://localhost:16686/jaeger/ui/api/traces?service=$svc&limit=20&start=$startUs&end=$endUs" -TimeoutSec 10
        $errors = $r.data | Where-Object { $_.spans | Where-Object { $_.tags | Where-Object { $_.key -eq "error" -and $_.value -eq $true } } }
        Write-Output "  $svc : $($r.data.Count) traces | errors=$($errors.Count)"
        if ($r.data.Count -gt 0) {
            $latest = [DateTimeOffset]::FromUnixTimeMilliseconds($r.data[0].spans[0].startTime / 1000).ToString("HH:mm:ss")
            Write-Output "    Latest trace: $latest UTC"
        }
    } catch {
        Write-Output "  $svc : Jaeger tunnel not open — $($_.Exception.Message)"
    }
}

# --- 7. DEPLOY HISTORY (khi nao deploy cuoi?) ---
Write-Output "`n[7] Deployment rollout history..."
foreach ($d in @("checkout", "payment", "cart", "frontend-proxy")) {
    $age = kubectl -n techx-tf4 get deploy $d -o jsonpath="{.metadata.creationTimestamp}" 2>&1
    $ready = kubectl -n techx-tf4 get deploy $d -o jsonpath="{.status.readyReplicas}/{.status.replicas}" 2>&1
    Write-Output "  $d : ready=$ready"
}

Write-Output "`n============================================"
Write-Output "INCIDENT QUERY DONE — $(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')"
Write-Output "============================================"
