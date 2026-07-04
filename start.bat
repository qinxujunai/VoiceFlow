@echo off
cd /d "%~dp0"

set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8

echo.
echo  ========================================
echo    VoiceFlow - Local Speech to Text
echo  ========================================
echo.
echo    Free - Open Source - Offline
echo.
echo    [F2 / MouseSideButtons] Start / Stop dictation
echo    [Esc] Cancel
echo.
echo  ========================================
echo.

rem --- check venv ---
set "BOOTSTRAP_PY="

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -c "import sys" >nul 2>nul
    if not errorlevel 1 set "BOOTSTRAP_PY=venv\Scripts\python.exe"
)

if not defined BOOTSTRAP_PY (
    py -3.12 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "BOOTSTRAP_PY=py -3.12"
)

if not defined BOOTSTRAP_PY (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "BOOTSTRAP_PY=py -3"
)

if not defined BOOTSTRAP_PY (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "BOOTSTRAP_PY=python"
)

if not defined BOOTSTRAP_PY (
    echo [Error] No usable Python found. Install Python 3.10+ and try again.
    pause
    exit /b 1
)

%BOOTSTRAP_PY% scripts\bootstrap.py --ensure-shortcut
if errorlevel 1 (
    echo.
    echo [Error] VoiceFlow setup check failed.
    pause
    exit /b 1
)

echo [Launch] Starting VoiceFlow...
echo.

venv\Scripts\python.exe -u src\main.py
set EXITCODE=%ERRORLEVEL%

if %EXITCODE% neq 0 (
    echo.
    echo [Error] VoiceFlow exited with code %EXITCODE%
    pause
)

exit /b %EXITCODE%
