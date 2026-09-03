[CmdletBinding()]
param([switch]$Gpu)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runtime = Join-Path $root ".ugas\runtime"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
Push-Location $root
try {
    $env:UGAS_REPO_PATH = $root
    $env:UGAS_RUNTIME_PATH = $runtime
    $env:UGAS_DASHBOARD_PORT = if ($env:UGAS_DASHBOARD_PORT) { $env:UGAS_DASHBOARD_PORT } else { "8765" }

    & docker compose -f compose.yaml build dashboard
    if ($LASTEXITCODE -ne 0) { throw "DASHBOARD_BUILD_FAILED" }

    $gpuOutput = & docker run --rm --gpus all --entrypoint nvidia-smi ugas-dashboard:0.13.0 --query-gpu=name --format=csv,noheader 2>&1
    $gpuAvailable = ($LASTEXITCODE -eq 0 -and [bool](($gpuOutput -join "").Trim()))
    $composeFiles = @("-f", "compose.yaml")
    if ($gpuAvailable) { $composeFiles += @("-f", "compose.gpu.yaml") }

    & docker compose @composeFiles up -d
    if ($LASTEXITCODE -ne 0) { throw "DASHBOARD_START_FAILED" }
    $container = docker inspect ugas-dashboard --format '{{.Id}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}'
    [pscustomobject]@{
        status = "DASHBOARD_STARTED"
        url = "http://127.0.0.1:$($env:UGAS_DASHBOARD_PORT)/"
        container = $container.Trim()
        gpu_runtime = if ($gpuAvailable) { "AVAILABLE" } else { "GPU_CONTAINER_RUNTIME_GAP" }
        gpu_reason = if ($gpuAvailable) { $null } else { "Docker NVIDIA passthrough did not return a usable nvidia-smi result" }
        restart_policy = "unless-stopped"
    } | ConvertTo-Json -Compress
}
finally { Pop-Location }
