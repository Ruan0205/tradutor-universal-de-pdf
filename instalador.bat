@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1

set "NOPAUSE=0"
set "ALREADY_ELEVATED=0"
for %%A in (%*) do (
    if /I "%%~A"=="nopause" set "NOPAUSE=1"
    if /I "%%~A"=="elevated" set "ALREADY_ELEVATED=1"
)

set "SELF=%~f0"
call :set_paths

title Instalador - Tradutor Universal de PDF v1.9

echo.
echo ================================================================
echo   INSTALADOR AUTOMATICO v1.9
echo   Tradutor Universal de PDF
echo ================================================================
echo.
echo Este instalador prepara automaticamente:
echo - Python (venv local no projeto)
echo - Dependencias Python
echo - Pacote de fontes extras para reconstrucao visual
echo - Ollama (opcional) e modelo de traducao
echo.
if "!NOPAUSE!"=="0" pause

call :ensure_admin
if !errorlevel! equ 2 exit /b 0
if !errorlevel! neq 0 goto :fatal

call :main
if !errorlevel! neq 0 goto :fatal
goto :success

:main
echo.
echo [1/6] Localizando Python...
call :find_python
if !errorlevel! neq 0 call :install_portable_python
if !errorlevel! neq 0 exit /b 1

for /f "tokens=*" %%v in ('"!PYTHON_EXE!" --version 2^>^&1') do set "PY_VER=%%v"
echo    OK: !PY_VER!
echo    Path: !PYTHON_EXE!

if not exist "!ENGINE_DIR!" mkdir "!ENGINE_DIR!"
echo !PYTHON_EXE!>"!PYTHON_PATH_FILE!"

echo.
echo [2/6] Preparando ambiente virtual...
if exist "!VENV_DIR!\Scripts\python.exe" (
    set "VENV_PYTHON=!VENV_DIR!\Scripts\python.exe"
    set "VENV_PIP=!VENV_DIR!\Scripts\pip.exe"
    echo    Ambiente virtual ja existe.
) else (
    "!PYTHON_EXE!" -m venv "!VENV_DIR!" >nul 2>&1
    if !errorlevel! neq 0 (
        echo    venv nativo indisponivel. Tentando virtualenv...
        "!PYTHON_EXE!" -m pip install virtualenv --quiet
        if !errorlevel! equ 0 "!PYTHON_EXE!" -m virtualenv "!VENV_DIR!"
    )

    if not exist "!VENV_DIR!\Scripts\python.exe" (
        echo    ERRO: falha ao criar ambiente virtual.
        exit /b 1
    )

    set "VENV_PYTHON=!VENV_DIR!\Scripts\python.exe"
    set "VENV_PIP=!VENV_DIR!\Scripts\pip.exe"
    echo    Ambiente virtual criado.
)

echo.
echo [3/6] Instalando pacotes Python...
"!VENV_PIP!" install --upgrade pip >nul 2>&1
"!VENV_PIP!" install --upgrade PyMuPDF Pillow rapidocr-onnxruntime tqdm pystray opencv-python onnxruntime
if !errorlevel! neq 0 (
    echo    ERRO: falha na instalacao de dependencias Python.
    exit /b 1
)
echo    Dependencias base instaladas.

echo    Tentando habilitar backend GPU via DirectML (Windows 10+ AMD/NVIDIA/Intel)...
"!VENV_PIP!" install --upgrade onnxruntime-directml >nul 2>&1
if !errorlevel! neq 0 (
    echo    Aviso: DirectML nao disponivel neste ambiente. OCR permanecera em CPU por padrao.
) else (
    echo    DirectML instalado com sucesso. Voce pode selecionar GPU nas Configuracoes.
)
echo ok>"!DEPS_FILE!"
echo    Dependencias instaladas.

echo.
echo [4/6] Verificando Ollama...
call :find_ollama
if !errorlevel! neq 0 (
    echo    Ollama nao encontrado.
    set "INSTALL_OLLAMA="
    set /p INSTALL_OLLAMA="    Deseja instalar agora? (S/N): "
    if /I "!INSTALL_OLLAMA!"=="S" (
        call :install_ollama
        call :find_ollama
    )
)

