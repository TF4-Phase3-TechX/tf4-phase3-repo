# CDO08-REL-23 Subtask 4 - Validation checklist (§4.4/§7.1): row counts, quan he 1:1/1:N, orphan check,
# tong tien. Dung chung duoc cho ca drill (-DbInstanceIdentifier isolated -Database otel_drill) lan
# production that (-DbInstanceIdentifier techx-tf4-postgresql -Database otel, mac dinh) - tranh trung
# logic. Neu truyen -ExpectedOrderCount/-ExpectedOrderItemCount/-ExpectedShippingCount se doi chieu
# tuyet doi voi baseline; khong truyen thi chi in ra de doi chieu tay.
#
# Vi du (drill):
#   .\07-validate-production.ps1 -DbInstanceIdentifier rel23-accounting-pitr-... -Database otel_drill
# Vi du (production, sau R.2):
#   .\07-validate-production.ps1 -ExpectedOrderCount 205891 -ExpectedOrderItemCount 377846 -ExpectedShippingCount 205891

param(
    [string]$DbInstanceIdentifier = 'techx-tf4-postgresql',
    [string]$Database = 'otel',
    [string]$Region = 'us-east-1',
    [string]$OpsNamespace = 'rel23-ops',
    [Nullable[int]]$ExpectedOrderCount = $null,
    [Nullable[int]]$ExpectedOrderItemCount = $null,
    [Nullable[int]]$ExpectedShippingCount = $null
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

$runId = New-RunId
$podName = "pg-validate-$runId"
$creds = Get-RdsMasterCreds -DbInstanceIdentifier $DbInstanceIdentifier -Region $Region
$pod = New-PgClientPod -Namespace $OpsNamespace -PodName $podName `
    -PgHost $creds.Host -PgPort $creds.Port -PgUser $creds.User -PgPassword $creds.Password -PgDatabase $Database

$failed = @()

try {
    $orderCount     = [int](Invoke-PgSqlScalar -Namespace $pod.Namespace -PodName $pod.PodName -Sql 'SELECT count(*) FROM accounting."order";')
    $orderItemCount = [int](Invoke-PgSqlScalar -Namespace $pod.Namespace -PodName $pod.PodName -Sql 'SELECT count(*) FROM accounting.orderitem;')
    $shippingCount  = [int](Invoke-PgSqlScalar -Namespace $pod.Namespace -PodName $pod.PodName -Sql 'SELECT count(*) FROM accounting.shipping;')
    $orphanItem     = [int](Invoke-PgSqlScalar -Namespace $pod.Namespace -PodName $pod.PodName -Sql @'
SELECT count(*) FROM accounting.orderitem oi LEFT JOIN accounting."order" o ON oi.order_id = o.order_id WHERE o.order_id IS NULL;
'@)
    $orphanShipping = [int](Invoke-PgSqlScalar -Namespace $pod.Namespace -PodName $pod.PodName -Sql @'
SELECT count(*) FROM accounting.shipping s LEFT JOIN accounting."order" o ON s.order_id = o.order_id WHERE o.order_id IS NULL;
'@)
    $totalUnits = Invoke-PgSqlScalar -Namespace $pod.Namespace -PodName $pod.PodName -Sql 'SELECT coalesce(sum(item_cost_units),0) FROM accounting.orderitem;'
    $totalNanos = Invoke-PgSqlScalar -Namespace $pod.Namespace -PodName $pod.PodName -Sql 'SELECT coalesce(sum(item_cost_nanos),0) FROM accounting.orderitem;'

    Write-Host "[RESULT] order_count      = $orderCount"
    Write-Host "[RESULT] orderitem_count  = $orderItemCount"
    Write-Host "[RESULT] shipping_count   = $shippingCount"
    Write-Host "[RESULT] orphan orderitem = $orphanItem"
    Write-Host "[RESULT] orphan shipping  = $orphanShipping"
    Write-Host "[RESULT] sum item_cost_units = $totalUnits"
    Write-Host "[RESULT] sum item_cost_nanos = $totalNanos"

    # #2: shipping_count == order_count (quan he 1:1)
    if ($shippingCount -ne $orderCount) { $failed += "shipping_count($shippingCount) != order_count($orderCount) - vi pham quan he 1:1" }
    # #3: orderitem_count >= order_count
    if ($orderItemCount -lt $orderCount) { $failed += "orderitem_count($orderItemCount) < order_count($orderCount) - vi pham quan he 1:N toi thieu" }
    # #4/#5: orphan check phai = 0
    if ($orphanItem -ne 0) { $failed += "orphan orderitem = $orphanItem (ky vong 0)" }
    if ($orphanShipping -ne 0) { $failed += "orphan shipping = $orphanShipping (ky vong 0)" }

    if ($null -ne $ExpectedOrderCount -and $orderCount -ne $ExpectedOrderCount) {
        $failed += "order_count($orderCount) != ExpectedOrderCount($ExpectedOrderCount)"
    }
    if ($null -ne $ExpectedOrderItemCount -and $orderItemCount -ne $ExpectedOrderItemCount) {
        $failed += "orderitem_count($orderItemCount) != ExpectedOrderItemCount($ExpectedOrderItemCount)"
    }
    if ($null -ne $ExpectedShippingCount -and $shippingCount -ne $ExpectedShippingCount) {
        $failed += "shipping_count($shippingCount) != ExpectedShippingCount($ExpectedShippingCount)"
    }
}
finally {
    Remove-PgClientPod -Namespace $pod.Namespace -PodName $pod.PodName
}

if ($failed.Count -gt 0) {
    Write-Host '[FAIL] Validation khong dat:'
    foreach ($f in $failed) { Write-Host "  - $f" }
    Write-Host '[NOTE] Neu day la production sau R.2 va nguyen nhan la "thieu order trong rollback window": KHONG tu dong rollback - xem nhanh remediation §7.2.1 (xac nhan da chay R.1b + doi consumer lag ve 0 sau 08-reopen-traffic.ps1 roi validate lai) truoc khi chay rollback-01-restore-old-schema.ps1.'
    exit 1
}

Write-Host '[OK] Validation PASS.'
Write-Host '[NOTE] PASS o day chi chung minh noi bo (khong orphan, dung quan he) - KHONG chung minh du du lieu tuyet doi (schema khong co cot timestamp). Nguon chan ly ve tinh day du la Kafka - xem plan §7.1/§7.2.1.'
