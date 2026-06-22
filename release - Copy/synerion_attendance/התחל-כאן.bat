@echo off
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "WEB_EXE=%SCRIPT_DIR%synerion_web_ui.exe"

if not exist "%WEB_EXE%" (
	echo [ERROR] synerion_web_ui.exe was not found in this folder.
	pause
	exit /b 1
)

echo Starting local web interface...
echo Your browser will open automatically.
echo If browser does not open, browse to: http://127.0.0.1:5000
echo Leave this window open while using the web page.
echo.

"%WEB_EXE%"

echo.
echo Web interface stopped.
pause