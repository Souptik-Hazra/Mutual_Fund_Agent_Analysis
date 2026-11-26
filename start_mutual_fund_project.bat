@echo off
setlocal EnableExtensions

REM Relaunch in a persistent Command Prompt when started by double-click.
if /i "%~1"=="__keep_open" goto :launcher
start "Mutual Fund Agent Analysis" "%ComSpec%" /k ""%~f0" __keep_open"
exit /b

:launcher
title Mutual Fund Agent Analysis - Launcher
for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
set "VENV_ACTIVATE=%PROJECT_DIR%\.venv\Scripts\activate.bat"
set "VENV_PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "FRONTEND_DIR=%PROJECT_DIR%\frontend"

echo.
echo ==========================================
echo   Mutual Fund Agent Analysis - Startup
echo ==========================================
echo Project: "%PROJECT_DIR%"
echo.

REM Validate required files and tools. Label-based checks avoid fragile IF blocks.
if exist "%PROJECT_DIR%\docker-compose.yml" goto :check_venv
echo ERROR: docker-compose.yml was not found.
goto :fail

:check_venv
if exist "%VENV_ACTIVATE%" goto :check_python
echo ERROR: Windows virtual environment activation script was not found:
echo "%VENV_ACTIVATE%"
goto :fail

:check_python
if exist "%VENV_PYTHON%" goto :check_frontend
echo ERROR: Virtual environment Python executable is missing.
goto :fail

:check_frontend
if exist "%FRONTEND_DIR%\package.json" goto :check_vite
echo ERROR: Frontend package.json was not found.
goto :fail

:check_vite
if exist "%FRONTEND_DIR%\node_modules\vite\bin\vite.js" goto :check_wsl
echo ERROR: Frontend dependencies are missing. Run npm ci in frontend first.
goto :fail

:check_wsl
where wsl.exe >nul 2>nul
if not errorlevel 1 goto :check_npm
echo ERROR: WSL is not installed or wsl.exe is not on PATH.
goto :fail

:check_npm
where npm.cmd >nul 2>nul
if not errorlevel 1 goto :check_terminal
echo ERROR: npm was not found on PATH.
goto :fail

:check_terminal
where wt.exe >nul 2>nul
if not errorlevel 1 goto :resolve_wsl
echo ERROR: Windows Terminal (wt.exe) is required for three separate terminals.
goto :fail

:resolve_wsl
set "WSL_PROJECT="
for /f "usebackq delims=" %%I in (`wsl.exe wslpath -a "%PROJECT_DIR%" 2^>nul`) do set "WSL_PROJECT=%%I"
if defined WSL_PROJECT goto :check_docker
echo ERROR: Could not translate the project path into WSL.
goto :fail

:check_docker
wsl.exe --cd "%WSL_PROJECT%" -- bash -lc "command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1"
if not errorlevel 1 goto :launch_terminals
echo ERROR: Docker Engine and Docker Compose are not available in the default WSL distribution.
goto :fail

:launch_terminals
REM Terminal 1: start Docker Engine and the database/vector services.
start "Docker - WSL" wt.exe -w new --title "Docker - WSL" wsl.exe --cd "%WSL_PROJECT%" -- bash -lc "sudo service docker start && docker compose up -d db qdrant; exec bash -i"

REM Terminal 2: wait for PostgreSQL, migrate, then start FastAPI.
start "Backend - FastAPI" wt.exe -w new --title "Backend - FastAPI" cmd.exe /k "cd /d ""%PROJECT_DIR%"" && call ""%VENV_ACTIVATE%"" && set ""DATABASE_URL=postgresql+psycopg://mfa:mfa_dev_password@127.0.0.1:5432/mutual_fund_agent"" && set ""QDRANT_URL=http://127.0.0.1:6333"" && set ""QDRANT_API_KEY="" && powershell -NoProfile -ExecutionPolicy Bypass -File ""%PROJECT_DIR%\scripts\wait_for_postgres.ps1"" && alembic upgrade head && uvicorn mutual_fund_agent_analysis.main:app --reload"

REM Terminal 3: start the Vite development server.
start "Frontend - Vite" wt.exe -w new --title "Frontend - Vite" cmd.exe /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"

echo.
echo Startup terminals have been launched.
echo Docker:    PostgreSQL :5432 and Qdrant :6333 (WSL services)
echo Backend:   http://127.0.0.1:8000
echo Frontend:  http://127.0.0.1:5173
echo.
echo Keep all three terminals open while developing.
echo Press any key to close this launcher window.
pause
exit /b 0

:fail
echo.
echo Startup failed. Review the error above.
echo Press any key to close this window.
pause
exit /b 1
