param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$NoReload,
    [switch]$Https,
    [switch]$ReplacePort
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot "venv\Scripts\python.exe"
$managePath = Join-Path $projectRoot "manage.py"

if (-not (Test-Path $pythonPath)) {
    Write-Error "Python virtual environment was not found at: $pythonPath"
}

if (-not (Test-Path $managePath)) {
    Write-Error "manage.py was not found at: $managePath"
}

Set-Location $projectRoot

function Get-ListeningProcessIds {
    param([int]$TargetPort)

    $matches = netstat -ano | Select-String -Pattern ":$TargetPort\s+.*LISTENING\s+(\d+)"
    $ids = @()
    foreach ($match in $matches) {
        $id = [int]$match.Matches[0].Groups[1].Value
        if ($id -gt 0 -and -not $ids.Contains($id)) {
            $ids += $id
        }
    }
    return $ids
}

Write-Host "Project root: $projectRoot" -ForegroundColor Cyan
Write-Host "Python: $pythonPath" -ForegroundColor Cyan

if ($Https) {
    $listeners = Get-ListeningProcessIds -TargetPort $Port
    if ($listeners.Count -gt 0) {
        if ($ReplacePort) {
            Write-Host "Stopping existing listener(s) on port ${Port}: $($listeners -join ', ')" -ForegroundColor Yellow
            Stop-Process -Id $listeners -Force -ErrorAction Stop
            Start-Sleep -Seconds 1
        } else {
            Write-Error "Port $Port is already in use by process id(s): $($listeners -join ', '). Stop the old server or run: .\run_dev.ps1 -Https -ReplacePort"
        }
    }

    $arguments = @("scripts\dev_https.py", "--host", $HostAddress, "--port", $Port)
    Write-Host "Server: https://localhost:$Port/" -ForegroundColor Green
    Write-Host "Starting Django ASGI over local HTTPS..." -ForegroundColor Yellow
    & $pythonPath @arguments
} else {
    $arguments = @("manage.py", "runserver", "$HostAddress`:$Port")
    if ($NoReload) {
        $arguments += "--noreload"
    }
    Write-Host "Server: http://127.0.0.1:$Port/" -ForegroundColor Green
    Write-Host "Starting Django with the project virtual environment..." -ForegroundColor Yellow
    & $pythonPath @arguments
}
