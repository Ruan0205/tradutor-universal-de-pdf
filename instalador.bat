@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ============================================================================
:: INSTALADOR AUTOMÁTICO - TRADUTOR UNIVERSAL DE PDF
:: ============================================================================
:: Este script verifica e instala automaticamente TODAS as dependências:
:: - Python 3.11.x
:: - Ambiente virtual (venv)
:: - Pacotes Python necessários
:: - Ollama (opcional, mas recomendado)
:: ============================================================================

title Instalador - Tradutor Universal de PDF

:: Previne o fechamento imediato em caso de erro
if "%1"=="nopause" (
    set NOPAUSE=1
) else (
    set NOPAUSE=0
)

cls
echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║                                                               ║
echo ║        📦 INSTALADOR AUTOMÁTICO v1.5 📦                      ║
echo ║                                                               ║
echo ║        Tradutor Universal de PDF - Sistema de IA             ║
echo ║                                                               ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
echo.
echo ⚠️  ATENÇÃO: Este instalador precisa de permissões de ADMINISTRADOR
echo    para instalar o Python e outras dependências do sistema.
echo.
echo    Se você ainda não executou como administrador:
echo    1. Clique com botão direito neste arquivo
echo    2. Selecione "Executar como administrador"
echo.
echo ═══════════════════════════════════════════════════════════════
echo.
echo    Preparando instalação...
echo.
pause
echo.

:: Muda para o diretório do script
cd /d "%~dp0"
set "PROJECT_DIR=%~dp0"
set "BASE_DIR=%PROJECT_DIR%.."
set "VENV_DIR=%BASE_DIR%\.venv"
set "PYTHON_INSTALLER=%TEMP%\python-installer.exe"
set "PYTHON_PORTABLE_DIR=%PROJECT_DIR%python-portable"
set "PYTHON_EMBEDDED_ZIP=%TEMP%\python-embedded.zip"
set "PYTHON_VERSION=3.11.9"
set "OLLAMA_MODEL_PRIMARY=translategemmma"
set "OLLAMA_MODEL_FALLBACK=translategemma"
set "OLLAMA_EXE=ollama"

:: ============================================================================
:: INÍCIO DO FLUXO PRINCIPAL
:: ============================================================================
goto :main

:: ============================================================================
:: FUNÇÕES AUXILIARES
:: ============================================================================

:verify_python
:: Verifica se o Python passado como parâmetro é real e funcional
set "TEST_PYTHON=%~1"
"%TEST_PYTHON%" --version >nul 2>&1
exit /b %errorlevel%

:: ============================================================================
:: ETAPA 1: VERIFICAR E INSTALAR PYTHON
:: ============================================================================

:main
echo [1/5] Verificando Python...
echo.

:: Tenta encontrar Python no venv primeiro
if exist "%VENV_DIR%\Scripts\python.exe" (
    set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
    echo ✅ Python encontrado no ambiente virtual
    goto :check_version
)

:: Procura Python portável no próprio projeto
if exist "%PROJECT_DIR%python-portable\python.exe" (
    set "PYTHON_EXE=%PROJECT_DIR%python-portable\python.exe"
    echo ✅ Python portável encontrado no projeto
    goto :check_version
)

:: Procura Python no PATH comum do Windows (locais específicos primeiro)
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "C:\Python311\python.exe"
    "C:\Python312\python.exe"
    "C:\Python310\python.exe"
    "C:\Python313\python.exe"
) do (
    if exist %%P (
        call :verify_python %%P
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=%%P"
            goto :check_version
        )
    )
)

:: Tenta encontrar Python no PATH do sistema (EVITANDO WindowsApps/Microsoft Store)
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('where python') do (
        set "TEMP_PYTHON=%%i"
        echo    Verificando: !TEMP_PYTHON!
        
        :: Ignora o alias falso da Microsoft Store
        echo !TEMP_PYTHON! | find /i "WindowsApps" >nul
        if !errorlevel! neq 0 (
            call :verify_python "!TEMP_PYTHON!"
            if !errorlevel! equ 0 (
                set "PYTHON_EXE=!TEMP_PYTHON!"
                goto :check_version
            )
        ) else (
            echo    ⚠️  Ignorando alias da Microsoft Store
        )
    )
)

