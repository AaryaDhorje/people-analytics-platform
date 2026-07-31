<#
.SYNOPSIS
  Start the API for local development, reliably.

.DESCRIPTION
  Frees the port by *owning process* before starting, so an orphaned `--reload` child
  cannot keep serving stale code from a port the new server then fails to bind. See
  scripts/Free-Port.ps1 for why that is not hypothetical.

.EXAMPLE
  pwsh scripts/dev-api.ps1
  pwsh scripts/dev-api.ps1 -Port 8001 -NoReload
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    # Skip --reload. Use when running something long that a stray file save must not restart.
    [switch]$NoReload
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Free-Port.ps1')

$backend = Join-Path (Split-Path -Parent $PSScriptRoot) 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw "No virtualenv at $python. Run: cd backend; python -m venv .venv; .venv\Scripts\pip install -e '.[dev]'"
}

Clear-Port -Port $Port

$uvicornArgs = @('-m', 'uvicorn', 'app.main:app', '--port', "$Port")
if (-not $NoReload) { $uvicornArgs += '--reload' }

Write-Host "Starting: python $($uvicornArgs -join ' ')  (cwd $backend)"
Push-Location $backend
try {
    & $python @uvicornArgs
}
finally {
    Pop-Location
}
