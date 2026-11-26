$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

$ActivateScript = Join-Path $ProjectDir ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $ActivateScript)) {
    throw "Virtual environment activation script not found: $ActivateScript"
}
. $ActivateScript

$env:DATABASE_URL = "postgresql+psycopg://mfa:mfa_dev_password@127.0.0.1:5432/mutual_fund_agent"
$env:QDRANT_URL = "http://127.0.0.1:6333"
$env:QDRANT_API_KEY = ""

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "wait_for_postgres.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL readiness check failed."
}

alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    throw "Database migration failed."
}

python -m mutual_fund_agent_analysis.cli.sync_catalogue
if ($LASTEXITCODE -ne 0) {
    throw "Mutual fund scheme catalogue initialization failed."
}

uvicorn mutual_fund_agent_analysis.main:app --reload
