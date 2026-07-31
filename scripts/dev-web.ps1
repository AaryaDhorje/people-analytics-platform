<#
.SYNOPSIS
  Start the Vite dev server on a known port, reliably.

.DESCRIPTION
  Pinned with --strictPort. Vite's default behaviour on a busy port is to silently move to
  the next one, which is how this build ended up with three dead listeners across
  5173-5180 and a CORS_ORIGINS list chasing them. Better to free the port we mean and fail
  loudly if we cannot.

.EXAMPLE
  pwsh scripts/dev-web.ps1
  pwsh scripts/dev-web.ps1 -Port 5174
#>
[CmdletBinding()]
param(
    [int]$Port = 5173
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Free-Port.ps1')

$frontend = Join-Path (Split-Path -Parent $PSScriptRoot) 'frontend'

if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    throw "No node_modules in $frontend. Run: cd frontend; npm install"
}

Clear-Port -Port $Port

Write-Host "Starting: npm run dev -- --port $Port --strictPort  (cwd $frontend)"
Push-Location $frontend
try {
    & npm run dev -- --port $Port --strictPort
}
finally {
    Pop-Location
}
