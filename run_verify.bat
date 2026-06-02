@echo off
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%invoke_attendance.ps1" -Mode verify %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo Done.
pause
exit /b %EXIT_CODE%
