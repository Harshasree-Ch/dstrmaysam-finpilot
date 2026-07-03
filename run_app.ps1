$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    py -m venv .venv
}

& $venvPython -c "import streamlit, growwapi" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install -r requirements.txt
}

& $venvPython -m streamlit run app.py @args
