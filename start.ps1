param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [switch]$Build,
    [ValidateRange(1, 120)][int]$StartupTimeoutSeconds = 30
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$serverPath = Join-Path $projectRoot 'scripts\start-local.py'
$url = "http://127.0.0.1:$Port"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Project environment is missing. Run bootstrap.ps1 once.'
}
if (-not (Test-Path -LiteralPath $serverPath)) {
    throw 'Local server helper is missing: scripts\start-local.py.'
}

function Get-LocalListener {
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Assert-ProjectListener($Listeners) {
    $owners = @($Listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -ne 1) {
        throw "Port $Port is occupied; no process was stopped."
    }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($owners[0])"
    $helperPattern = [regex]::Escape($serverPath)
    if (-not $owner -or $owner.CommandLine -notmatch $helperPattern -or
        $owner.CommandLine -notmatch "--port\s+$Port(?:\s|$)") {
        throw "Port $Port is occupied by another process (PID $($owners[0])); no process was stopped."
    }
    return $owners[0]
}

function Test-LocalReady {
    try {
        $bootstrap = Invoke-RestMethod -Uri "$url/api/bootstrap" -TimeoutSec 2
        if ($bootstrap.local_only -ne $true) { return $false }
        $page = Invoke-WebRequest -UseBasicParsing -Uri "$url/" -TimeoutSec 2
        return $page.StatusCode -eq 200 -and $page.Headers['Content-Type'] -like 'text/html*'
    } catch { return $false }
}

$existing = @(Get-LocalListener)
if ($existing.Count -gt 0) { $serverPid = Assert-ProjectListener $existing }
if ($Build -or -not (Test-Path -LiteralPath (Join-Path $projectRoot 'web\dist\index.html'))) {
    Push-Location (Join-Path $projectRoot 'web')
    try {
        & pnpm build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed; server not started.' }
    } finally { Pop-Location }
}

if ($existing.Count -eq 0) {
    $logDirectory = Join-Path $projectRoot 'logs'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-ffff'
    $outputLog = Join-Path $logDirectory "local-$Port-$stamp.stdout.log"
    $errorLog = Join-Path $logDirectory "local-$Port-$stamp.stderr.log"
    $launched = Start-Process -FilePath $pythonPath -ArgumentList @(
        '-u', "`"$serverPath`"", '--port', "$Port",
        '--stdout-log', "`"$outputLog`"", '--stderr-log', "`"$errorLog`""
    ) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
}

$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
do {
    $listeners = @(Get-LocalListener)
    if ($listeners.Count -gt 0) {
        $serverPid = Assert-ProjectListener $listeners
        if (Test-LocalReady) {
            $status = if ($existing.Count -gt 0) { 'Already running' } else { 'Ready in background' }
            Write-Host "$status`: $url (PID $serverPid)"
            if ($errorLog) { Write-Host "Server log: $errorLog" }
            Write-Host 'Local only; no publication or paid API calls at startup.'
            return
        }
    }
    if ($launched -and $launched.HasExited -and $listeners.Count -eq 0) {
        throw "Local server exited before readiness. Inspect $errorLog"
    }
    Start-Sleep -Milliseconds 200
} while ((Get-Date) -lt $deadline)

$diagnostic = if ($errorLog) { "Inspect $errorLog" } else { "Existing PID $serverPid did not become ready." }
throw "Local server was not ready within $StartupTimeoutSeconds seconds. $diagnostic No process was stopped."
