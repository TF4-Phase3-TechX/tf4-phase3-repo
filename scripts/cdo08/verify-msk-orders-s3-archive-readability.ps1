param(
    [string]$Bucket = "tf4-msk-orders-archive-511825856493-us-east-1",
    [string[]]$Keys,
    [string]$Profile = "tf4",
    [string]$Region = "us-east-1",
    [string]$OutDir = (Join-Path $env:TEMP "rel22-msk-archive-readability")
)

if (-not $Keys -or $Keys.Count -eq 0) {
    throw "Pass one or more S3 object keys through -Keys."
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$records = foreach ($key in $Keys) {
    $fileName = [IO.Path]::GetFileName($key)
    $filePath = Join-Path $OutDir $fileName
    aws s3 cp "s3://$Bucket/$key" $filePath --profile $Profile --region $Region --no-progress | Out-Null

    $bytes = [IO.File]::ReadAllBytes($filePath)
    $text = [Text.Encoding]::UTF8.GetString($bytes)
    $parsed = $null
    $parseError = $null

    try {
        $parsed = $text | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        $parseError = $_.Exception.Message
    }

    [PSCustomObject]@{
        Key = $key
        Bytes = $bytes.Length
        MarkerId = if ($parsed) { $parsed.marker_id } else { $null }
        OrderId = if ($parsed) { $parsed.order_id } else { $null }
        Source = if ($parsed) { $parsed.source } else { $null }
        CreatedAt = if ($parsed) { $parsed.created_at } else { $null }
        Parsed = [bool]$parsed
        ParseError = $parseError
        Utf8ReplacementCharPresent = $text.Contains([char]0xFFFD)
    }
}

$records | Format-Table -AutoSize

$summary = [PSCustomObject]@{
    ProducedMarkers = $Keys.Count
    ArchivedObjects = $records.Count
    ParsedObjects = @($records | Where-Object { $_.Parsed }).Count
    MissingMarkers = @($records | Where-Object { -not $_.OrderId }).Count
    DuplicateOrderIds = @($records | Group-Object OrderId | Where-Object { $_.Name -and $_.Count -gt 1 }).Count
    Utf8ReplacementObjects = @($records | Where-Object { $_.Utf8ReplacementCharPresent }).Count
}

""
"Summary"
$summary | Format-List
