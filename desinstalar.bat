@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title Desinstalar - Tradutor Universal de PDF

cls
echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║                                                               ║
echo ║        🗑️  DESINSTALADOR - TRADUTOR UNIVERSAL DE PDF 🗑️       ║
echo ║                                                               ║
echo ║        Remove todos os componentes instalados                ║
echo ║                                                               ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
echo.

:: Muda para o diretório do script
cd /d "%~dp0"
set "PROJECT_DIR=%~dp0"
set "BASE_DIR=%PROJECT_DIR%"

echo  ⚠️  ATENÇÃO: Este processo irá remover:
echo.
echo     • Ambiente virtual Python (.venv)
echo     • Python portável (se instalado pelo instalador)
echo     • Arquivos de configuração e estado
echo     • Logs de tradução e validação
echo     • Cache de dependências
echo.
echo  ℹ️  NÃO serão removidos:
echo.
echo     • PDFs na fila (livros-para-traduzir)
echo     • PDFs traduzidos (traduzidos)
echo     • PDFs originais salvos (na-lingua-anterior)
echo     • Ollama (instalado separadamente no sistema)
echo.
echo ═══════════════════════════════════════════════════════════════
echo.

set /p CONFIRM="  Deseja continuar com a desinstalação? (S/N): "
if /i not "!CONFIRM!"=="S" (
    echo.
    echo  ❌ Desinstalação cancelada.
    echo.
    pause
    exit /b 0
)

echo.
echo ═══════════════════════════════════════════════════════════════
echo.

:: ============================================================================
:: ETAPA 1: Encerrar processos Python do projeto
:: ============================================================================

echo [1/6] Encerrando processos do tradutor...
echo.

:: Mata processos do servidor e pipeline
taskkill /F /FI "WINDOWTITLE eq Tradutor Universal de PDF" >nul 2>&1
if exist "%BASE_DIR%\.venv\Scripts\python.exe" (
    for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST 2^>nul ^| find "PID:"') do (
        wmic process where processid=%%i get commandline 2>nul | find /i "server.py" >nul && taskkill /F /PID %%i >nul 2>&1
        wmic process where processid=%%i get commandline 2>nul | find /i "pipeline.py" >nul && taskkill /F /PID %%i >nul 2>&1
        wmic process where processid=%%i get commandline 2>nul | find /i "validator.py" >nul && taskkill /F /PID %%i >nul 2>&1
    )
)
echo    ✅ Processos encerrados
echo.

:: ============================================================================
:: ETAPA 2: Remover ambiente virtual
:: ============================================================================

echo [2/6] Removendo ambiente virtual (.venv)...
echo.

if exist "%BASE_DIR%\.venv" (
    rmdir /S /Q "%BASE_DIR%\.venv" >nul 2>&1
    if exist "%BASE_DIR%\.venv" (
        echo    ⚠️  Alguns arquivos estão em uso. Tentando forçar...
        timeout /t 3 /nobreak >nul
        rmdir /S /Q "%BASE_DIR%\.venv" >nul 2>&1
    )
    if not exist "%BASE_DIR%\.venv" (
        echo    ✅ Ambiente virtual removido
    ) else (
        echo    ⚠️  Não foi possível remover completamente. Remova manualmente:
        echo       %BASE_DIR%\.venv
    )
) else (
    echo    ℹ️  Ambiente virtual não encontrado (já removido)
)
echo.

:: ============================================================================
:: ETAPA 3: Remover Python portável
:: ============================================================================

echo [3/6] Removendo Python portável...
echo.

if exist "%PROJECT_DIR%python-portable" (
    rmdir /S /Q "%PROJECT_DIR%python-portable" >nul 2>&1
    if not exist "%PROJECT_DIR%python-portable" (
        echo    ✅ Python portável removido
    ) else (
        echo    ⚠️  Não foi possível remover completamente
    )
) else (
    echo    ℹ️  Python portável não encontrado (já removido)
)
echo.

:: ============================================================================
:: ETAPA 4: Remover arquivos de configuração e estado
:: ============================================================================

echo [4/6] Removendo arquivos de configuração e estado...
echo.

:: Arquivos no engine/
if exist "%PROJECT_DIR%engine\pipeline_state.json" del /F /Q "%PROJECT_DIR%engine\pipeline_state.json" >nul 2>&1
if exist "%PROJECT_DIR%engine\pipeline_control.json" del /F /Q "%PROJECT_DIR%engine\pipeline_control.json" >nul 2>&1
if exist "%PROJECT_DIR%engine\server_port.txt" del /F /Q "%PROJECT_DIR%engine\server_port.txt" >nul 2>&1
if exist "%PROJECT_DIR%engine\.deps_installed" del /F /Q "%PROJECT_DIR%engine\.deps_installed" >nul 2>&1
if exist "%PROJECT_DIR%engine\.python_path" del /F /Q "%PROJECT_DIR%engine\.python_path" >nul 2>&1

