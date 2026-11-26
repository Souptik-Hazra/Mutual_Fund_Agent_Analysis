@echo off
setlocal

REM Project location on Windows
set "PROJECT_DIR=%USERPROFILE%\Downloads\Mutual_Fund_Agent_Analysis"
set "VENV_ACTIVATE=%PROJECT_DIR%\.venv\Scripts\activate.bat"
set "FRONTEND_DIR=%PROJECT_DIR%\frontend"

REM Convert the Windows project path to its WSL /mnt path.
set "WSL_PROJECT=/mnt/c/Users/%USERNAME%/Downloads/Mutual_Fund_Agent_Analysis"

if not exist "%PROJECT_DIR%\docker-compose.yml" (
    echo ERROR: Project folder not found:
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

where wt.exe >nul 2>nul
if errorlevel 1 (
    echo Windows Terminal was not found. Opening separate Command Prompt windows.
    start "Docker - WSL" cmd /k "wsl.exe --cd %WSL_PROJECT% -- bash -lc ""sudo service docker start && docker compose up -d db qdrant; exec bash"""
    start "Backend - FastAPI" cmd /k "cd /d ""%PROJECT_DIR%"" && call ""%VENV_ACTIVATE%"" && uvicorn mutual_fund_agent_analysis.main:app --reload"
    start "Frontend - Vite" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"
) else (
    REM Each command opens in its own Windows Terminal window.
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
