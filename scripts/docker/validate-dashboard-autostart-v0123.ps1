[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$installer = Join-Path $root "scripts\docker\install-dashboard-autostart.ps1"
$uninstaller = Join-Path $root "scripts\docker\uninstall-dashboard-autostart.ps1"
$startup = [Environment]::GetFolderPath("Startup")
$fallbackPath = Join-Path $startup "UGAS-Dashboard-AlwaysOn.cmd"
$taskName = "UGAS-Dashboard-AlwaysOn"
$powershell = (Get-Command powershell.exe).Source

function Invoke-UgasScript([string]$path) {
    $text = (& $powershell -NoProfile -ExecutionPolicy Bypass -File $path 2>&1 | Out-String).Trim()
    $code = $LASTEXITCODE
    $json = $null
    try { $json = $text | ConvertFrom-Json } catch { }
    return [pscustomobject]@{ exit_code = $code; output = $text; parsed = $json }
}

function Get-UgasTask {
    if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) { return Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue }
    return $null
}

$first = Invoke-UgasScript $installer
$second = Invoke-UgasScript $installer
$taskAfterInstall = Get-UgasTask
$fallbackAfterInstall = Test-Path -LiteralPath $fallbackPath
$entriesAfterInstall = @()
if ($taskAfterInstall) { $entriesAfterInstall += "TASK_SCHEDULER_PER_USER" }
if ($fallbackAfterInstall) { $entriesAfterInstall += "SIGNED_IN_USER_STARTUP" }

$uninstall = Invoke-UgasScript $uninstaller
$taskAfterUninstall = Get-UgasTask
$fallbackAfterUninstall = Test-Path -LiteralPath $fallbackPath
$reinstall = Invoke-UgasScript $installer
$taskFinal = Get-UgasTask
$fallbackFinal = Test-Path -LiteralPath $fallbackPath

$container = try { docker inspect ugas-dashboard --format '{{json .}}' | ConvertFrom-Json } catch { $null }
$apiStatus = try { Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/status" -TimeoutSec 4 } catch { $null }
$apiHealth = try { Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 4 } catch { $null }
$finalEntries = @()
if ($taskFinal) { $finalEntries += "TASK_SCHEDULER_PER_USER" }
if ($fallbackFinal) { $finalEntries += "SIGNED_IN_USER_STARTUP" }
$result = [ordered]@{
    schema_version = "0.12.3"
    installer = "scripts/docker/install-dashboard-autostart.ps1"
    task_name = $taskName
    fallback_name = "UGAS-Dashboard-AlwaysOn.cmd"
    fallback_path_is_user_startup = [bool]($startup -and $fallbackPath.StartsWith($startup, [StringComparison]::OrdinalIgnoreCase))
    first_install = $first
    second_install = $second
    idempotent = $entriesAfterInstall.Count -eq 1 -and $second.parsed.status -in @("AUTOSTART_INSTALLED", "AUTOSTART_INSTALLED_FALLBACK")
    entries_after_two_installs = $entriesAfterInstall
    uninstall = $uninstall
    uninstall_removed_only_ugas_entry = (-not $taskAfterUninstall -and -not $fallbackAfterUninstall)
    reinstall = $reinstall
    final_entries = $finalEntries
    final_one_logical_entry = $finalEntries.Count -eq 1
    current_online_state = [ordered]@{ container_id = if ($container) { $container.Id } else { $null }; container_status = if ($container) { $container.State.Status } else { $null }; container_health = if ($container -and $container.State.Health) { $container.State.Health.Status } else { $null }; url = "http://127.0.0.1:8765/"; api_status = $apiStatus; api_health = $apiHealth }
    uninstall_scope = "only UGAS-Dashboard-AlwaysOn task and UGAS-Dashboard-AlwaysOn.cmd; Docker Desktop startup and unrelated tasks untouched"
}
$output = Join-Path $root "docs\evidence\github-review-v0123\autostart-v0123.json"
[System.IO.File]::WriteAllText($output, ($result | ConvertTo-Json -Depth 12))
$result | ConvertTo-Json -Depth 12
if (-not $result.idempotent -or -not $result.uninstall_removed_only_ugas_entry -or -not $result.final_one_logical_entry) { exit 1 }
