#!/usr/bin/env python3
"""
Tradutor Universal de PDF - Inicializador
Verifica dependências, instala o necessário, e inicia o sistema.
"""

import os
import sys
import subprocess
import shutil
import json
import time
import socket
import urllib.request
import webbrowser
from pathlib import Path

# =====================================================================
# PATHS
# =====================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
ENGINE_DIR = SCRIPT_DIR / "engine"
BASE_DIR = SCRIPT_DIR
VENV_DIR = BASE_DIR / ".venv"
PYTHON_PORTABLE_DIR = SCRIPT_DIR / "python-portable"
PYTHON_CONFIG_FILE = ENGINE_DIR / ".python_path"
PYTHON_EXE = str(VENV_DIR / "Scripts" / "python.exe")
PIP_EXE = str(VENV_DIR / "Scripts" / "pip.exe")
SERVER_SCRIPT = str(ENGINE_DIR / "server.py")
PORT_FILE = ENGINE_DIR / "server_port.txt"
DEPS_DONE_FILE = ENGINE_DIR / ".deps_installed"

REQUIRED_PACKAGES = [
    "PyMuPDF",
    "Pillow",
    "rapidocr-onnxruntime",
    "tqdm",
]

OLLAMA_MODEL = "TranslateGemma"

# =====================================================================
# COLORS (Windows ANSI)
# =====================================================================

os.system("")  # Enable ANSI on Windows

