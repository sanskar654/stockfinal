$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot 'start-backend.ps1'
$frontendScript = 'npm run dev:frontend'

# Start backend in a dedicated process and wait for health endpoint before starting frontend.
$backendJob = Start-Job -Name 'trade-backend' -ScriptBlock {
    param($scriptPath, $projectRoot)
    Push-Location $projectRoot
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath
    } finally {
        Pop-Location
    }
} -ArgumentList $backendScript, $projectRoot

$healthUrl = 'http://127.0.0.1:8000/health'
$healthy = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    } catch {
        # Backend still starting; retry until ready.
    }
}

if (-not $healthy) {
    Write-Host 'Backend did not become healthy within 90 seconds.'
    Stop-Job -Name 'trade-backend' -ErrorAction SilentlyContinue
    Remove-Job -Name 'trade-backend' -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-Host 'Backend is healthy; starting frontend...'
Push-Location $projectRoot
try {
    Invoke-Expression $frontendScript
} finally {
    Pop-Location
}
