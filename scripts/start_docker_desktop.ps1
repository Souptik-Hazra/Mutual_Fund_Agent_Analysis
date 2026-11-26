$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

Write-Host "Starting Docker Desktop on Windows..."

$DockerDesktopCandidates = @(
    "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
    "$env:ProgramW6432\Docker\Docker\Docker Desktop.exe"
) | Select-Object -Unique

$DockerDesktop = $DockerDesktopCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($DockerDesktop) {
    $desktopProcess = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
    if (-not $desktopProcess) {
        Start-Process -FilePath $DockerDesktop
    }
}
else {
    Write-Warning "Docker Desktop executable was not found in the standard installation paths. Checking whether the Docker Engine is already running."
}

$deadline = (Get-Date).AddSeconds(180)
$engineReady = $false
while ((Get-Date) -lt $deadline) {
    docker.exe info --format "{{.ServerVersion}}" *> $null
    if ($LASTEXITCODE -eq 0) {
        $engineReady = $true
        break
    }
    Start-Sleep -Seconds 3
}

if (-not $engineReady) {
    throw "Docker Engine did not become ready within 180 seconds. Start Docker Desktop and ensure it is using the Linux containers engine."
}

Write-Host "Docker Engine is ready. Starting PostgreSQL and Qdrant..."
docker.exe compose up -d db qdrant
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed."
}

docker.exe compose ps
Write-Host ""
Write-Host "Docker services started. PostgreSQL: 127.0.0.1:5432 | Qdrant: 127.0.0.1:6333"