def is_valid_python(python_path: str) -> bool:
    """Verifica se um executável Python é real e funcional (não o alias da MS Store)."""
    try:
        # Ignora o alias da Microsoft Store/WindowsApps
        if "WindowsApps" in python_path:
            return False
        
        # Verifica se o arquivo existe
        if not os.path.exists(python_path):
            return False
        
        # Tenta executar --version para validar
        result = subprocess.run(
            [python_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def find_valid_python() -> str:
    """Encontra um Python válido no sistema, ignorando aliases falsos."""
    # 1. Verifica o Python salvo pelo instalador
    if PYTHON_CONFIG_FILE.exists():
        saved_python = PYTHON_CONFIG_FILE.read_text().strip()
        if is_valid_python(saved_python):
            return saved_python
    
    # 2. Verifica Python portável no projeto
    python_portable = PYTHON_PORTABLE_DIR / "python.exe"
    if is_valid_python(str(python_portable)):
        return str(python_portable)
    
    # 3. Verifica locais comuns no Windows
    common_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python311" / "python.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python310" / "python.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python313" / "python.exe",
        Path("C:/Python311/python.exe"),
        Path("C:/Python312/python.exe"),
        Path("C:/Python310/python.exe"),
    ]
    
    for path in common_paths:
        if is_valid_python(str(path)):
            return str(path)
    
    # 4. Procura no PATH do sistema (filtrando WindowsApps)
    python_path = shutil.which("python")
    if python_path and is_valid_python(python_path):
        return python_path
    
    # Não encontrou nenhum Python válido
    return None


def cprint(msg, color="white"):
    colors = {"green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
              "blue": "\033[94m", "cyan": "\033[96m", "white": "\033[0m", "bold": "\033[1m"}
    try:
        print(f"{colors.get(color, '')}{msg}\033[0m", end="\n", flush=True)
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback se houver erro de encoding
        try:
            print(msg, end="\n", flush=True)
        except Exception:
            pass


def banner():
    try:
        cprint("╔═══════════════════════════════════════════════════╗", "cyan")
        cprint("║        📚 TRADUTOR UNIVERSAL DE PDF 📚            ║", "cyan")
        cprint("║     Tradução automática com IA • Ollama          ║", "cyan")
        cprint("╚═══════════════════════════════════════════════════╝", "cyan")
    except Exception:
        # Fallback sem caracteres especiais
        print("\n=== TRADUTOR UNIVERSAL DE PDF ===\n")
    print()
    cprint("⚠️  IMPORTANTE: Se alguma dependência falhar,", "yellow")
    cprint("   execute o 'instalador.bat' como ADMINISTRADOR", "yellow")
    print()


# =====================================================================
# CHECKS
# =====================================================================

def check_python() -> bool:
    cprint("[1/6] Verificando Python...", "blue")
    
    # Primeiro verifica o venv
    if os.path.exists(PYTHON_EXE) and is_valid_python(PYTHON_EXE):
        try:
            ver = subprocess.check_output([PYTHON_EXE, "--version"], text=True).strip()
            cprint(f"  ✅ {ver} (venv encontrado)", "green")
            return True
        except Exception:
            pass
    
    # Busca um Python válido no sistema
    valid_python = find_valid_python()
    if valid_python:
        try:
            ver = subprocess.check_output([valid_python, "--version"], text=True).strip()
            cprint(f"  ✅ {ver}", "green")
            cprint(f"     Local: {valid_python}", "green")
            return True
        except Exception:
            pass
    
    # Tenta o Python atual (sys.executable) como último recurso
    if is_valid_python(sys.executable):
        try:
            ver = subprocess.check_output([sys.executable, "--version"], text=True).strip()
            cprint(f"  ✅ {ver} (sistema)", "green")
            return True
        except Exception:
            pass
    
    cprint("  ❌ Python não encontrado ou inválido!", "red")
    cprint("\n  💡 SOLUÇÃO:", "yellow")
    cprint("     Execute o 'instalador.bat' como ADMINISTRADOR", "yellow")
    cprint("     Ele irá instalar o Python PORTÁVEL no projeto", "yellow")
    cprint("     (Após instalado, você pode copiar o projeto para qualquer PC!)", "yellow")
    return False


def check_venv() -> bool:
    cprint("[2/6] Verificando ambiente virtual...", "blue")
    if os.path.exists(PYTHON_EXE) and is_valid_python(PYTHON_EXE):
        cprint("  ✅ Venv existe", "green")
        return True
    
    cprint("  ⏳ Criando venv...", "yellow")
    
    # Encontra um Python válido para criar o venv
    valid_python = find_valid_python()
    if not valid_python:
        valid_python = sys.executable
        if not is_valid_python(valid_python):
            cprint("  ❌ Nenhum Python válido encontrado para criar o venv", "red")
            cprint("\n  💡 SOLUÇÃO:", "yellow")
            cprint("     Execute o 'instalador.bat' como ADMINISTRADOR", "yellow")
            return False
    
    try:
        subprocess.run([valid_python, "-m", "venv", str(VENV_DIR)], check=True)
        cprint("  ✅ Venv criado", "green")
        return True
    except subprocess.CalledProcessError:
        # Tenta com virtualenv
        cprint("  ⏳ Tentando com virtualenv...", "yellow")
        try:
            subprocess.run([valid_python, "-m", "pip", "install", "--quiet", "virtualenv"], check=True)
            subprocess.run([valid_python, "-m", "virtualenv", str(VENV_DIR)], check=True)
            cprint("  ✅ Venv criado com virtualenv", "green")
            return True
        except Exception as e:
            cprint(f"  ❌ Erro ao criar venv: {e}", "red")
            cprint("\n  💡 SOLUÇÃO:", "yellow")
            cprint("     Execute o 'instalador.bat' como ADMINISTRADOR", "yellow")
            cprint("     Ele irá configurar o ambiente corretamente", "yellow")
            return False


def check_packages() -> bool:
    cprint("[3/6] Verificando pacotes Python...", "blue")

    if DEPS_DONE_FILE.exists():
        cprint("  ✅ Pacotes já instalados (cache)", "green")
        return True

    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            subprocess.run(
                [PYTHON_EXE, "-c", f"import importlib; importlib.import_module('{pkg_import_name(pkg)}')"],
                capture_output=True, check=True
            )
        except subprocess.CalledProcessError:
            missing.append(pkg)

    if missing:
        cprint(f"  ⏳ Instalando: {', '.join(missing)}...", "yellow")
        try:
            subprocess.run(
                [PIP_EXE, "install", "--quiet"] + missing,
                check=True
            )
            cprint("  ✅ Pacotes instalados", "green")
        except Exception as e:
            cprint(f"  ❌ Erro: {e}", "red")
            cprint("\n  💡 SOLUÇÃO:", "yellow")
            cprint("     Execute o 'instalador.bat' como ADMINISTRADOR", "yellow")
            cprint("     Ele irá instalar todos os pacotes necessários", "yellow")
            return False
    else:
        cprint("  ✅ Todos os pacotes presentes", "green")

    # Mark as done
    DEPS_DONE_FILE.write_text("ok")
    return True


def pkg_import_name(pkg: str) -> str:
    mapping = {
        "PyMuPDF": "fitz",
        "Pillow": "PIL",
        "rapidocr-onnxruntime": "rapidocr_onnxruntime",
        "tqdm": "tqdm",
    }
    return mapping.get(pkg, pkg.lower().replace("-", "_"))


def check_ollama() -> bool:
    cprint("[4/6] Verificando Ollama...", "blue")
    # Check if ollama is installed
    ollama_path = shutil.which("ollama")
    if not ollama_path:
        # Check common Windows paths
        common_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
            Path("C:/Users") / os.environ.get("USERNAME", "") / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
        ]
        for p in common_paths:
            if p.exists():
                ollama_path = str(p)
                break

    if not ollama_path:
        cprint("  ❌ Ollama não encontrado!", "red")
        cprint("\n  💡 SOLUÇÕES:", "yellow")
        cprint("     1. Execute o 'instalador.bat' como ADMINISTRADOR", "yellow")
        cprint("        (Ele pode instalar o Ollama automaticamente)", "yellow")
        cprint("     2. Ou instale manualmente de: https://ollama.com/download", "yellow")
        cprint("\n  ⚠️  O sistema NÃO funcionará sem o Ollama (IA de tradução)", "red")
        return False

    cprint(f"  ✅ Ollama encontrado", "green")
    return True