if defined OLLAMA_EXE (
    echo    Baixando modelo principal: !OLLAMA_MODEL_PRIMARY!
    "!OLLAMA_EXE!" pull !OLLAMA_MODEL_PRIMARY!
    if !errorlevel! neq 0 (
        echo    Falha no principal. Tentando fallback: !OLLAMA_MODEL_FALLBACK!
        "!OLLAMA_EXE!" pull !OLLAMA_MODEL_FALLBACK!
        if !errorlevel! neq 0 (
            echo    Aviso: nao foi possivel baixar modelo automaticamente.
            echo    Execute manualmente depois:
            echo      "!OLLAMA_EXE!" pull !OLLAMA_MODEL_PRIMARY!
            echo      "!OLLAMA_EXE!" pull !OLLAMA_MODEL_FALLBACK!
        ) else (
            echo    Modelo fallback instalado com sucesso.
        )
    ) else (
        echo    Modelo principal instalado com sucesso.
    )
) else (
    echo    Aviso: sem Ollama, a traducao com IA nao funcionara.
)

echo.
echo [5/6] Instalando pacote de fontes...
call :install_font_pack
echo.
echo [6/6] Criando estrutura de pastas...
if not exist "!INPUT_DIR!" mkdir "!INPUT_DIR!"
if not exist "!OUTPUT_DIR!" mkdir "!OUTPUT_DIR!"
if not exist "!ORIGINALS_DIR!" mkdir "!ORIGINALS_DIR!"
if not exist "!WORKING_DIR!" mkdir "!WORKING_DIR!"
echo    Estrutura pronta.

exit /b 0

:set_paths
cd /d "%~dp0"
for %%I in (.) do set "PROJECT_DIR=%%~fI"
set "ENGINE_DIR=!PROJECT_DIR!\engine"
set "VENV_DIR=!PROJECT_DIR!\.venv"
set "PYTHON_PORTABLE_DIR=!PROJECT_DIR!\python-portable"
set "PYTHON_EMBEDDED_ZIP=%TEMP%\python-embedded.zip"
set "PYTHON_VERSION=3.11.9"
set "PYTHON_EMBEDDED_URL=https://www.python.org/ftp/python/!PYTHON_VERSION!/python-!PYTHON_VERSION!-embed-amd64.zip"
set "PYTHON_PATH_FILE=!ENGINE_DIR!\.python_path"
set "DEPS_FILE=!ENGINE_DIR!\.deps_installed"
set "INPUT_DIR=!PROJECT_DIR!\livros-para-traduzir"
set "OUTPUT_DIR=!PROJECT_DIR!\traduzidos"
set "ORIGINALS_DIR=!PROJECT_DIR!\na-lingua-anterior"
set "WORKING_DIR=!PROJECT_DIR!\traduzindo"
set "FONT_PACK_DIR=!PROJECT_DIR!\assets\fonts"
set "OLLAMA_EXE="
set "OLLAMA_MODEL_PRIMARY=translategemma"
set "OLLAMA_MODEL_FALLBACK=TranslateGemma"
exit /b 0

:ensure_admin
net session >nul 2>&1
if !errorlevel! equ 0 exit /b 0

if "!ALREADY_ELEVATED!"=="1" (
    echo.
    echo Aviso: sem privilegios de administrador. Continuando em modo portatil.
    exit /b 0
)

echo.
echo Solicitando elevacao de privilegios...
set "RELAUNCH_ARGS=elevated"
if "!NOPAUSE!"=="1" set "RELAUNCH_ARGS=!RELAUNCH_ARGS! nopause"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'cmd.exe' -Verb RunAs -ArgumentList '/c','""!SELF!" !RELAUNCH_ARGS!"'"
if !errorlevel! equ 0 exit /b 2

echo Aviso: elevacao negada. Continuando sem admin.
exit /b 0

:find_python
set "PYTHON_EXE="

if exist "!VENV_DIR!\Scripts\python.exe" (
    call :verify_python "!VENV_DIR!\Scripts\python.exe"
    if !errorlevel! equ 0 set "PYTHON_EXE=!VENV_DIR!\Scripts\python.exe"
)
if defined PYTHON_EXE exit /b 0

if exist "!PYTHON_PORTABLE_DIR!\python.exe" (
    call :verify_python "!PYTHON_PORTABLE_DIR!\python.exe"
    if !errorlevel! equ 0 set "PYTHON_EXE=!PYTHON_PORTABLE_DIR!\python.exe"
)
if defined PYTHON_EXE exit /b 0

for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
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

:verify_python
set "TEST_PY=%~1"
"%~1" --version >nul 2>&1
exit /b %errorlevel%

:install_portable_python
echo.
echo Python nao encontrado. Instalando Python portatil no projeto...

