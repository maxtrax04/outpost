<#
.SYNOPSIS
    Runs all tests inside Docker containers, so nothing needs to be installed.
.EXAMPLE
    .\scripts\test.ps1
#>
$ErrorActionPreference = "Stop"

$root = (git rev-parse --show-toplevel).Trim()

Write-Host "== Python tests ==" -ForegroundColor Cyan
docker run --rm -v "${root}:/work" -w /work -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim python -m unittest discover -s tests -b
if ($LASTEXITCODE -ne 0) { Write-Host "Python tests failed." -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "`n== JavaScript tests ==" -ForegroundColor Cyan
docker run --rm -v "${root}:/work" -w /work -e TZ=UTC node:22-slim node --test tests/dim.test.js
if ($LASTEXITCODE -ne 0) { Write-Host "JavaScript tests failed." -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "`nAll tests passed." -ForegroundColor Green
