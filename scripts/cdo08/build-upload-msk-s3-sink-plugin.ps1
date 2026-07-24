param(
    [Parameter(Mandatory = $true)]
    [string] $Bucket,

    [string] $Region = "us-east-1",
    [string] $Profile = "tf4",
    [string] $ConnectorVersion = "12.1.0",
    [string] $ConfigProviderVersion = "0.4.0",
    [string] $WorkDir = ".tmp/msk-connect-s3-sink-plugin"
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string] $Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

Require-Command "aws"

$workRoot = Resolve-Path -Path (New-Item -ItemType Directory -Force -Path $WorkDir)
$downloadDir = Join-Path $workRoot "downloads"
$extractDir = Join-Path $workRoot "extract"
$bundleDir = Join-Path $workRoot "custom-plugin"
$outputDir = Join-Path $workRoot "dist"

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $downloadDir, $extractDir, $bundleDir, $outputDir
New-Item -ItemType Directory -Force -Path $downloadDir, $extractDir, $bundleDir, $outputDir | Out-Null

$s3SinkArchive = Join-Path $downloadDir "confluentinc-kafka-connect-s3-$ConnectorVersion.zip"
$configProviderArchive = Join-Path $downloadDir "msk-config-providers-$ConfigProviderVersion-with-dependencies.zip"
$pluginZip = Join-Path $outputDir "confluent-s3-sink-msk-config-provider-$ConfigProviderVersion.zip"

$s3SinkUrl = "https://api.hub.confluent.io/api/plugins/confluentinc/kafka-connect-s3/versions/$ConnectorVersion/archive"
$configProviderUrl = "https://github.com/aws-samples/msk-config-providers/releases/download/r$ConfigProviderVersion/msk-config-providers-$ConfigProviderVersion-with-dependencies.zip"

Write-Host "[INFO] Downloading Confluent S3 Sink connector $ConnectorVersion"
Invoke-WebRequest -Uri $s3SinkUrl -OutFile $s3SinkArchive

Write-Host "[INFO] Downloading AWS MSK config providers $ConfigProviderVersion"
Invoke-WebRequest -Uri $configProviderUrl -OutFile $configProviderArchive

Write-Host "[INFO] Extracting connector bundle"
Expand-Archive -Path $s3SinkArchive -DestinationPath (Join-Path $extractDir "s3-sink") -Force
Expand-Archive -Path $configProviderArchive -DestinationPath (Join-Path $extractDir "msk-config-providers") -Force

$s3SinkRoot = Get-ChildItem -Path (Join-Path $extractDir "s3-sink") -Directory | Select-Object -First 1
if (-not $s3SinkRoot) {
    throw "Could not locate extracted Confluent S3 Sink connector directory."
}

Copy-Item -Recurse -Path $s3SinkRoot.FullName -Destination (Join-Path $bundleDir $s3SinkRoot.Name)
Copy-Item -Recurse -Path (Join-Path $extractDir "msk-config-providers") -Destination (Join-Path $bundleDir "msk-config-providers")

Write-Host "[INFO] Creating MSK Connect custom plugin ZIP"
Compress-Archive -Path (Join-Path $bundleDir "*") -DestinationPath $pluginZip -Force

$sha256 = (Get-FileHash -Algorithm SHA256 -Path $pluginZip).Hash.ToLowerInvariant()
$key = "plugins/confluent-s3-sink/$ConnectorVersion/confluent-s3-sink-msk-config-provider-$ConfigProviderVersion.zip"

Write-Host "[INFO] Uploading plugin ZIP to s3://$Bucket/$key"
$putResult = aws s3api put-object `
    --bucket $Bucket `
    --key $key `
    --body $pluginZip `
    --server-side-encryption AES256 `
    --metadata "connector-version=$ConnectorVersion,config-provider-version=$ConfigProviderVersion,sha256=$sha256" `
    --region $Region `
    --profile $Profile `
    --output json | ConvertFrom-Json

$result = [ordered]@{
    Bucket                = $Bucket
    Key                   = $key
    VersionId             = $putResult.VersionId
    ConnectorVersion      = $ConnectorVersion
    ConfigProviderVersion = $ConfigProviderVersion
    Sha256                = $sha256
    LocalZip              = (Resolve-Path $pluginZip).Path
}

Write-Host "[OK] Plugin artifact uploaded"
$result | ConvertTo-Json -Depth 3
