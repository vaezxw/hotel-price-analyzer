@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title hotel-price-analyzer-setup

echo ==============================================
echo   Hotel Price Tool - Setup
echo ==============================================
echo.
echo Script folder:
echo   %CD%
echo.

set "PY="
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [ERROR] Python 3 not found.
    echo.
    echo Install from: https://www.python.org/downloads/
    echo Check the box: Add python.exe to PATH
    echo Then close this window and run setup again.
    echo.
    goto :END
)

echo [1/3] Python:
%PY% --version
if errorlevel 1 (
    echo [ERROR] Cannot run Python.
    goto :END
)
echo.

echo [2/3] Installing pip packages...
%PY% -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed. Check network and retry.
    goto :END
)
echo.

echo [3/3] Installing Chromium for Playwright...
%PY% -m playwright install chromium
if errorlevel 1 (
    echo [ERROR] playwright install chromium failed.
    goto :END
)

%PY% -c "from pathlib import Path; Path('data').mkdir(exist_ok=True); Path('\u8f93\u51fa').mkdir(exist_ok=True)"

echo.
echo ==============================================
echo   Setup OK
echo ==============================================
echo.
echo Next:
echo   1. Double-click start script: start with Chinese name "qi dong"
echo      File name: use the bat next to this one named with Chinese "start"
echo   2. In menu choose 1 - login Ctrip
echo   3. In menu choose 6 - collect / analyze / export
echo.
echo Read: shuoming.txt (Chinese filename "shuo ming")
echo.

:END
echo.
echo Press any key to close...
pause >nul
endlocal
