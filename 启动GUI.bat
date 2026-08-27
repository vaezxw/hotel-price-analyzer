@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Launch GUI with pythonw so only the tool window appears (no console).

where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw -3 "%~dp0gui\app.py"
    exit /b 0
)

where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw "%~dp0gui\app.py"
    exit /b 0
)

rem Resolve python.exe path, then use sibling pythonw.exe
set "PYEXE="
where py >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
)
if not defined PYEXE (
    where python >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
    )
)

if defined PYEXE (
    for %%I in ("%PYEXE%") do set "PYDIR=%%~dpI"
    if exist "%PYDIR%pythonw.exe" (
        start "" "%PYDIR%pythonw.exe" "%~dp0gui\app.py"
        exit /b 0
    )
)

echo [ERROR] pythonw.exe not found.
echo Install Python 3 (with pythonw) and add to PATH.
echo.
pause
endlocal
