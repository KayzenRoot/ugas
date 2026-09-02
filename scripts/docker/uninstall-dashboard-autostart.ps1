[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "UGAS-Dashboard-AlwaysOn"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    '{"status":"AUTOSTART_UNINSTALLED","task":"UGAS-Dashboard-AlwaysOn","scope":"task only"}'
} else {
    '{"status":"AUTOSTART_NOT_FOUND","task":"UGAS-Dashboard-AlwaysOn","scope":"no other task or Docker service touched"}'
}
