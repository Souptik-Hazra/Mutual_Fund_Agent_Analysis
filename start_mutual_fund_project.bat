@echo off
setlocal

REM Resolve the repository directory from this script's location.
for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
set "VENV_ACTIVATE=%PROJECT_DIR%\.venv\Scripts\activate.bat"
set "FRONTEND_DIR=%PROJECT_DIR%\frontend"

if not exist "%PROJECT_DIR%\docker-compose.yml" (
    echo ERROR: docker-compose.yml was not found in:
    echo %PROJECT_DIR%
    pause
    exit /b 1
)

if not exist "%VENV_ACTIVATE%" (
    echo ERROR: Windows virtual environment not found:
    echo %VENV_ACTIVATE%
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo ERROR: Frontend package.json not found:
    echo %FRONTEND_DIR%
    pause
    exit /b 1
)

REM Convert the actual repository path to the selected WSL distribution's path.
for /f "usebackq delims=" %%I in (`wsl.exe wslpath -a "%PROJECT_DIR%" 2^>nul`) do set "WSL_PROJECT=%%I"
if not defined WSL_PROJECT (
    echo ERROR: Could not translate the project path into WSL.
    echo Check that WSL is installed and the Windows drive is mounted.
    pause
    exit /b 1
)

where wt.exe >nul 2>nul
if errorlevel 1 (
    echo Windows Terminal was not found. Opening separate Command Prompt windows.
    start "Docker - WSL" cmd /k "wsl.exe --cd ""%WSL_PROJECT%"" -- bash -lc ""sudo service docker start && docker compose up -d db qdrant; exec bash"""
    start "Backend - FastAPI" cmd /k "cd /d ""%PROJECT_DIR%"" && call ""%VENV_ACTIVATE%"" && uvicorn mutual_fund_agent_analysis.main:app --reload"
    start "Frontend - Vite" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"
) else (
    start "Docker - WSL" wt.exe -w new --title "Docker - WSL" wsl.exe --cd "%WSL_PROJECT%" -- bash -lc "sudo service docker start && docker compose up -d db qdrant; exec bash"
    start "Backend - FastAPI" wt.exe -w new --title "Backend - FastAPI" cmd.exe /k "cd /d ""%PROJECT_DIR%"" && call ""%VENV_ACTIVATE%"" && uvicorn mutual_fund_agent_analysis.main:app --reload"
    start "Frontend - Vite" wt.exe -w new --title "Frontend - Vite" cmd.exe /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"
)

echo.
echo Startup terminals have been launched.
echo Docker services: PostgreSQL and Qdrant
echo Backend:         http://127.0.0.1:8000
echo Frontend:        Vite development server
echo.
endlocal
