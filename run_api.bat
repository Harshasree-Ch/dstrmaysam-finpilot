@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -m venv .venv
.venv\Scripts\python.exe -c "import fastapi, uvicorn" 2>nul
if errorlevel 1 .venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn finpilot.api:app --app-dir src --host 0.0.0.0 --port 8600 %*
