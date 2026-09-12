$ErrorActionPreference = 'Stop'

$backendDir = Join-Path $PSScriptRoot '..\Backend'
$venvPy = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'

if (-not (Test-Path $venvPy)) {
    $venvPy = Join-Path $backendDir '.venv\Scripts\python.exe'
}

if (-not (Test-Path $venvPy)) {
    $venvPy = 'python'
}

$port = 8000
$listener = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($listener) {
    Write-Host "Port 8000 is already in use; attempting to stop the stale listener..."
    foreach ($item in $listener) {
        try {
            $procId = $item.OwningProcess
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped process $procId holding port 8000."
        } catch {
            Write-Host "Could not stop process $procId; continuing."
        }
    }
    Start-Sleep -Seconds 1
}

Push-Location $backendDir
try {
    & $venvPy -m uvicorn api.app:app --reload --host 0.0.0.0 --port $port
} finally {
    Pop-Location
}
