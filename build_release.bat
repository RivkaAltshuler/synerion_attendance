@echo off
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "PY_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "RELEASE_DIR=%SCRIPT_DIR%release\synerion_attendance"
set "ZIP_PATH=%SCRIPT_DIR%release\synerion_attendance.zip"

if not exist "%PY_EXE%" (
  echo [שגיאה] סביבת הפיתוח לא מוכנה. יש להריץ קודם setup.bat.
  pause
  exit /b 1
)

echo [1/5] בונה EXE ללוגיקת הדיווח...
"%PY_EXE%" -m PyInstaller --clean --noconfirm --onefile --name synerion_attendance "%SCRIPT_DIR%attend.py"
if errorlevel 1 (
  echo [שגיאה] בניית ה-EXE נכשלה.
  pause
  exit /b 1
)

echo [2/5] בונה EXE לממשק ה-Web המקומי...
"%PY_EXE%" -m PyInstaller --clean --noconfirm --onefile --name synerion_web_ui "%SCRIPT_DIR%web_app.py"
if errorlevel 1 (
  echo [שגיאה] בניית EXE לממשק ה-Web נכשלה.
  pause
  exit /b 1
)

echo [3/5] יוצר תיקיית הפצה...
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"

echo [4/5] מעתיק קבצים למשתמש הקצה...
copy /y "%SCRIPT_DIR%dist\synerion_attendance.exe" "%RELEASE_DIR%\synerion_attendance.exe" >nul
copy /y "%SCRIPT_DIR%dist\synerion_web_ui.exe" "%RELEASE_DIR%\synerion_web_ui.exe" >nul
copy /y "%SCRIPT_DIR%select_pdf.ps1" "%RELEASE_DIR%\select_pdf.ps1" >nul
copy /y "%SCRIPT_DIR%02-בדיקת-קובץ-PDF.bat" "%RELEASE_DIR%\02-בדיקת-קובץ-PDF.bat" >nul
copy /y "%SCRIPT_DIR%03-אימות-מול-סינריון.bat" "%RELEASE_DIR%\03-אימות-מול-סינריון.bat" >nul
copy /y "%SCRIPT_DIR%04-דיווח-אוטומטי-לסינריון.bat" "%RELEASE_DIR%\04-דיווח-אוטומטי-לסינריון.bat" >nul
copy /y "%SCRIPT_DIR%05-ממשק-ווב-מקומי.bat" "%RELEASE_DIR%\05-ממשק-ווב-מקומי.bat" >nul
copy /y "%SCRIPT_DIR%run_summary.bat" "%RELEASE_DIR%\run_summary.bat" >nul
copy /y "%SCRIPT_DIR%run_verify.bat" "%RELEASE_DIR%\run_verify.bat" >nul
copy /y "%SCRIPT_DIR%run_auto.bat" "%RELEASE_DIR%\run_auto.bat" >nul
copy /y "%SCRIPT_DIR%run_web.bat" "%RELEASE_DIR%\run_web.bat" >nul
copy /y "%SCRIPT_DIR%invoke_attendance.ps1" "%RELEASE_DIR%\invoke_attendance.ps1" >nul
copy /y "%SCRIPT_DIR%README.md" "%RELEASE_DIR%\README.md" >nul
copy /y "%SCRIPT_DIR%הוראות-שימוש-מהיר.txt" "%RELEASE_DIR%\הוראות-שימוש-מהיר.txt" >nul

echo [5/5] יוצר ZIP להפצה...
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path '%ZIP_PATH%') { Remove-Item '%ZIP_PATH%' -Force }; Compress-Archive -Path '%RELEASE_DIR%\*' -DestinationPath '%ZIP_PATH%'"
if errorlevel 1 (
  echo [שגיאה] יצירת קובץ ה-ZIP נכשלה.
  pause
  exit /b 1
)

echo.
echo [הצלחה] חבילת ההפצה מוכנה.
echo תיקייה: %RELEASE_DIR%
echo ZIP:    %ZIP_PATH%