echo    ✅ Arquivos de estado removidos
echo.

:: ============================================================================
:: ETAPA 5: Remover logs
:: ============================================================================

echo [5/6] Removendo logs...
echo.

if exist "%BASE_DIR%\translation.log" del /F /Q "%BASE_DIR%\translation.log" >nul 2>&1
if exist "%BASE_DIR%\validation_report.log" del /F /Q "%BASE_DIR%\validation_report.log" >nul 2>&1

echo    ✅ Logs removidos
echo.

:: ============================================================================
:: ETAPA 6: Remover pasta traduzindo (temporária)
:: ============================================================================

echo [6/6] Removendo pasta temporária (traduzindo)...
echo.

if exist "%BASE_DIR%\traduzindo" (
    rmdir /S /Q "%BASE_DIR%\traduzindo" >nul 2>&1
    echo    ✅ Pasta traduzindo removida
) else (
    echo    ℹ️  Pasta traduzindo não encontrada
)
echo.

:: ============================================================================
:: PERGUNTAR SOBRE PDFs
:: ============================================================================

echo ═══════════════════════════════════════════════════════════════
echo.
echo  Deseja também remover os PDFs? (traduzidos, originais e fila)
echo.
echo    ⚠️  CUIDADO: Isso apagará TODOS os seus PDFs traduzidos!
echo.

set /p REMOVE_PDFS="  Remover PDFs? (S/N): "
if /i "!REMOVE_PDFS!"=="S" (
    echo.
    if exist "%BASE_DIR%\livros-para-traduzir" (
        rmdir /S /Q "%BASE_DIR%\livros-para-traduzir" >nul 2>&1
        echo    ✅ Fila de tradução removida
    )
    if exist "%BASE_DIR%\traduzidos" (
        rmdir /S /Q "%BASE_DIR%\traduzidos" >nul 2>&1
        echo    ✅ PDFs traduzidos removidos
    )
    if exist "%BASE_DIR%\na-lingua-anterior" (
        rmdir /S /Q "%BASE_DIR%\na-lingua-anterior" >nul 2>&1
        echo    ✅ Originais na lingua anterior removidos
    )
    echo.
) else (
    echo.
    echo    ℹ️  PDFs preservados nas pastas originais
    echo.
)

:: ============================================================================
:: PERGUNTAR SOBRE CONFIG
:: ============================================================================

set /p REMOVE_CONFIG="  Remover configurações do Ollama (config.json)? (S/N): "
if /i "!REMOVE_CONFIG!"=="S" (
    if exist "%PROJECT_DIR%engine\config.json" del /F /Q "%PROJECT_DIR%engine\config.json" >nul 2>&1
    echo    ✅ config.json removido
    echo.
)

:: ============================================================================
:: PERGUNTAR SOBRE REMOÇÃO TOTAL DO PROJETO
:: ============================================================================

echo.
echo ═══════════════════════════════════════════════════════════════
echo.
echo  Deseja remover TODA a pasta do projeto?
echo.
echo    ⚠️  Isso apagará o próprio programa (código-fonte, scripts, etc.)
echo    A pasta inteira "%PROJECT_DIR%" será removida.
echo.

set /p REMOVE_ALL="  Remover todo o projeto? (S/N): "
if /i "!REMOVE_ALL!"=="S" (
    echo.
    echo    ⏳ Preparando remoção completa...
    echo    A pasta será removida após fechar esta janela.
    echo.
    
    :: Cria um script temporário que aguarda e remove tudo
    set "CLEANUP_SCRIPT=%TEMP%\tradutor_cleanup_%RANDOM%.bat"
    (
        echo @echo off
        echo timeout /t 3 /nobreak ^>nul
        echo rmdir /S /Q "%PROJECT_DIR%" ^>nul 2^>^&1
        echo rmdir /S /Q "%BASE_DIR%" ^>nul 2^>^&1
        echo del "%%~f0"
    ) > "!CLEANUP_SCRIPT!"
    
    echo ═══════════════════════════════════════════════════════════════
    echo.
    echo ✅ DESINSTALAÇÃO CONCLUÍDA!
    echo.
    echo    O projeto será removido em instantes.
    echo.
    echo ═══════════════════════════════════════════════════════════════
    echo.
    pause
    start /min "" cmd /c "!CLEANUP_SCRIPT!"
    exit /b 0
)

:: ============================================================================
:: FINALIZAÇÃO
:: ============================================================================

echo.
echo ═══════════════════════════════════════════════════════════════
echo.
echo ✅ DESINSTALAÇÃO CONCLUÍDA!
echo.
echo    Itens removidos:
echo    • Ambiente virtual (.venv)
echo    • Python portável
echo    • Arquivos de estado e logs
echo    • Pasta temporária (traduzindo)
echo.
echo    Para reinstalar, execute o "instalador.bat"
echo.
echo ═══════════════════════════════════════════════════════════════
echo.
pause
exit /b 0
