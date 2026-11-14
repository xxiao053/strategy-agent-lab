param([ValidateSet('start','stop','restart')][string]$Action='start')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw 'Docker command failed. Start Docker Desktop with Linux containers, then retry. Data volumes were not removed.' }
}
Push-Location -LiteralPath $projectRoot
try {
    Invoke-Docker info --format '{{.OSType}}'
    if ($Action -eq 'stop') { Invoke-Docker compose stop; return }
    if ($Action -eq 'restart') { Invoke-Docker compose restart controller }
    else {
        Invoke-Docker compose build worker controller
        Invoke-Docker compose up -d --wait --wait-timeout 90 controller
    }
    Write-Output 'Open http://127.0.0.1:8765. Stop: .\scripts\start-docker.cmd stop. Restart: .\scripts\start-docker.cmd restart. Data is preserved.'
} finally { Pop-Location }
