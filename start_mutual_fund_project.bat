@echo off
setlocal EnableExtensions

if /i "%~1"=="__keep_open" goto :launcher
start "Mutual Fund Agent Analysis" "%ComSpec%" /k ""%~f0" __keep_open"
exit /b

:launcher
title Mutual Fund Agent Analysis - Launcher
for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
set "FRONTEND_DIR=%PROJECT_DIR%\frontend"
set "VENV_ACTIVATE=%PROJECT_DIR%\.venv\Scripts\activate.bat"

echo.
echo ==========================================
echo   Mutual Fund Agent Analysis - Startup
echo ==========================================
echo Project: "%PROJECT_DIR%"
echo.

if exist "%VENV_ACTIVATE%" goto :check_frontend
echo ERROR: Windows virtual environment was not found: "%VENV_ACTIVATE%"
goto :fail

:check_frontend
if exist "%FRONTEND_DIR%\package.json" goto :check_modules
echo ERROR: Frontend package.json was not found.
goto :fail

:check_modules
if exist "%FRONTEND_DIR%\node_modules\vite\bin\vite.js" goto :check_npm
echo ERROR: Frontend dependencies are missing. Run npm ci in frontend.
goto :fail

:check_npm
where npm.cmd >nul 2>nul
if not errorlevel 1 goto :check_terminal
echo ERROR: npm is unavailable on PATH.
goto :fail

:check_terminal
where wt.exe >nul 2>nul
if not errorlevel 1 goto :launch
echo ERROR: Windows Terminal (wt.exe) is required.
goto :fail

:launch
REM Start only the Windows-hosted backend and frontend. Docker must be started separately.
start "Backend - FastAPI" wt.exe -w new --title "Backend - FastAPI" --startingDirectory "%PROJECT_DIR%" powershell.exe -NoExit -ExecutionPolicy Bypass -File "%PROJECT_DIR%\scripts\start_backend.ps1"
start "Frontend - Vite" wt.exe -w new --title "Frontend - Vite" --startingDirectory "%FRONTEND_DIR%" cmd.exe /k npm run dev

echo.
echo Backend and frontend terminals have been launched.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo.
echo Ensure PostgreSQL and Qdrant are already running before using backend features.
echo Keep both terminals open while developing.
pause
exit /b 0

:fail
echo.
echo Startup failed. Review the error above.
pause
exit /b 1
