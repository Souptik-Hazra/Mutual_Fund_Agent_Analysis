$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $ProjectDir "docker-compose.yml"))) {
    throw "docker-compose.yml was not found in $ProjectDir"
}

# Convert the Windows drive path using WSL's standard /mnt/<drive> automount.
# This avoids depending on wslpath being available in the default distribution.
if ($ProjectDir -notmatch '^([A-Za-z]):(.*)$') {
    throw "Project directory is not on a drive-letter path: $ProjectDir"
}

$Drive = $Matches[1].ToLowerInvariant()
$Tail = $Matches[2].Replace("\", "/")
$WslProject = "/mnt/$Drive$Tail"

Write-Host "Starting Docker services in WSL:"
Write-Host $WslProject
Write-Host ""

# Confirm WSL can access this exact project directory before launching the script.
& wsl.exe --cd "$WslProject" --exec test -f docker-compose.yml
if ($LASTEXITCODE -ne 0) {
    throw "WSL cannot access $WslProject. Check that the Windows drive is mounted in WSL."
}

& wsl.exe --cd "$WslProject" --exec bash scripts/start_docker_wsl.sh
if ($LASTEXITCODE -ne 0) {
    throw "WSL Docker startup failed with exit code $LASTEXITCODE."
}
