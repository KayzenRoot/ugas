[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $root
try {
    & docker compose -f compose.yaml down
    if ($LASTEXITCODE -ne 0) { throw "DASHBOARD_STOP_FAILED" }
    '{"status":"DASHBOARD_STOPPED","removed_scope":"ugas-dashboard compose service only"}'
}
finally { Pop-Location }
