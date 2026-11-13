@echo off
setlocal EnableExtensions DisableDelayedExpansion
title DataLogPro - InfluxDB user setup

rem ===========================================================================
rem  Creates two InfluxDB users in the FactoryTalk View SE built-in InfluxDB:
rem    - an ADMIN user  (owner of org Rockwell)
rem    - a MEMBER user  (read-only, for the DataLogPro Report Tool)
rem  Run on the HMI PC, as the Windows user whose influx CLI is configured.
rem  The FTViewSE user is never touched.
rem ===========================================================================

set "INFLUX=C:\Program Files (x86)\Rockwell Software\RSView Enterprise\3rdParty\InfluxData\InfluxCli\influx.exe"
set "ORG=Rockwell"
set "ERRORS=0"

echo.
echo  ============================================================
echo   DataLogPro - InfluxDB user setup
echo  ============================================================
echo.

rem ---- 1. checks -----------------------------------------------------------
rem (the path contains "(x86)", so it is echoed outside any ( ) block)
if exist "%INFLUX%" goto :have_influx
echo  [ERROR] influx.exe was not found at:
echo          %INFLUX%
echo          Is FactoryTalk View SE v16 installed on this PC?
goto :fail
:have_influx

"%INFLUX%" ping >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] InfluxDB is not responding. Start the HMI server and try again.
    goto :fail
)
echo  [OK]    InfluxDB is running.

"%INFLUX%" org list -n "%ORG%" >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] The influx CLI cannot read org "%ORG%".
    echo          Run this file as the Windows user that has the influx CLI configured.
    goto :fail
)
echo  [OK]    Org "%ORG%" found and CLI is authorized.
echo.

rem ---- 2. names --------------------------------------------------------------
set "ADMIN=DLPAdmin"
set "MEMBER=DLPReport"
set /p "ADMIN=  Admin user name  [DLPAdmin]  : "
set /p "MEMBER=  Member user name [DLPReport] : "

call :validate "%ADMIN%"  || goto :fail
call :validate "%MEMBER%" || goto :fail
if /i "%ADMIN%"=="%MEMBER%" (
    echo  [ERROR] Admin and member must have different names.
    goto :fail
)
echo.

rem ---- 3. create ---------------------------------------------------------------
call :create_user "%ADMIN%" owner
call :create_user "%MEMBER%" member

rem ---- 4. summary ----------------------------------------------------------------
echo.
echo  ============================================================
echo   Members of org %ORG%
echo  ============================================================
"%INFLUX%" org members list -n "%ORG%"
echo.
if "%ERRORS%"=="0" (
    echo  [DONE]  Users are ready.
    echo          Admin  : %ADMIN%  - owner, for administration only
    echo          Member : %MEMBER% - read-only, use this in the Report Tool
) else (
    echo  [WARN]  Finished with %ERRORS% error^(s^). Read the messages above.
)
echo.
pause
exit /b %ERRORS%

:fail
echo.
echo  Nothing more was changed.
echo.
pause
exit /b 1

rem ===========================================================================
:validate
set "NAME=%~1"
if "%NAME%"=="" (
    echo  [ERROR] A user name cannot be empty.
    exit /b 1
)
if /i "%NAME%"=="FTViewSE" (
    echo  [ERROR] "FTViewSE" is used by FactoryTalk View. Choose another name.
    exit /b 1
)
echo "%NAME%" | findstr /r /c:" " >nul
if not errorlevel 1 (
    echo  [ERROR] User names cannot contain spaces: "%NAME%"
    exit /b 1
)
exit /b 0

rem ===========================================================================
:create_user
set "U=%~1"
set "ROLE=%~2"
echo  ------------------------------------------------------------
echo   %ROLE% user "%U%"
echo  ------------------------------------------------------------

"%INFLUX%" user list -n "%U%" >nul 2>&1
if not errorlevel 1 (
    echo  [SKIP]  User "%U%" already exists. Its role and password were not changed.
    echo.
    exit /b 0
)

"%INFLUX%" user create -n "%U%" -o "%ORG%" >nul
if errorlevel 1 (
    echo  [ERROR] Could not create user "%U%".
    set /a ERRORS+=1
    exit /b 1
)
echo  [OK]    User "%U%" created as member of %ORG%.

if /i not "%ROLE%"=="owner" goto :password

set "UID="
for /f "usebackq tokens=1" %%i in (`"%INFLUX%" user list -n "%U%" --hide-headers`) do set "UID=%%i"
if not defined UID (
    echo  [ERROR] Could not read the ID of "%U%" to make it owner.
    set /a ERRORS+=1
    goto :password
)
"%INFLUX%" org members remove -n "%ORG%" -m %UID% >nul
"%INFLUX%" org members add -n "%ORG%" -m %UID% --owner >nul
if errorlevel 1 (
    echo  [ERROR] Could not make "%U%" an owner. It is still a member.
    set /a ERRORS+=1
) else (
    echo  [OK]    "%U%" is now owner of %ORG%.
)

:password
set "TRIES=0"
:password_retry
set /a TRIES+=1
echo.
echo  Set the password for "%U%" ^(at least 8 characters, typing is hidden^):
"%INFLUX%" user password -n "%U%"
if not errorlevel 1 (
    echo  [OK]    Password set for "%U%".
    echo.
    exit /b 0
)
if %TRIES% lss 3 (
    echo  [RETRY] Password was not accepted. Try again.
    goto :password_retry
)
echo  [ERROR] Password not set for "%U%". Set it later with:
echo          influx user password -n %U%
set /a ERRORS+=1
echo.
exit /b 1
