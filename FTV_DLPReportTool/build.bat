@echo off
setlocal EnableExtensions
rem Builds dist\DLPReport.exe (runs the unit tests first).
cd /d "%~dp0"

py -m pip install -r requirements.txt pyinstaller || goto :fail
py -m unittest discover -s tests -v || goto :fail
py -m PyInstaller --noconfirm --clean --onefile --windowed --name DLPReport --collect-data sv_ttk main.py || goto :fail

echo.
echo [DONE] dist\DLPReport.exe
pause
exit /b 0

:fail
echo.
echo [ERROR] Build failed - see the messages above.
pause
exit /b 1
