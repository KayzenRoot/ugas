[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "UGAS-Dashboard-AlwaysOn"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ensure = Join-Path $root "scripts\docker\ensure-dashboard-online.ps1"
$startup = [Environment]::GetFolderPath("Startup")
$fallbackName = "UGAS-Dashboard-AlwaysOn.cmd"
$fallback = Join-Path $startup $fallbackName
$shell = if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) { (Get-Command pwsh.exe).Source } else { (Get-Command powershell.exe).Source }

if (-not $startup -or -not (Test-Path -LiteralPath $ensure)) {
    [pscustomobject]@{ status = "AUTOSTART_INSTALL_GAP"; task = $taskName; reason = "UGAS ensure script or signed-in user Startup folder is unavailable"; remediation = "Restore the canonical repository path and rerun the installer." } | ConvertTo-Json -Compress
    exit 2
}

$fallbackContent = "@echo off`r`n`"$shell`" -NoProfile -ExecutionPolicy Bypass -File `"$ensure`" -RepositoryPath `"$root`" -EngineTimeoutSeconds 90`r`n"
$taskError = $null
try {
    # A successful task install is the preferred single logical entry. Remove
    # only the fallback previously created by UGAS so two entries cannot grow.
    $action = New-ScheduledTaskAction -Execute $shell -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ensure`" -RepositoryPath `"$root`" -EngineTimeoutSeconds 90"
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Keep the local UGAS Docker observability dashboard online." -Force | Out-Null
    if (Test-Path -LiteralPath $fallback) { Remove-Item -LiteralPath $fallback -Force }
    [pscustomobject]@{ status = "AUTOSTART_INSTALLED"; method = "TASK_SCHEDULER_PER_USER"; task = $taskName; fallback = $null; command = $ensure; scope = "UGAS task only" } | ConvertTo-Json -Compress
}
catch {
    $taskError = $_.Exception.Message
    try {
        # This is a non-admin, signed-in-user fallback. It invokes the same
        # canonical ensure script and owns exactly one deterministic filename.
        [System.IO.File]::WriteAllText($fallback, $fallbackContent)
        [pscustomobject]@{ status = "AUTOSTART_INSTALLED_FALLBACK"; method = "SIGNED_IN_USER_STARTUP"; task = $taskName; fallback = $fallbackName; command = $ensure; repository_path = $root; task_scheduler_error = $taskError; uninstall_target = $fallbackName; scope = "UGAS Startup entry only" } | ConvertTo-Json -Compress
    }
    catch {
        [pscustomobject]@{ status = "AUTOSTART_INSTALL_GAP"; task = $taskName; reason = $_.Exception.Message; task_scheduler_error = $taskError; remediation = "Allow the per-user Task Scheduler route or make the signed-in user Startup folder writable, then rerun the installer." } | ConvertTo-Json -Compress
        exit 2
    }
}
