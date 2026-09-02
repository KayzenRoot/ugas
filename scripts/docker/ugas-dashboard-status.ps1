[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $root
try {
    $container = docker inspect ugas-dashboard 2>$null | ConvertFrom-Json
    if (-not $container) {
        '{"status":"DASHBOARD_NOT_FOUND","url":"http://127.0.0.1:8765/"}'
        exit 1
    }
    $state = $container[0].State
    $health = if ($state.Health) { $state.Health.Status } else { "no-health" }
    $status = try { Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/status" -TimeoutSec 4 } catch { $null }
    $healthApi = try { Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 4 } catch { $null }
    [pscustomobject]@{
        status = if ($state.Status -eq "running" -and $health -in @("healthy", "no-health")) { "DASHBOARD_RUNNING" } else { "DASHBOARD_DEGRADED" }
        container_id = $container[0].Id
        container_status = $state.Status
        container_health = $health
        started_at = $state.StartedAt
        url = "http://127.0.0.1:8765/"
        api_status = $status
        api_health = $healthApi
    } | ConvertTo-Json -Depth 8
}
finally { Pop-Location }
