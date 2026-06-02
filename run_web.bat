@echo off
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "WEB_EXE=%SCRIPT_DIR%synerion_web_ui.exe"
set "DIST_WEB_EXE=%SCRIPT_DIR%dist\synerion_web_ui.exe"
set "PY_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"

if not exist "%WEB_EXE%" if not exist "%DIST_WEB_EXE%" if not exist "%PY_EXE%" (
	echo [ERROR] Web UI executable and development environment were not found.
	echo End user: run from the release folder.
	echo Developer: run setup.bat first.
	pause
	exit /b 1
)

echo Starting local web interface...
echo Your browser will open automatically.
echo If browser does not open, browse to: http://127.0.0.1:5000
echo Leave this window open while using the web page.
echo.

if exist "%WEB_EXE%" (
	"%WEB_EXE%"
) else if exist "%DIST_WEB_EXE%" (
	"%DIST_WEB_EXE%"
) else (
	"%PY_EXE%" "%SCRIPT_DIR%web_app.py"
)

echo.
echo Web interface stopped.
pause