:: Python não encontrado - precisa instalar
echo ❌ Python não encontrado no sistema
echo.
echo 📦 Instalando Python PORTÁVEL no projeto...
echo    (Isso torna o projeto 100%% portável - pode copiar para outros PCs!)
echo.
echo 📥 Baixando Python %PYTHON_VERSION% Embedded...
echo    (Isso pode levar alguns minutos)
echo.

:: URL do Python Embedded (versão portável)
set "PYTHON_EMBEDDED_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip"

:: Baixa usando PowerShell
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Write-Host '   Baixando...'; (New-Object Net.WebClient).DownloadFile('%PYTHON_EMBEDDED_URL%', '%PYTHON_EMBEDDED_ZIP%'); Write-Host '   Download concluído!'}"

if not exist "%PYTHON_EMBEDDED_ZIP%" (
    echo.
    echo ❌ ERRO: Não foi possível baixar o Python Embedded
    echo    Verifique sua conexão com a internet
    echo.
    echo    ALTERNATIVA: Baixe o Python Embedded manualmente:
    echo    %PYTHON_EMBEDDED_URL%
    echo.
    echo    Extraia para: %PYTHON_PORTABLE_DIR%
    pause
    exit /b 1
)

echo.
echo ⏳ Extraindo Python portável...

:: Cria o diretório se não existir
if not exist "%PYTHON_PORTABLE_DIR%" mkdir "%PYTHON_PORTABLE_DIR%"

:: Extrai o ZIP usando PowerShell
powershell -Command "& {Expand-Archive -Path '%PYTHON_EMBEDDED_ZIP%' -DestinationPath '%PYTHON_PORTABLE_DIR%' -Force}"

:: Remove o arquivo ZIP
del "%PYTHON_EMBEDDED_ZIP%" >nul 2>&1

:: Configura o Python Embedded para funcionar com pip
echo.
echo ⚙️  Configurando Python portável...

:: Descomenta as linhas de import site no python311._pth
if exist "%PYTHON_PORTABLE_DIR%\python311._pth" (
    powershell -Command "(Get-Content '%PYTHON_PORTABLE_DIR%\python311._pth') -replace '#import site', 'import site' | Set-Content '%PYTHON_PORTABLE_DIR%\python311._pth'"
)

:: Baixa e instala o get-pip.py
echo    Instalando pip no Python portátil...
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py', '%PYTHON_PORTABLE_DIR%\get-pip.py')}"

if exist "%PYTHON_PORTABLE_DIR%\get-pip.py" (
    "%PYTHON_PORTABLE_DIR%\python.exe" "%PYTHON_PORTABLE_DIR%\get-pip.py" --no-warn-script-location
    del "%PYTHON_PORTABLE_DIR%\get-pip.py" >nul 2>&1
)

echo.
echo ✅ Python portável instalado com sucesso!
echo    Local: %PYTHON_PORTABLE_DIR%
echo.
echo    💡 VANTAGEM: Agora você pode copiar a pasta inteira do projeto
echo       para outro computador e funcionará imediatamente!
echo.

set "PYTHON_EXE=%PYTHON_PORTABLE_DIR%\python.exe"
goto :check_version

:check_version
echo.
for /f "tokens=*" %%i in ('"%PYTHON_EXE%" --version 2^>^&1') do set PYTHON_VERSION_STR=%%i
echo    Versão: %PYTHON_VERSION_STR%
echo    Local: %PYTHON_EXE%
echo.

:: Cria o diretório engine se não existir
if not exist "%PROJECT_DIR%engine" mkdir "%PROJECT_DIR%engine"

:: Salva o caminho do Python em um arquivo de configuração para uso rápido
echo %PYTHON_EXE%> "%PROJECT_DIR%engine\.python_path"

