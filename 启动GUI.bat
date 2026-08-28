@echo off
rem Double-clicking .bat always flashes a console briefly.
rem Hand off immediately to the silent VBS launcher (no pythonw console).
start "" wscript //nologo "%~dp0启动GUI.vbs"
exit /b 0
