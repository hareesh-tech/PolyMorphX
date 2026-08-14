@echo off
REM PolyMorph setup wrapper for Windows - double-click friendly.
REM Runs setup.ps1 with the execution policy bypassed for this process only.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
echo.
pause
