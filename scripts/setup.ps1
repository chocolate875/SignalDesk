$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/' }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js/npm is needed to build the local dashboard.' }
    Write-Host 'Installing locked Python dependencies...'
    & uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        Write-Host 'Building local dashboard assets...'
        & npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Dashboard build failed.' }
    } finally { Pop-Location }
    Write-Host 'Ready. Double-click Start-SignalDesk.cmd.'
} finally { Pop-Location }