:: ============================================================================
:: ETAPA 2: CRIAR AMBIENTE VIRTUAL
:: ============================================================================

echo [2/5] Verificando ambiente virtual...
echo.

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo ✅ Ambiente virtual já existe
    set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
    set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
) else (
    echo ⏳ Criando ambiente virtual...
    
    :: Tenta criar o venv com o módulo venv nativo
    "%PYTHON_EXE%" -m venv "%VENV_DIR%" >nul 2>&1
    
    if !errorlevel! neq 0 (
        echo    ⚠️  Módulo venv não disponível, instalando virtualenv...
        "%PYTHON_EXE%" -m pip install virtualenv --quiet
        
        if !errorlevel! equ 0 (
            echo    ⏳ Criando ambiente virtual com virtualenv...
            "%PYTHON_EXE%" -m virtualenv "%VENV_DIR%"
        ) else (
            echo    ❌ Erro ao instalar virtualenv
            echo       Tentando criar venv de forma alternativa...
            
            :: Se for Python portável, tenta instalar pip primeiro
            if exist "%PYTHON_PORTABLE_DIR%\python.exe" (
                echo       Configurando pip no Python portátil...
                powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py', '%TEMP%\get-pip.py')}"
                "%PYTHON_EXE%" "%TEMP%\get-pip.py" --no-warn-script-location
                del "%TEMP%\get-pip.py" >nul 2>&1
                
                :: Tenta novamente
                "%PYTHON_EXE%" -m pip install virtualenv --quiet
                "%PYTHON_EXE%" -m virtualenv "%VENV_DIR%"
            )
        )
    )
    
    if exist "%VENV_DIR%\Scripts\python.exe" (
        echo ✅ Ambiente virtual criado com sucesso
        set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
        set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
    ) else (
        echo ❌ ERRO: Não foi possível criar o ambiente virtual
        echo.
        echo    Possíveis soluções:
        echo    1. Execute este script como ADMINISTRADOR
        echo    2. Desinstale o Python atual e execute novamente
        echo    3. Verifique se há espaço em disco suficiente
        pause
        exit /b 1
    )
)

echo.

:: ============================================================================
:: ETAPA 3: INSTALAR PACOTES PYTHON
:: ============================================================================

echo [3/5] Instalando pacotes Python necessários...
echo.

echo ⏳ Atualizando pip...
"%VENV_PIP%" install --upgrade pip >nul 2>&1

echo ⏳ Instalando PyMuPDF...
"%VENV_PIP%" install PyMuPDF

echo ⏳ Instalando Pillow...
"%VENV_PIP%" install Pillow

echo ⏳ Instalando rapidocr-onnxruntime...
"%VENV_PIP%" install rapidocr-onnxruntime

echo ⏳ Instalando tqdm...
"%VENV_PIP%" install tqdm

echo.
echo ✅ Todos os pacotes Python instalados!
echo.

:: Criar flag de dependências instaladas
if not exist "%PROJECT_DIR%engine" mkdir "%PROJECT_DIR%engine"
echo ok > "%PROJECT_DIR%engine\.deps_installed"

:: ============================================================================
:: ETAPA 4: VERIFICAR OLLAMA
:: ============================================================================

echo [4/5] Verificando Ollama (IA para tradução)...
echo.

where ollama >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Ollama encontrado
    set "OLLAMA_EXE=ollama"
    goto :pull_ollama_model
)

:: Verifica em locais comuns
set "OLLAMA_PATH="
for %%O in (
    "%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    "%LOCALAPPDATA%\Ollama\ollama.exe"
    "C:\Program Files\Ollama\ollama.exe"
) do (
    if exist %%O (
        set "OLLAMA_PATH=%%O"
        set "OLLAMA_EXE=%%O"
        echo ✅ Ollama encontrado em %%O
        goto :pull_ollama_model
    )
)

echo ⚠️  Ollama não encontrado
echo.
echo    O Ollama é necessário para tradução com IA.
echo.
set /p INSTALL_OLLAMA="    Deseja instalar o Ollama agora? (S/N): "

