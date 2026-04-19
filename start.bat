@echo off
REM ============================================================
REM Multi-Agent Data Analyst - ONE-CLICK Windows launcher
REM ------------------------------------------------------------
REM What this file does, in order:
REM   1) Locates a Python interpreter (prefer .venv, then global).
REM   2) First-run only: creates .venv and pip-installs requirements.
REM   3) Copies .env from .env.example if missing.
REM   4) Hands over to launch.py (handles uvicorn + readiness + browser).
REM   5) Keeps the cmd window open on error so you can read the message.
REM
REM IMPORTANT: keep this file pure ASCII + CRLF.
REM            cmd.exe will otherwise mangle bytes under GBK codepage.
REM ============================================================

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo === Multi-Agent Data Analyst : Launcher ===
echo Working dir: %CD%
echo.

REM ---- 1. Locate a Python interpreter for the install step ----
REM      (venv has not been created yet on first run)
set "BOOTPY="
where python >nul 2>nul
if not errorlevel 1 set "BOOTPY=python"
if "%BOOTPY%"=="" (
    where py >nul 2>nul
    if not errorlevel 1 set "BOOTPY=py -3"
)
if "%BOOTPY%"=="" (
    echo [ERROR] Python is not installed, or not on PATH.
    echo.
    echo         Please install Python 3.10 or newer from:
    echo             https://www.python.org/downloads/
    echo.
    echo         During installation tick the box "Add Python to PATH".
    echo         Then double-click start.bat again.
    echo.
    pause
    exit /b 1
)

REM ---- 2. First-run install: create .venv and pip install ----
if not exist ".venv\Scripts\python.exe" (
    echo [First run] .venv not found. Installing now...
    echo             This takes 2-5 minutes and only happens once.
    echo.
    %BOOTPY% -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to create virtual environment.
        echo         Check the traceback above.
        pause
        exit /b 1
    )
    echo [Install] Upgrading pip...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    echo.
    echo [Install] Installing dependencies from requirements.txt...
    echo           (pandas/matplotlib/langgraph etc. will be downloaded)
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install dependencies. See messages above.
        echo         Common causes:
        echo           - No internet / corporate proxy blocking pip
        echo           - Antivirus quarantined a wheel
        echo         Delete the .venv\ folder and double-click start.bat again.
        pause
        exit /b 1
    )
    echo.
    echo [Install] Done. Launching...
    echo.
)

REM ---- 3. Copy .env on first run ----
if not exist ".env" (
    if exist ".env.example" copy /Y ".env.example" ".env" >nul
)

REM ---- 4. Hand over to launch.py (readiness + browser + Ctrl+C handling) ----
".venv\Scripts\python.exe" launch.py
set "RC=%errorlevel%"

if not "%RC%"=="0" (
    echo.
    echo [ERROR] Launcher exited with code %RC%.
    echo See the messages above for details.
    pause
)

endlocal
