@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title Tradutor Universal de PDF

cls
echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║                                                               ║
echo ║          📚 TRADUTOR UNIVERSAL DE PDF v1.5 📚                  ║
echo ║                                                               ║
echo ║        Tradução Automática com IA - Ollama                   ║
echo ║                                                               ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
echo  ⚠️  IMPORTANTE: Para primeira execução ou instalação de
echo      dependências, execute como ADMINISTRADOR!
echo.
echo      Clique com botão direito no arquivo e selecione
echo      "Executar como administrador"
echo.
echo ═══════════════════════════════════════════════════════════════
echo.

:: Muda para o diretório do script (onde está o iniciar.bat)
cd /d "%~dp0"

set "PROJECT_DIR=%~dp0"
set "BASE_DIR=%PROJECT_DIR%.."
set "VENV_DIR=%BASE_DIR%\.venv"
set "PYTHON_EXE="
set "PYTHON_CONFIG=%PROJECT_DIR%engine\.python_path"

:: ============================================================================
:: INICIO DO FLUXO PRINCIPAL
:: ============================================================================
goto :main

:: ============================================================================
:: FUNÇÕES AUXILIARES
:: ============================================================================

:verify_python
:: Verifica se o Python é real (não o alias da MS Store)
set "TEST_PY=%~1"
"%TEST_PY%" --version >nul 2>&1
exit /b %errorlevel%

:: ============================================================================
:: BUSCAR PYTHON
:: ============================================================================

:main

:: 1. PRIORIDADE MÁXIMA: Python do ambiente virtual
if exist "%VENV_DIR%\Scripts\python.exe" (
    call :verify_python "%VENV_DIR%\Scripts\python.exe"
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
        goto :run_python
    )
)

:: 2. Usa o caminho salvo pelo instalador (se existir)
if exist "%PYTHON_CONFIG%" (
    for /f "usebackq delims=" %%i in ("%PYTHON_CONFIG%") do set "SAVED_PYTHON=%%i"
    if exist "!SAVED_PYTHON!" (
        call :verify_python "!SAVED_PYTHON!"
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=!SAVED_PYTHON!"
            goto :run_python
        )
    )
)

:: 3. Procura Python portável no projeto
if exist "%PROJECT_DIR%python-portable\python.exe" (
    call :verify_python "%PROJECT_DIR%python-portable\python.exe"
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=%PROJECT_DIR%python-portable\python.exe"
        goto :run_python
    )
)

:: 4. Procura Python em locais comuns do Windows (locais específicos)
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "C:\Python311\python.exe"
    "C:\Python312\python.exe"
    "C:\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python39\python.exe"
) do (
    if exist %%P (
        call :verify_python "%%~P"
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=%%~P"
            goto :run_python
        )
    )
)

:: 5. Procura no PATH do sistema (FILTRANDO o alias da Microsoft Store!)
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('where python') do (
        set "TEMP_PYTHON=%%i"
        
        :: Ignora completamente o alias falso da Microsoft Store/WindowsApps
        echo !TEMP_PYTHON! | find /i "WindowsApps" >nul
        if !errorlevel! neq 0 (
            call :verify_python "!TEMP_PYTHON!"
            if !errorlevel! equ 0 (
                set "PYTHON_EXE=!TEMP_PYTHON!"
                goto :run_python
            )
        )
    )
)

:: Python não encontrado
echo.
echo ═══════════════════════════════════════════════════════════════
echo.
echo ❌ ERRO: Python não encontrado no sistema!
echo.
echo    O Python é necessário para executar o Tradutor de PDF.
echo.
echo    🔧 SOLUÇÕES:
echo.
echo    1. Execute o arquivo "instalador.bat" como ADMINISTRADOR
echo       (Clique com botão direito ^> Executar como administrador)
echo.
echo       O instalador irá:
echo       - Baixar e instalar o Python automaticamente
echo       - Configurar o ambiente virtual
echo       - Instalar todas as dependências necessárias
echo.
echo    2. OU baixe e instale o Python manualmente:
echo       https://www.python.org/downloads/
echo       (Marque "Add Python to PATH" durante a instalação!)
echo.
echo ═══════════════════════════════════════════════════════════════
echo.
pause
exit /b 1

:: ============================================================================
:: EXECUTAR PYTHON
:: ============================================================================

:run_python
echo.
echo ⏳ Iniciando sistema...
echo    Python: !PYTHON_EXE!
echo.

"!PYTHON_EXE!" "%~dp0iniciar.py"

if %errorlevel% neq 0 (
    echo.
    echo ═══════════════════════════════════════════════════════════════
    echo.
    echo ⚠️  ERRO ao executar o sistema
    echo.
    echo    Se for a primeira vez executando, ou se faltam dependências,
    echo    execute o "instalador.bat" como ADMINISTRADOR.
    echo.
    echo ═══════════════════════════════════════════════════════════════
    echo.
)

pause
