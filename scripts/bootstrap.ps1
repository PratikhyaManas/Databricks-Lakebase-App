Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pythonExe = ".venv\Scripts\python.exe"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not installed or not on PATH. Install uv first: https://docs.astral.sh/uv/"
}

if (-not (Test-Path $pythonExe)) {
    Write-Host "==> Creating virtual environment with uv"
    uv venv .venv
}

Write-Host "==> Installing development dependencies"
uv pip install --python $pythonExe -r requirements-dev.txt

Write-Host "==> Running Ruff"
& $pythonExe -m ruff check app_src tests

Write-Host "==> Running pytest"
& $pythonExe -m pytest -q

Write-Host "==> Bootstrap checks completed"