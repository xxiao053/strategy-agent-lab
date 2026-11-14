param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
    }
    & .\.venv\Scripts\python.exe -m pip install -e '.[test]'
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    Push-Location web
    try {
        & pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Web dependency installation failed.' }
        & pnpm build
        if ($LASTEXITCODE -ne 0) { throw 'Web build failed.' }
    } finally { Pop-Location }
    Write-Host 'Ready. Run .\start.ps1. No paid API calls were made.'
} finally { Pop-Location }
