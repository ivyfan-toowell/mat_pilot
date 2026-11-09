# MatPilot Streamlit UI launcher (Windows PowerShell)
# Invoke this script as: .\start_ui.ps1
# $PSScriptRoot is available inside .ps1 files; no manual PYTHONPATH required.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is not installed or not on PATH. See README.md.'
}

uv run --locked --all-extras streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
