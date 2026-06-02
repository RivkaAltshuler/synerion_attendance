@echo off
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "PY_EXE=%VENV_DIR%\Scripts\python.exe"
set "PIP_EXE=%VENV_DIR%\Scripts\pip.exe"
set "PLAYWRIGHT_EXE=%VENV_DIR%\Scripts\playwright.exe"
set "PY_CMD="

echo [1/4] Checking Python environment...
where py >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3"
if "%PY_CMD%"=="" (
  where python >nul 2>&1
  if not errorlevel 1 set "PY_CMD=python"
)
if "%PY_CMD%"=="" (
  echo [ERROR] Python was not found. Install Python 3.10 or later with PATH enabled.
  pause
  exit /b 1
)
echo [OK] Using command: %PY_CMD%

echo [2/4] Creating local environment if needed...
if not exist "%PY_EXE%" (
  %PY_CMD% -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERROR] Failed to create the local environment.
    pause
    exit /b 1
  )
) else (
  echo [OK] Local environment already exists.
)

echo [3/4] Installing Python dependencies...
"%PY_EXE%" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] Failed to upgrade pip.
  pause
  exit /b 1
)

"%PY_EXE%" -m pip install -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (
  echo [ERROR] Failed to install required packages.
  pause
  exit /b 1
)

echo [4/4] Installing Playwright Chromium...
"%PLAYWRIGHT_EXE%" install chromium
if errorlevel 1 (
  echo [ERROR] Failed to install Playwright Chromium.
  pause
  exit /b 1
)

echo.
echo [SUCCESS] Setup completed.
echo You can now run one of these files:
echo   02-בדיקת-קובץ-PDF.bat        - Validate the PDF only
echo   03-אימות-מול-סינריון.bat     - Verify against Synerion
echo   04-דיווח-אוטומטי-לסינריון.bat - Fill Synerion automatically
pause
