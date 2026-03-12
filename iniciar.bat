@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Tradutor Universal de PDF v2.0.1

set "NOPAUSE=0"
for %%A in (%*) do (
    if /I "%%~A"=="nopause" set "NOPAUSE=1"
)

call :set_paths

echo.
echo ================================================================
echo   TRADUTOR UNIVERSAL DE PDF v2.0.1
echo ================================================================
echo.

call :find_python
if !errorlevel! neq 0 goto :python_missing

set "PYTHONW_EXE=!PYTHON_EXE:python.exe=pythonw.exe!"
if exist "!PYTHONW_EXE!" (
    start "" "!PYTHONW_EXE!" "!PROJECT_DIR!\iniciar.py" --tray
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath '!PYTHON_EXE!' -ArgumentList '\"!PROJECT_DIR!\\iniciar.py\"','--tray'"
)

if "!NOPAUSE!"=="0" (
    echo Sistema iniciado em segundo plano.
    echo Dashboard: http://localhost:8050/
    timeout /t 2 >nul
)
exit /b 0

:set_paths
cd /d "%~dp0"
for %%I in (.) do set "PROJECT_DIR=%%~fI"
set "VENV_DIR=!PROJECT_DIR!\.venv"
set "PYTHON_CONFIG=!PROJECT_DIR!\engine\.python_path"
set "PYTHON_EXE="
exit /b 0

:verify_python
"%~1" --version >nul 2>&1
exit /b %errorlevel%

:find_python
if exist "!VENV_DIR!\Scripts\python.exe" (
    call :verify_python "!VENV_DIR!\Scripts\python.exe"
    if !errorlevel! equ 0 set "PYTHON_EXE=!VENV_DIR!\Scripts\python.exe"
)
if defined PYTHON_EXE exit /b 0

if exist "!PYTHON_CONFIG!" (
    for /f "usebackq delims=" %%I in ("!PYTHON_CONFIG!") do set "SAVED_PYTHON=%%I"
    if defined SAVED_PYTHON (
        if exist "!SAVED_PYTHON!" (
            call :verify_python "!SAVED_PYTHON!"
            if !errorlevel! equ 0 set "PYTHON_EXE=!SAVED_PYTHON!"
        )
    )
)
if defined PYTHON_EXE exit /b 0

if exist "!PROJECT_DIR!\python-portable\python.exe" (
    call :verify_python "!PROJECT_DIR!\python-portable\python.exe"
    if !errorlevel! equ 0 set "PYTHON_EXE=!PROJECT_DIR!\python-portable\python.exe"
)
if defined PYTHON_EXE exit /b 0

for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "C:\Python39\python.exe"
) do (
    if exist "%%~fP" (
        call :verify_python "%%~fP"
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=%%~fP"
            goto :find_python_done
        )
    )
)

where python >nul 2>&1
if !errorlevel! equ 0 (
    for /f "usebackq delims=" %%I in (`where python`) do (
        set "CANDIDATE=%%~fI"
        echo !CANDIDATE! | find /I "WindowsApps" >nul
        if !errorlevel! neq 0 (
            call :verify_python "!CANDIDATE!"
            if !errorlevel! equ 0 (
                set "PYTHON_EXE=!CANDIDATE!"
                goto :find_python_done
            )
        )
    )
)

:find_python_done
if defined PYTHON_EXE exit /b 0
exit /b 1

:python_missing
echo.
echo ERRO: Python nao encontrado.
echo Execute instalador.bat primeiro.
echo.
if "!NOPAUSE!"=="0" pause
exit /b 1

:run_error
echo.
echo ERRO ao iniciar o sistema.
echo Se for a primeira execucao, rode instalador.bat.
echo.
if "!NOPAUSE!"=="0" pause
exit /b 1
