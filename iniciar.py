#!/usr/bin/env python3
"""
Tradutor Universal de PDF - Launcher
Starts the dashboard server and can keep it running in the Windows tray.
"""

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

# =====================================================================
# PATHS / CONSTANTS
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
DEPS_DONE_FILE = ENGINE_DIR / ".deps_installed"

DASHBOARD_PORT = 8050
DASHBOARD_URL = f"http://localhost:{DASHBOARD_PORT}/"

INPUT_DIR = BASE_DIR / "livros-para-traduzir"
TRANSLATING_DIR = BASE_DIR / "traduzindo"
OUTPUT_DIR = BASE_DIR / "traduzidos"
PREVIOUS_LANG_DIR = BASE_DIR / "na-lingua-anterior"
LEGACY_PREVIOUS_LANG_DIR = BASE_DIR / "em-inges"

OLLAMA_MODEL = "TranslateGemma"

REQUIRED_PACKAGES = [
    "PyMuPDF",
    "Pillow",
    "rapidocr-onnxruntime",
    "tqdm",
    "pystray",
]

# Windows process creation flags
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000

# Enable ANSI on Windows terminals
os.system("")


def cprint(message: str, color: str = "white"):
    colors = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "white": "\033[0m",
        "bold": "\033[1m",
    }
    try:
        print(f"{colors.get(color, '')}{message}\033[0m", flush=True)
    except Exception:
        print(message, flush=True)


def show_message(title: str, message: str, is_error: bool = False):
    """Show a Windows popup (fallback to console)."""
    if os.name == "nt":
        flags = 0x10 if is_error else 0x40
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, flags)
            return
        except Exception:
            pass
    cprint(f"[{title}] {message}", "red" if is_error else "yellow")


def banner():
    cprint("=" * 60, "cyan")
    cprint("TRADUTOR UNIVERSAL DE PDF v1.8", "bold")
    cprint("Traducao automatica com IA local (Ollama)", "cyan")
    cprint("=" * 60, "cyan")


def pkg_import_name(pkg: str) -> str:
    mapping = {
        "PyMuPDF": "fitz",
        "Pillow": "PIL",
        "rapidocr-onnxruntime": "rapidocr_onnxruntime",
        "tqdm": "tqdm",
        "pystray": "pystray",
    }
    return mapping.get(pkg, pkg.lower().replace("-", "_"))


