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
if not exist "venv\Scripts\python.exe" (
    echo [Setup] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [Error] Failed to create venv. Is Python installed and in PATH?
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    echo [Setup] Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [Error] pip install failed.
        pause
        exit /b 1
    )
    echo [Setup] Done.
    echo.
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
