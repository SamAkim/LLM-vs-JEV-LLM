Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
python -m pip install -q -r requirements.txt
Write-Host "Open http://localhost:8000 in your browser (Ctrl+C to stop)" -ForegroundColor Green
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
