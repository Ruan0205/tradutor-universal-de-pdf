@echo off
chcp 65001 >nul 2>&1
title Tradutor Universal de PDF

cd /d "%~dp0"

:: Try venv python first
if exist "..\..\.venv\Scripts\python.exe" (
    ..\..\.venv\Scripts\python.exe iniciar.py
) else if exist "%~dp0..\.venv\Scripts\python.exe" (
    "%~dp0..\.venv\Scripts\python.exe" iniciar.py
) else (
    python iniciar.py
)

pause
