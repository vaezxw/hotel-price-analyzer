@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [ERROR] Python not found. Install Python 3 and add to PATH.
    goto :END
)

%PY% pack_share.py
if errorlevel 1 echo [ERROR] pack_share.py failed.

:END
echo.
echo Press any key to close...
pause >nul
endlocal
