@echo off
setlocal EnableExtensions

title Mutual Fund Agent Analysis - Launcher

REM Resolve the repository directory from this script's location.
for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
set "VENV_ACTIVATE=%PROJECT_DIR%\.venv\Scripts\activate.bat"
set "FRONTEND_DIR=%PROJECT_DIR%\frontend"

echo.
echo ==========================================
echo   Mutual Fund Agent Analysis - Startup
echo ==========================================
echo Project: "%PROJECT_DIR%"
echo.

REM Validate required project files and local tools before opening terminals.
if not exist "%PROJECT_DIR%\docker-compose.yml" (
    echo ERROR: docker-compose.yml was not found in the project directory.
    goto :fail
)
if not exist "%VENV_ACTIVATE%" (
    echo ERROR: Windows virtual environment not found:
    echo "%VENV_ACTIVATE%"
    goto :fail
)
if not exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
    echo ERROR: The virtual environment Python executable is missing.
    goto :fail
)
if not exist "%FRONTEND_DIR%\package.json" (
    echo ERROR: Frontend package.json was not found.
    goto :fail
)
if not exist "%FRONTEND_DIR%\node_modules\vite\bin\vite.js" (
    echo ERROR: Frontend dependencies are missing. Run "npm ci" in frontend first.
    goto :fail
)
where wsl.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: WSL is not installed or wsl.exe is not on PATH.
    goto :fail
)
where python.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    goto :fail
)
where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm was not found on PATH.
    goto :fail
)

REM Convert the actual Windows repository path to the default WSL distribution path.
set "WSL_PROJECT="
for /f "usebackq delims=" %%I in (`wsl.exe wslpath -a "%PROJECT_DIR%" 2^>nul`) do set "WSL_PROJECT=%%I"
if not defined WSL_PROJECT (
    echo ERROR: Could not translate the project path into WSL.
    echo Check that your Windows drive is mounted in the default WSL distribution.
    goto :fail
)

REM Confirm Docker Compose is available inside the selected default WSL distribution.
wsl.exe --cd "%WSL_PROJECT%" -- bash -lc "command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1"
if errorlevel 1 (
    echo ERROR: Docker Engine and Docker Compose must be installed in the default WSL distribution.
    goto :fail
)

where wt.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: Windows Terminal (wt.exe) is required for three separate terminals.
    goto :fail
)

REM Terminal 1: start Docker Engine, PostgreSQL and Qdrant.
start "Docker - WSL" wt.exe -w new --title "Docker - WSL" wsl.exe --cd "%WSL_PROJECT%" -- bash -lc "sudo service docker start && docker compose up -d db qdrant; exec bash -i"

REM Terminal 2: wait for PostgreSQL, apply migrations, then start FastAPI.
start "Backend - FastAPI" wt.exe -w new --title "Backend - FastAPI" cmd.exe /k "cd /d ""%PROJECT_DIR%"" && call ""%VENV_ACTIVATE%"" && set ""DATABASE_URL=postgresql+psycopg://mfa:mfa_dev_password@127.0.0.1:5432/mutual_fund_agent"" && set ""QDRANT_URL=http://127.0.0.1:6333"" && set ""QDRANT_API_KEY="" && powershell -NoProfile -Command ""$deadline=(Get-Date).AddSeconds(120); while ((Get-Date) -lt $deadline) { try { $client=New-Object Net.Sockets.TcpClient; $client.Connect('127.0.0.1',5432); $client.Close(); exit 0 } catch { Start-Sleep -Seconds 2 } }; exit 1"" && alembic upgrade head && uvicorn mutual_fund_agent_analysis.main:app --reload"

REM Terminal 3: start the Vite development server.
start "Frontend - Vite" wt.exe -w new --title "Frontend - Vite" cmd.exe /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"

echo.
echo Startup terminals have been launched.
echo Docker:    PostgreSQL :5432 and Qdrant :6333 (WSL services)
echo Backend:   http://127.0.0.1:8000
echo Frontend:  http://127.0.0.1:5173
echo.
echo Keep all three terminals open while developing.
echo.
echo This launcher window will remain open. Press any key to close it.
pause >nul
exit /b 0

:fail
echo.
echo Startup failed. Review the error above.
echo Press any key to close this window.
pause >nul
exit /b 1
