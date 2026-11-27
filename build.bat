@echo off
setlocal EnableExtensions
rem Builds dist\DLPReport.exe (runs the unit tests first).
cd /d "%~dp0"

py -m pip install -r requirements.txt pyinstaller || goto :fail
py -m unittest discover -s tests -v || goto :fail
py -m PyInstaller --noconfirm --clean --onefile --windowed --name DLPReport main.py || goto :fail
py tools\collect_licenses.py -r requirements.txt --tkinter --app "DLPReport" -o dist\THIRD_PARTY_LICENSES.txt || goto :fail

echo.
echo [DONE] dist\DLPReport.exe  (share dist\THIRD_PARTY_LICENSES.txt with it)
pause
exit /b 0

:fail
echo.
echo [ERROR] Build failed - see the messages above.
pause
exit /b 1
