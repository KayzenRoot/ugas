[CmdletBinding()]
param(
    [int]$EngineTimeoutSeconds = 90,
    [string]$RepositoryPath = ""
)

$ErrorActionPreference = "Stop"
$root = if ($RepositoryPath) { (Resolve-Path -LiteralPath $RepositoryPath).Path } else { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { '{"status":"DOCKER_ENGINE_GAP","reason":"docker executable not found"}'; exit 2 }

$deadline = (Get-Date).AddSeconds($EngineTimeoutSeconds)
$engineReady = $false
do {
    & docker info *> $null
    if ($LASTEXITCODE -eq 0) { $engineReady = $true; break }
    $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path -LiteralPath $desktop) { Start-Process -FilePath $desktop -WindowStyle Hidden }
    Start-Sleep -Seconds 3
} while ((Get-Date) -lt $deadline)

if (-not $engineReady) {
    '{"status":"DOCKER_ENGINE_GAP","reason":"Docker Engine did not become ready within the bounded wait"}'
    exit 2
}
& (Join-Path $root "scripts\docker\ugas-dashboard-up.ps1")
exit $LASTEXITCODE
