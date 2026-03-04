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
BASE_DIR = SCRIPT_DIR.parent  # testecode/
VENV_DIR = BASE_DIR / ".venv"
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

def cprint(msg, color="white"):
    colors = {"green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
              "blue": "\033[94m", "cyan": "\033[96m", "white": "\033[0m", "bold": "\033[1m"}
    print(f"{colors.get(color, '')}{msg}\033[0m")

def banner():
    cprint("╔═══════════════════════════════════════════════════╗", "cyan")
    cprint("║        📚 TRADUTOR UNIVERSAL DE PDF 📚            ║", "cyan")
    cprint("║     Tradução automática com IA • Ollama          ║", "cyan")
    cprint("╚═══════════════════════════════════════════════════╝", "cyan")
    print()


# =====================================================================
# CHECKS
# =====================================================================

def check_python() -> bool:
    cprint("[1/6] Verificando Python...", "blue")
    if os.path.exists(PYTHON_EXE):
        ver = subprocess.check_output([PYTHON_EXE, "--version"], text=True).strip()
        cprint(f"  ✅ {ver} (venv encontrado)", "green")
        return True
    # Check system python
    try:
        ver = subprocess.check_output([sys.executable, "--version"], text=True).strip()
        cprint(f"  ✅ {ver} (sistema)", "green")
        return True
    except Exception:
        cprint("  ❌ Python não encontrado!", "red")
        return False


def check_venv() -> bool:
    cprint("[2/6] Verificando ambiente virtual...", "blue")
    if os.path.exists(PYTHON_EXE):
        cprint("  ✅ Venv existe", "green")
        return True
    cprint("  ⏳ Criando venv...", "yellow")
    try:
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        cprint("  ✅ Venv criado", "green")
        return True
    except Exception as e:
        cprint(f"  ❌ Erro ao criar venv: {e}", "red")
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
        cprint("  ⏳ Instalando Ollama...", "yellow")
        try:
            # Download and install Ollama for Windows
            cprint("  📥 Baixando Ollama (pode demorar)...", "yellow")
            installer_url = "https://ollama.com/download/OllamaSetup.exe"
            installer_path = str(BASE_DIR / "OllamaSetup.exe")
            urllib.request.urlretrieve(installer_url, installer_path)
            cprint("  ⏳ Instalando (vai abrir o instalador)...", "yellow")
            subprocess.run([installer_path, "/VERYSILENT"], check=False)
            os.remove(installer_path)
            time.sleep(5)
        except Exception as e:
            cprint(f"  ❌ Erro ao instalar Ollama: {e}", "red")
            cprint("  💡 Instale manualmente: https://ollama.com/download", "yellow")
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
