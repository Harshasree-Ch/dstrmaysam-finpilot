$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    py -m venv .venv
}

& $venvPython -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install -r requirements.txt
}

& $venvPython -m uvicorn finpilot.api:app --app-dir src --host 0.0.0.0 --port 8600 @args
