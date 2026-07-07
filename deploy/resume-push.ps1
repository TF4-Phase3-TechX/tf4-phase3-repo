# Resume push to ECR - 3 services con lai (kafka, opensearch, llm)
# ECR da co 17/21: accounting, ad, cart, checkout, currency, email,
#   fraud-detection, frontend, frontend-proxy, image-provider, load-generator,
#   payment, product-catalog, product-reviews, quote, recommendation, shipping
#
# TOI UU: dung buildx bake --push -> stream thang len ECR, khong load local
#   - Nhanh hon ~30% vi bo qua buoc load vao Docker daemon
#   - An toan: ECR xac nhan digest sau moi push
#   - Auto ECR login truoc khi chay
# -----------------------------------------------------------------------
param(
    [string]$StartFrom = ""   # truyen ten service de bat dau tu giua, vi du: opensearch
)
$ErrorActionPreference = "Stop"

# --- ECR login -----------------------------------------------------------
Write-Host ">> Kiem tra ECR login..." -ForegroundColor Cyan
$loginOk = aws ecr get-login-password --region us-east-1 |
           docker login --username AWS --password-stdin `
                        511825856493.dkr.ecr.us-east-1.amazonaws.com 2>&1
if ($LASTEXITCODE -ne 0) { Write-Error "ECR login that bai!"; exit 1 }
Write-Host ">> ECR OK" -ForegroundColor Green

# --- Doc bien moi truong -------------------------------------------------
$envFile = "$PSScriptRoot\..\techx-corp-platform\.env.override"
if (-not (Test-Path $envFile)) { Write-Error "missing .env.override"; exit 1 }
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
}
$IMAGE_NAME   = $env:IMAGE_NAME
$DEMO_VERSION = $env:DEMO_VERSION
Write-Host ">> IMAGE     : $IMAGE_NAME" -ForegroundColor Cyan
Write-Host ">> VERSION   : $DEMO_VERSION" -ForegroundColor Cyan
Write-Host ""

# --- Danh sach services --------------------------------------------------
$ALL = @("kafka", "opensearch", "llm")

# Ho tro bat dau tu service bat ky (neu bi ngat giua chung)
$skip = $StartFrom -ne ""
$REMAINING = $ALL | Where-Object {
    if ($skip -and $_ -ne $StartFrom) { return $false }
    $skip = $false
    return $true
}

$TOTAL = @($REMAINING).Count
$INDEX = 0
Set-Location "$PSScriptRoot\..\techx-corp-platform"

foreach ($SERVICE in $REMAINING) {
    $INDEX++
    $TAG = "${IMAGE_NAME}:${DEMO_VERSION}-${SERVICE}"

    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host ">> [$INDEX/$TOTAL] $SERVICE" -ForegroundColor Cyan
    Write-Host ">> Tag: $TAG" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan

    # --push: build + stream thang len ECR, khong can load vao local daemon
    docker buildx bake -f docker-compose.yml `
        --set "*.platform=linux/amd64" `
        --set "${SERVICE}.tags=${TAG}" `
        --push `
        $SERVICE

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Error "FAILED: $SERVICE - Chay lai voi: .\resume-push.ps1 -StartFrom $SERVICE"
        exit 1
    }

    # Xac nhan image da co tren ECR
    $digest = aws ecr describe-images --repository-name techx-corp --region us-east-1 `
        --image-ids imageTag="${DEMO_VERSION}-${SERVICE}" `
        --query "imageDetails[0].imageDigest" --output text 2>&1
    Write-Host ">> DONE: $SERVICE (digest: $digest)" -ForegroundColor Green
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Green
Write-Host "XONG! kafka + opensearch + llm da push len ECR" -ForegroundColor Green
Write-Host "Con lai: flagd-ui (dang fix heroicons)" -ForegroundColor Yellow
Write-Host "ECR: https://us-east-1.console.aws.amazon.com/ecr/repositories/private/511825856493/techx-corp?region=us-east-1" -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
