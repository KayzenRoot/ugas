[CmdletBinding()]
param([int]$Tail = 200, [switch]$Follow)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $root
try {
    $args = @("compose", "-f", "compose.yaml", "logs", "--tail", $Tail.ToString())
    if ($Follow) { $args += "--follow" }
    & docker @args
    exit $LASTEXITCODE
}
finally { Pop-Location }