if /i "!INSTALL_OLLAMA!"=="S" (
    echo.
    echo 📥 Baixando Ollama...
    
    set "OLLAMA_INSTALLER=%TEMP%\OllamaSetup.exe"
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://ollama.com/download/OllamaSetup.exe', '!OLLAMA_INSTALLER!')}"
    
    if exist "!OLLAMA_INSTALLER!" (
        echo.
        echo ⏳ Instalando Ollama...
        echo    (Uma janela de instalação será aberta)
        start /wait "" "!OLLAMA_INSTALLER!" /VERYSILENT
        del "!OLLAMA_INSTALLER!" >nul 2>&1
        echo ✅ Ollama instalado!
        
        :: Detecta o executável do Ollama após instalação
        if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
        if exist "%LOCALAPPDATA%\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Ollama\ollama.exe"
        if exist "C:\Program Files\Ollama\ollama.exe" set "OLLAMA_EXE=C:\Program Files\Ollama\ollama.exe"
        goto :pull_ollama_model
    ) else (
        echo ❌ Não foi possível baixar o Ollama
        echo    Você pode instalá-lo manualmente depois de: https://ollama.com/download
    )
) else (
    echo.
    echo    ℹ️  Você pode instalar o Ollama depois de: https://ollama.com/download
    echo    O sistema não funcionará sem o Ollama.
)

echo.
goto :create_dirs

:pull_ollama_model
echo.
echo ⏳ Baixando modelo do Ollama automaticamente...
echo    Modelo solicitado: %OLLAMA_MODEL_PRIMARY%

"%OLLAMA_EXE%" pull %OLLAMA_MODEL_PRIMARY%
if %errorlevel% neq 0 (
    echo ⚠️  Falha ao baixar '%OLLAMA_MODEL_PRIMARY%'. Tentando fallback '%OLLAMA_MODEL_FALLBACK%'...
    "%OLLAMA_EXE%" pull %OLLAMA_MODEL_FALLBACK%
    if %errorlevel% neq 0 (
        echo ⚠️  Não foi possível baixar o modelo automaticamente agora.
        echo    Execute depois manualmente:
        echo    "%OLLAMA_EXE%" pull %OLLAMA_MODEL_PRIMARY%
        echo    ou
        echo    "%OLLAMA_EXE%" pull %OLLAMA_MODEL_FALLBACK%
    ) else (
        echo ✅ Modelo '%OLLAMA_MODEL_FALLBACK%' baixado com sucesso!
    )
) else (
    echo ✅ Modelo '%OLLAMA_MODEL_PRIMARY%' baixado com sucesso!
)

echo.

:: ============================================================================
:: ETAPA 5: CRIAR DIRETÓRIOS NECESSÁRIOS
:: ============================================================================

:create_dirs
echo [5/5] Criando estrutura de pastas...
echo.

if not exist "%BASE_DIR%\livros-para-traduzir" mkdir "%BASE_DIR%\livros-para-traduzir"
if not exist "%BASE_DIR%\traduzidos" mkdir "%BASE_DIR%\traduzidos"
if not exist "%BASE_DIR%\em-inges" mkdir "%BASE_DIR%\em-inges"
if not exist "%BASE_DIR%\traduzindo" mkdir "%BASE_DIR%\traduzindo"

echo ✅ Estrutura de pastas criada
echo.

:: ============================================================================
:: INSTALAÇÃO CONCLUÍDA
:: ============================================================================

echo.
echo ═══════════════════════════════════════════════════════════════
echo.
echo ✅ INSTALAÇÃO CONCLUÍDA COM SUCESSO!
echo.
echo    Agora você pode usar o sistema:
echo    1. Execute o arquivo "iniciar.bat"
echo    2. O dashboard será aberto automaticamente
echo    3. Coloque seus PDFs na pasta "livros-para-traduzir"
echo    4. Clique em "Iniciar" no dashboard
echo.
echo ═══════════════════════════════════════════════════════════════
echo.
pause

exit /b 0