def is_valid_python(python_path: str) -> bool:
    try:
        if not python_path:
            return False
        if "WindowsApps" in python_path:
            return False
        if not os.path.exists(python_path):
            return False
        result = subprocess.run(
            [python_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def find_valid_python() -> str:
    # 1) Saved path from installer
    if PYTHON_CONFIG_FILE.exists():
        try:
            saved_python = PYTHON_CONFIG_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            saved_python = ""
        if is_valid_python(saved_python):
            return saved_python

    # 2) Portable Python inside project
    python_portable = PYTHON_PORTABLE_DIR / "python.exe"
    if is_valid_python(str(python_portable)):
        return str(python_portable)

    # 3) Common install locations
    common_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python313" / "python.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python311" / "python.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python310" / "python.exe",
        Path("C:/Python313/python.exe"),
        Path("C:/Python312/python.exe"),
        Path("C:/Python311/python.exe"),
        Path("C:/Python310/python.exe"),
    ]
    for path in common_paths:
        if is_valid_python(str(path)):
            return str(path)

    # 4) PATH
    python_path = shutil.which("python")
    if python_path and is_valid_python(python_path):
        return python_path

    return ""


def ensure_previous_lang_dir():
    PREVIOUS_LANG_DIR.mkdir(parents=True, exist_ok=True)
    if not LEGACY_PREVIOUS_LANG_DIR.exists() or not LEGACY_PREVIOUS_LANG_DIR.is_dir():
        return

    for item in LEGACY_PREVIOUS_LANG_DIR.iterdir():
        target = PREVIOUS_LANG_DIR / item.name
        if target.exists():
            continue
        try:
            shutil.move(str(item), str(target))
        except Exception:
            pass

    try:
        if not any(LEGACY_PREVIOUS_LANG_DIR.iterdir()):
            LEGACY_PREVIOUS_LANG_DIR.rmdir()
    except Exception:
        pass


def create_dirs():
    for d in [INPUT_DIR, TRANSLATING_DIR, OUTPUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    ensure_previous_lang_dir()


def dashboard_online() -> bool:
    try:
        req = urllib.request.Request(f"{DASHBOARD_URL}api/status", method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_dashboard(timeout_sec: int = 30) -> bool:
    start = time.time()
    while (time.time() - start) < timeout_sec:
        if dashboard_online():
            return True
        time.sleep(0.5)
    return False


def check_python() -> bool:
    cprint("[1/6] Verificando Python...", "blue")
    if is_valid_python(PYTHON_EXE):
        cprint("  OK Python da venv encontrado", "green")
        return True

    valid_python = find_valid_python()
    if valid_python:
        cprint(f"  OK Python detectado: {valid_python}", "green")
        return True

    cprint("  ERRO: Python nao encontrado.", "red")
    cprint("  Execute o instalador.bat como administrador.", "yellow")
    return False


def check_venv() -> bool:
    cprint("[2/6] Verificando ambiente virtual...", "blue")
    if is_valid_python(PYTHON_EXE):
        cprint("  OK Ambiente virtual pronto", "green")
        return True

    base_python = find_valid_python()
    if not base_python and is_valid_python(sys.executable):
        base_python = sys.executable
    if not base_python:
        cprint("  ERRO: nenhum Python valido para criar venv.", "red")
        return False

    try:
        subprocess.run([base_python, "-m", "venv", str(VENV_DIR)], check=True)
        cprint("  OK Ambiente virtual criado", "green")
        return True
    except Exception as exc:
        cprint(f"  ERRO ao criar venv: {exc}", "red")
        return False


def check_packages() -> bool:
    cprint("[3/6] Verificando pacotes Python...", "blue")
    if not is_valid_python(PYTHON_EXE):
        cprint("  ERRO: Python da venv indisponivel.", "red")
        return False

    missing = []
    for pkg in REQUIRED_PACKAGES:
        import_name = pkg_import_name(pkg)
        try:
            subprocess.run(
                [PYTHON_EXE, "-c", f"import importlib; importlib.import_module('{import_name}')"],
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            missing.append(pkg)

    # Cache is only valid when every package is importable.
    if DEPS_DONE_FILE.exists() and not missing:
        cprint("  OK Pacotes ja instalados (cache valido)", "green")
        return True

    if not missing:
        cprint("  OK Todos os pacotes presentes", "green")
        DEPS_DONE_FILE.write_text("ok", encoding="utf-8")
        return True

    cprint(f"  Instalando: {', '.join(missing)}", "yellow")
    try:
        subprocess.run([PIP_EXE, "install", "--quiet"] + missing, check=True)
        DEPS_DONE_FILE.write_text("ok", encoding="utf-8")
        cprint("  OK Pacotes instalados", "green")
        return True
    except Exception as exc:
        cprint(f"  ERRO ao instalar pacotes: {exc}", "red")
        return False


def check_ollama() -> bool:
    cprint("[4/6] Verificando Ollama...", "blue")
    ollama_path = shutil.which("ollama")
    if ollama_path:
        cprint("  OK Ollama encontrado", "green")
        return True

    common_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path("C:/Users") / os.environ.get("USERNAME", "") / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
    ]
    if any(p.exists() for p in common_paths):
        cprint("  OK Ollama encontrado", "green")
        return True

    cprint("  ERRO: Ollama nao encontrado.", "red")
    cprint("  Instale via https://ollama.com/download ou rode instalador.bat.", "yellow")
    return False


def check_ollama_running() -> bool:
    cprint("[5/6] Verificando servico Ollama...", "blue")
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5):
            cprint("  OK Ollama em execucao", "green")
            return True
    except Exception:
        pass

    cprint("  Iniciando ollama serve...", "yellow")
    try:
        creationflags = CREATE_NEW_PROCESS_GROUP
        if os.name == "nt":
            creationflags |= DETACHED_PROCESS | CREATE_NO_WINDOW
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags if os.name == "nt" else 0,
        )
        if wait_ollama(timeout_sec=10):
            cprint("  OK Ollama iniciado", "green")
            return True
        cprint("  AVISO: Ollama nao respondeu a tempo", "yellow")
        return True
    except Exception as exc:
        cprint(f"  AVISO: nao foi possivel iniciar Ollama automaticamente ({exc})", "yellow")
        return True


def wait_ollama(timeout_sec: int = 10) -> bool:
    start = time.time()
    while (time.time() - start) < timeout_sec:
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
                return True
        except Exception:
            time.sleep(0.5)
    return False


def check_model() -> bool:
    cprint(f"[6/6] Verificando modelo '{OLLAMA_MODEL}'...", "blue")
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
        names = [m.get("name", "") for m in data.get("models", [])]
        if any(OLLAMA_MODEL.lower() in n.lower() for n in names):
            cprint(f"  OK Modelo '{OLLAMA_MODEL}' disponivel", "green")
            return True
    except Exception as exc:
        cprint(f"  AVISO: nao foi possivel consultar modelos ({exc})", "yellow")
        return True

    cprint(f"  Baixando modelo '{OLLAMA_MODEL}' (pode demorar)...", "yellow")
    try:
        subprocess.run(["ollama", "pull", OLLAMA_MODEL], check=True)
        cprint("  OK Modelo instalado", "green")
        return True
    except Exception as exc:
        cprint(f"  AVISO: falha ao baixar modelo ({exc})", "yellow")
        return True


def launch_server(background: bool):
    """
    Returns: (process_or_none, status)
    status: started | already_running | failed
    """
    if dashboard_online():
        return None, "already_running"

    env = os.environ.copy()
    env["TUP_PORT"] = str(DASHBOARD_PORT)

    creationflags = 0
    if os.name == "nt":
        creationflags = CREATE_NEW_PROCESS_GROUP
        if background:
            creationflags |= DETACHED_PROCESS | CREATE_NO_WINDOW

    kwargs = {
        "cwd": str(ENGINE_DIR),
        "env": env,
        "creationflags": creationflags if os.name == "nt" else 0,
    }
    if background:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL

    try:
        proc = subprocess.Popen([PYTHON_EXE, SERVER_SCRIPT], **kwargs)
    except Exception:
        return None, "failed"

    if wait_dashboard(timeout_sec=30):
        return proc, "started"

    try:
        proc.terminate()
    except Exception:
        pass
    return None, "failed"


def open_dashboard():
    try:
        webbrowser.open(DASHBOARD_URL)
    except Exception:
        pass


def stop_pipeline_via_api():
    try:
        req = urllib.request.Request(
            f"{DASHBOARD_URL}api/stop",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        pass

    try:
        req = urllib.request.Request(
            f"{DASHBOARD_URL}api/stop-validator",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        pass


def stop_server(server_proc: subprocess.Popen | None):
    if server_proc is None:
        return
    if server_proc.poll() is not None:
        return

    stop_pipeline_via_api()
    try:
        server_proc.terminate()
        server_proc.wait(timeout=6)
    except Exception:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(server_proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        except Exception:
            pass


def open_folder(path: Path):
    if os.name == "nt":
        os.startfile(str(path))


def create_tray_image():
    from PIL import Image, ImageDraw

    size = 64
    image = Image.new("RGBA", (size, size), (35, 56, 84, 255))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((8, 8, 56, 56), radius=10, fill=(232, 245, 233, 255), outline=(27, 94, 32, 255), width=3)
    draw.rectangle((18, 16, 46, 52), fill=(255, 255, 255, 255), outline=(76, 175, 80, 255), width=2)
    draw.line((22, 22, 42, 22), fill=(66, 66, 66, 255), width=2)
    draw.line((22, 28, 42, 28), fill=(66, 66, 66, 255), width=2)
    draw.line((22, 34, 42, 34), fill=(66, 66, 66, 255), width=2)
    draw.ellipse((44, 40, 56, 52), fill=(33, 150, 243, 255))
    return image


def run_tray(server_proc: subprocess.Popen | None):
    try:
        import pystray
        from pystray import MenuItem as Item
    except Exception as exc:
        show_message("Erro", f"pystray indisponivel: {exc}", is_error=True)
        stop_server(server_proc)
        return

    icon = None

    def on_open_dashboard(icon_ref, item):
        del icon_ref, item
        open_dashboard()

    def on_open_input(icon_ref, item):
        del icon_ref, item
        open_folder(INPUT_DIR)

    def on_open_output(icon_ref, item):
        del icon_ref, item
        open_folder(OUTPUT_DIR)

    def on_stop_pipeline(icon_ref, item):
        del icon_ref, item
        stop_pipeline_via_api()
        try:
            icon.notify("Pipeline parada.", "Tradutor Universal de PDF")
        except Exception:
            pass

    def on_exit(icon_ref, item):
        del item
        icon_ref.stop()

    menu = pystray.Menu(
        Item("Abrir Dashboard", on_open_dashboard, default=True),
        Item("Abrir fila de traducao", on_open_input),
        Item("Abrir traduzidos", on_open_output),
        Item("Parar pipeline", on_stop_pipeline),
        Item("Sair", on_exit),
    )
    icon = pystray.Icon(
        "tradutor_universal_pdf",
        create_tray_image(),
        "Tradutor Universal de PDF v1.8",
        menu,
    )

    try:
        icon.run()
    finally:
        stop_server(server_proc)


def run_preflight(tray_mode: bool) -> bool:
    if not tray_mode:
        banner()
        cprint("Verificando dependencias...", "bold")

    steps = [
        check_python,
        check_venv,
        check_packages,
    ]

    # First run does complete checks.
    if not DEPS_DONE_FILE.exists():
        steps.extend([check_ollama, check_ollama_running, check_model])

    for step in steps:
        if not step():
            return False

    create_dirs()
    return True


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--tray", action="store_true", help="Run in system tray")
    args = parser.parse_args()

    if not run_preflight(args.tray):
        msg = "Falha na verificacao de dependencias. Rode instalador.bat como administrador."
        if args.tray:
            show_message("Tradutor Universal de PDF", msg, is_error=True)
        else:
            cprint(msg, "red")
        return 1

    server_proc, status = launch_server(background=args.tray)

    if status == "already_running":
        msg = f"O dashboard ja esta em execucao em {DASHBOARD_URL}"
        if not args.tray:
            cprint(msg, "yellow")
        open_dashboard()
        return 0

    if status == "failed":
        msg = f"Nao foi possivel iniciar o servidor em {DASHBOARD_URL}"
        if args.tray:
            show_message("Tradutor Universal de PDF", msg, is_error=True)
        else:
            cprint(msg, "red")
        return 1

    open_dashboard()

    if args.tray:
        run_tray(server_proc)
        return 0

    cprint(f"Sistema pronto em {DASHBOARD_URL}", "green")
    cprint("Pressione Ctrl+C para encerrar.", "cyan")
    try:
        if server_proc is not None:
            server_proc.wait()
    except KeyboardInterrupt:
        cprint("Encerrando...", "yellow")
        stop_server(server_proc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
