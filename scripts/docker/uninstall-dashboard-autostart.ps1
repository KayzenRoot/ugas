[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "UGAS-Dashboard-AlwaysOn"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$startup = [Environment]::GetFolderPath("Startup")
$fallback = Join-Path $startup "UGAS-Dashboard-AlwaysOn.cmd"
$taskRemoved = $false
$fallbackRemoved = $false
try {
    if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($task) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false; $taskRemoved = $true }
    }
} catch { throw "UGAS task uninstall failed: $($_.Exception.Message)" }
if ($startup -and (Test-Path -LiteralPath $fallback)) { Remove-Item -LiteralPath $fallback -Force; $fallbackRemoved = $true }
$status = if ($taskRemoved -or $fallbackRemoved) { "AUTOSTART_UNINSTALLED" } else { "AUTOSTART_NOT_FOUND" }
[pscustomobject]@{ status = $status; task = $taskName; task_removed = $taskRemoved; fallback = "UGAS-Dashboard-AlwaysOn.cmd"; fallback_removed = $fallbackRemoved; repository_path = $root; scope = "only UGAS-created task and exact UGAS Startup entry; Docker Desktop and unrelated tasks untouched" } | ConvertTo-Json -Compress
