@echo off
setlocal
cd /d "%~dp0"

python -m pip install -q -r requirements.txt
echo Open http://localhost:8000 in your browser (Press Ctrl+C to stop)
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
