@echo off
setlocal
cd /d "%~dp0..\frontend"
if errorlevel 1 (
    echo ERROR: Could not enter the frontend directory.
    pause
    exit /b 1
)
npm run dev
pause
