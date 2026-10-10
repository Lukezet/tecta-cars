$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
& (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") (Join-Path $PSScriptRoot "app.py")
