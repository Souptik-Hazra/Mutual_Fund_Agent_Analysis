$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $ProjectDir "docker-compose.yml"))) {
    throw "docker-compose.yml was not found in $ProjectDir"
}

$WslProject = (& wsl.exe wslpath -a $ProjectDir 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($WslProject)) {
    throw "Could not resolve the project directory inside WSL."
}

Write-Host "Starting Docker services in WSL:"
Write-Host $WslProject
Write-Host ""

& wsl.exe --cd $WslProject --exec bash scripts/start_docker_wsl.sh
if ($LASTEXITCODE -ne 0) {
    throw "WSL Docker startup failed with exit code $LASTEXITCODE."
}