def check_ollama_running() -> bool:
    cprint("[5/6] Verificando serviço Ollama...", "blue")
    try:
        r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        data = json.loads(r.read())
        cprint(f"  ✅ Ollama rodando ({len(data.get('models', []))} modelos)", "green")
        return True
    except Exception:
        cprint("  ⏳ Iniciando Ollama...", "yellow")
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            time.sleep(3)
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
            cprint("  ✅ Ollama iniciado", "green")
            return True
        except Exception as e:
            cprint(f"  ⚠️ Não conseguiu iniciar Ollama: {e}", "yellow")
            cprint("  💡 Inicie o Ollama manualmente", "yellow")
            return True  # Continue anyway


def check_model() -> bool:
    cprint(f"[6/6] Verificando modelo '{OLLAMA_MODEL}'...", "blue")
    try:
        r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        data = json.loads(r.read())
        names = [m["name"] for m in data.get("models", [])]
        if any(OLLAMA_MODEL.lower() in n.lower() for n in names):
            cprint(f"  ✅ Modelo '{OLLAMA_MODEL}' disponível", "green")
            return True
        cprint(f"  ⏳ Baixando modelo '{OLLAMA_MODEL}' (pode demorar)...", "yellow")
        subprocess.run(["ollama", "pull", OLLAMA_MODEL], check=True)
        cprint(f"  ✅ Modelo '{OLLAMA_MODEL}' instalado", "green")
        return True
    except Exception as e:
        cprint(f"  ⚠️ Modelo check: {e}", "yellow")
        return True  # Continue anyway


def create_dirs():
    """Create required directories."""
    for d in ["livros-para-traduzir", "traduzidos", "em-inges", "traduzindo"]:
        (BASE_DIR / d).mkdir(parents=True, exist_ok=True)


# =====================================================================
# LAUNCH
# =====================================================================

def launch_server():
    cprint("\n🚀 Iniciando servidor do dashboard...\n", "bold")

    # Kill old dashboard if port file exists
    if PORT_FILE.exists():
        try:
            old_port = int(PORT_FILE.read_text().strip())
            # Check if port is in use
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("localhost", old_port)) == 0:
                    cprint(f"  ⚠️ Porta {old_port} já em uso, buscando outra...", "yellow")
        except Exception:
            pass

    proc = subprocess.Popen(
        [PYTHON_EXE, SERVER_SCRIPT],
        cwd=str(ENGINE_DIR),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )

    # Wait for server to start and read port
    for _ in range(30):
        time.sleep(0.5)
        if PORT_FILE.exists():
            try:
                port = int(PORT_FILE.read_text().strip())
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(("localhost", port)) == 0:
                        cprint(f"  ✅ Dashboard rodando em http://localhost:{port}", "green")
                        cprint(f"\n  🌐 Abrindo navegador...", "cyan")
                        webbrowser.open(f"http://localhost:{port}")
                        return proc, port
            except Exception:
                pass

    cprint("  ⚠️ Servidor pode estar demorando para iniciar...", "yellow")
    return proc, None


# =====================================================================
# MAIN
# =====================================================================

def main():
    banner()

    if DEPS_DONE_FILE.exists():
        cprint("⚡ Dependências já verificadas. Iniciando rapidamente...\n", "green")
        create_dirs()
        proc, port = launch_server()
        if port:
            cprint(f"\n{'='*55}", "cyan")
            cprint(f"  ✅ Sistema pronto! Dashboard: http://localhost:{port}", "bold")
            cprint(f"  📚 Coloque PDFs na pasta 'livros-para-traduzir'", "cyan")
            cprint(f"  🎯 Clique 'Iniciar' no dashboard para traduzir", "cyan")
            cprint(f"  ⏹  Ctrl+C aqui para encerrar", "cyan")
            cprint(f"{'='*55}\n", "cyan")
        try:
            proc.wait()
        except KeyboardInterrupt:
            cprint("\n🛑 Encerrando...", "yellow")
            proc.terminate()
        return

    cprint("🔍 Verificando dependências...\n", "bold")

    steps = [
        check_python,
        check_venv,
        check_packages,
        check_ollama,
        check_ollama_running,
        check_model,
    ]

    for step in steps:
        if not step():
            cprint(f"\n❌ Falha na verificação. Corrija o problema e tente novamente.", "red")
            input("\nPressione Enter para sair...")
            return

    create_dirs()
    cprint("\n✅ Todas as dependências verificadas!\n", "green")

    proc, port = launch_server()
    if port:
        cprint(f"\n{'='*55}", "cyan")
        cprint(f"  ✅ Sistema pronto! Dashboard: http://localhost:{port}", "bold")
        cprint(f"  📚 Coloque PDFs na pasta 'livros-para-traduzir'", "cyan")
        cprint(f"  🎯 Clique 'Iniciar' no dashboard para traduzir", "cyan")
        cprint(f"  ⏹  Ctrl+C aqui para encerrar", "cyan")
        cprint(f"{'='*55}\n", "cyan")

    try:
        proc.wait()
    except KeyboardInterrupt:
        cprint("\n🛑 Encerrando...", "yellow")
        proc.terminate()


if __name__ == "__main__":
    main()
