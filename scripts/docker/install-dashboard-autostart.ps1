[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "UGAS-Dashboard-AlwaysOn"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ensure = Join-Path $root "scripts\docker\ensure-dashboard-online.ps1"
try {
    $action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ensure`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Keep the local UGAS Docker observability dashboard online." -Force | Out-Null
    [pscustomobject]@{ status = "AUTOSTART_INSTALLED"; task = $taskName; command = $ensure } | ConvertTo-Json -Compress
}
catch {
    [pscustomobject]@{ status = "AUTOSTART_INSTALL_GAP"; task = $taskName; reason = $_.Exception.Message; remediation = "Run this script as the signed-in user and allow per-user Task Scheduler registration." } | ConvertTo-Json -Compress
    exit 2
}
