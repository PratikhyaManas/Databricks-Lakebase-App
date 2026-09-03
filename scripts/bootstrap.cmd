@echo off
setlocal

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul

where uv >nul 2>&1
if errorlevel 1 (
  echo uv is not installed or not on PATH. Install uv first: https://docs.astral.sh/uv/
  popd >nul
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo ==^> Creating virtual environment with uv
  uv venv .venv
  if errorlevel 1 goto :fail
)

echo ==^> Installing development dependencies
uv pip install --python ".venv\Scripts\python.exe" -r requirements-dev.txt
if errorlevel 1 goto :fail

echo ==^> Running Ruff
".venv\Scripts\python.exe" -m ruff check app_src tests
if errorlevel 1 goto :fail

echo ==^> Running pytest
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto :fail

echo ==^> Bootstrap checks completed
popd >nul
exit /b 0

:fail
popd >nul
exit /b 1