if not exist "!PYTHON_PORTABLE_DIR!" mkdir "!PYTHON_PORTABLE_DIR!"
del /f /q "!PYTHON_EMBEDDED_ZIP!" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('!PYTHON_EMBEDDED_URL!','!PYTHON_EMBEDDED_ZIP!')"
if not exist "!PYTHON_EMBEDDED_ZIP!" (
    echo    ERRO: falha no download do Python embedded.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '!PYTHON_EMBEDDED_ZIP!' -DestinationPath '!PYTHON_PORTABLE_DIR!' -Force"
del /f /q "!PYTHON_EMBEDDED_ZIP!" >nul 2>&1

if exist "!PYTHON_PORTABLE_DIR!\python311._pth" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content '!PYTHON_PORTABLE_DIR!\python311._pth') -replace '#import site','import site' | Set-Content '!PYTHON_PORTABLE_DIR!\python311._pth'"
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py','!PYTHON_PORTABLE_DIR!\get-pip.py')"
if exist "!PYTHON_PORTABLE_DIR!\get-pip.py" (
    "!PYTHON_PORTABLE_DIR!\python.exe" "!PYTHON_PORTABLE_DIR!\get-pip.py" --no-warn-script-location
    del /f /q "!PYTHON_PORTABLE_DIR!\get-pip.py" >nul 2>&1
)

call :verify_python "!PYTHON_PORTABLE_DIR!\python.exe"
if !errorlevel! neq 0 exit /b 1
set "PYTHON_EXE=!PYTHON_PORTABLE_DIR!\python.exe"
echo    Python portatil instalado.
exit /b 0

:find_ollama
set "OLLAMA_EXE="
where ollama >nul 2>&1
if !errorlevel! equ 0 (
    set "OLLAMA_EXE=ollama"
    exit /b 0
)

for %%O in (
    "%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    "%LOCALAPPDATA%\Ollama\ollama.exe"
    "C:\Program Files\Ollama\ollama.exe"
) do (
    if exist "%%~fO" (
        set "OLLAMA_EXE=%%~fO"
        exit /b 0
    )
)

exit /b 1

:install_ollama
set "OLLAMA_INSTALLER=%TEMP%\OllamaSetup.exe"
del /f /q "!OLLAMA_INSTALLER!" >nul 2>&1

echo    Baixando instalador do Ollama...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://ollama.com/download/OllamaSetup.exe','!OLLAMA_INSTALLER!')"
if not exist "!OLLAMA_INSTALLER!" (
    echo    Falha no download do Ollama.
    exit /b 1
)

echo    Executando instalacao do Ollama...
start /wait "" "!OLLAMA_INSTALLER!" /VERYSILENT
del /f /q "!OLLAMA_INSTALLER!" >nul 2>&1
exit /b 0

:install_font_pack
if not exist "!FONT_PACK_DIR!" mkdir "!FONT_PACK_DIR!" >nul 2>&1
echo    Pasta de fontes: !FONT_PACK_DIR!

call :download_font "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf" "NotoSans-Regular.ttf"
call :download_font "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf" "NotoSans-Bold.ttf"
call :download_font "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Italic.ttf" "NotoSans-Italic.ttf"
call :download_font "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSerif/NotoSerif-Regular.ttf" "NotoSerif-Regular.ttf"
call :download_font "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSerif/NotoSerif-Bold.ttf" "NotoSerif-Bold.ttf"
call :download_font "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansMono/NotoSansMono-Regular.ttf" "NotoSansMono-Regular.ttf"
call :download_font "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansMono/NotoSansMono-Bold.ttf" "NotoSansMono-Bold.ttf"

echo    Pacote de fontes atualizado.
exit /b 0

:download_font
set "FONT_URL=%~1"
set "FONT_NAME=%~2"
set "FONT_DEST=!FONT_PACK_DIR!\!FONT_NAME!"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%~1','!FONT_DEST!') } catch { exit 1 }"
if exist "!FONT_DEST!" (
    echo      OK !FONT_NAME!
) else (
    echo      Aviso: falha ao baixar !FONT_NAME! (continua com fontes locais)
)
exit /b 0

:success
echo.
echo ================================================================
echo   INSTALACAO CONCLUIDA COM SUCESSO (v1.9)
echo ================================================================
echo 1. Execute iniciar.bat
echo 2. Abra o dashboard no navegador
echo 3. Coloque PDFs em livros-para-traduzir
echo.
if "!NOPAUSE!"=="0" pause
exit /b 0

:fatal
echo.
echo ================================================================
echo   ERRO: instalacao interrompida.
echo ================================================================
echo Se necessario, mova o projeto para um caminho simples,
echo ex: C:\TradutorUniversalPDF\
echo.
if "!NOPAUSE!"=="0" pause
exit /b 1
