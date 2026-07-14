# Task 23 - ST-3.1 + ST-3.2 before
# Run: .\run-st31-st32.ps1

$ALB = "http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"
$dir = $PSScriptRoot

# ---- ST-3.1 ----
Write-Host "Running ST-3.1..."
$ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

$ip = "UNKNOWN"
foreach ($src in @("https://checkip.amazonaws.com","https://api.ipify.org","https://icanhazip.com")) {
    try {
        $ip = (New-Object System.Net.WebClient).DownloadString($src).Trim()
        break
    } catch {}
}

$curlInfo = "PowerShell Invoke-WebRequest"
$c = Get-Command curl.exe -ErrorAction SilentlyContinue
if ($c) { $curlInfo = (& curl.exe --version | Select-Object -First 1) }

$st31 = "ST-3.1 - Environment Setup`r`n"
$st31 += "Timestamp : $ts`r`n"
$st31 += "Public IP : $ip`r`n"
$st31 += "Tool      : $curlInfo`r`n"
$st31 += "Shell     : PowerShell $($PSVersionTable.PSVersion) on Windows`r`n"
$st31 += "Network   : External - not VPN, not kubectl port-forward`r`n"

[System.IO.File]::WriteAllText("$dir\st31-env-setup.txt", $st31, [System.Text.Encoding]::ASCII)
Write-Host "  Done -> st31-env-setup.txt"
Write-Host "  Timestamp : $ts"
Write-Host "  Public IP : $ip"

# ---- ST-3.2 before ----
Write-Host ""
Write-Host "Running ST-3.2 before..."
$ts2 = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$ip2 = $ip

$out = "ST-3.2 BEFORE - External curl test (baseline, before CDO08 deploy)`r`n"
$out += "Timestamp : $ts2`r`n"
$out += "From IP   : $ip2`r`n"
$out += "ALB       : $ALB`r`n"
$out += "`r`n"

$paths = @(
    @("",            "GET /            "),
    @("grafana/",    "GET /grafana/    "),
    @("grafana",     "GET /grafana     "),
    @("jaeger/ui/",  "GET /jaeger/ui/  "),
    @("jaeger/",     "GET /jaeger/     "),
    @("loadgen/",    "GET /loadgen/    "),
    @("feature",     "GET /feature     "),
    @("flagservice/","GET /flagservice/"),
    @("otlp-http/",  "GET /otlp-http/  ")
)

$exposed = 0
foreach ($p in $paths) {
    $url = "$ALB/$($p[0])"
    $code = "ERR"
    try {
        $r = Invoke-WebRequest -Uri $url -Method GET -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction SilentlyContinue
        $code = $r.StatusCode
    } catch {
        try { $code = [int]$_.Exception.Response.StatusCode } catch { $code = "ERR" }
    }

    $note = ""
    if ([string]$code -eq "200" -and $p[0] -ne "") { $note = "EXPOSED - needs CDO08 block"; $exposed++ }
    elseif ([string]$code -eq "200") { $note = "OK - storefront public" }
    elseif ([string]$code -eq "404" -or [string]$code -eq "403") { $note = "BLOCKED" }

    $line = "$($p[1])-> HTTP $code   $note"
    $out += "$line`r`n"
    Write-Host "  $line"
}

$out += "`r`n"
$out += "Exposed routes : $exposed (HTTP 200 from external internet)`r`n"
$out += "Action needed  : CDO08 must deploy SEC-05 to block exposed routes`r`n"

[System.IO.File]::WriteAllText("$dir\st32-curl-before.txt", $out, [System.Text.Encoding]::ASCII)
Write-Host ""
Write-Host "  Done -> st32-curl-before.txt"
Write-Host "  Exposed routes: $exposed"
Write-Host ""
Write-Host "DONE. Check files:"
Write-Host "  $dir\st31-env-setup.txt"
Write-Host "  $dir\st32-curl-before.txt"
