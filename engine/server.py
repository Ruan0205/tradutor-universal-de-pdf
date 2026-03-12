#!/usr/bin/env python3
"""
Servidor Web + API do Tradutor Universal de PDF.
Gerencia o pipeline de tradução, validação, modelos Ollama, e serve o dashboard.
"""

import io
import json
import logging
import mimetypes
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from datetime import datetime, timedelta
from email.parser import BytesParser
from email.policy import default as EMAIL_POLICY
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse, unquote, quote

# =====================================================================
# PATHS
# =====================================================================

ENGINE_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = ENGINE_DIR.parent
BASE_DIR = PROJECT_DIR
STATIC_DIR = ENGINE_DIR / "static"

CONFIG_FILE = ENGINE_DIR / "config.json"
CONTROL_FILE = ENGINE_DIR / "pipeline_control.json"
STATE_FILE = ENGINE_DIR / "pipeline_state.json"
VALIDATION_LOG = BASE_DIR / "validation_report.log"
TRANSLATION_LOG = BASE_DIR / "translation.log"

INPUT_DIR = BASE_DIR / "livros-para-traduzir"
TRANSLATING_DIR = BASE_DIR / "traduzindo"
OUTPUT_DIR = BASE_DIR / "traduzidos"
PREVIOUS_LANG_DIR = BASE_DIR / "na-lingua-anterior"
LEGACY_PREVIOUS_LANG_DIR = BASE_DIR / "em-inges"
ENGLISH_DIR = PREVIOUS_LANG_DIR

PYTHON_EXE = str(PROJECT_DIR / ".venv" / "Scripts" / "python.exe")
PIPELINE_SCRIPT = str(ENGINE_DIR / "pipeline.py")
VALIDATOR_SCRIPT = str(ENGINE_DIR / "validator.py")

# =====================================================================
# LOGGING
# =====================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("server")

# =====================================================================
# PROCESS MANAGER
# =====================================================================

_pipeline_process: Optional[subprocess.Popen] = None
_validator_process: Optional[subprocess.Popen] = None
_lock = threading.Lock()


def _monitor_pipeline_process():
    """Monitor thread para detectar quando pipeline termina e resetar estado."""
    global _pipeline_process
    while True:
        time.sleep(2)
        with _lock:
            if _pipeline_process is not None and not is_process_alive(_pipeline_process):
                state = read_state()
                current_status = state.get("status", "idle")
                if current_status in ("running", "paused", "completed"):
                    log.info("Pipeline finalizado. Resetando estado para idle.")
                    write_state({"status": "idle"})
                _pipeline_process = None


_monitor_thread = threading.Thread(target=_monitor_pipeline_process, daemon=True)
_monitor_thread.start()


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


def load_config() -> dict:
    defaults = {
        "ollama_url": "http://localhost:11434",
        "model_name": "TranslateGemma",
        "base_dir": str(BASE_DIR),
        "validation_model": "TranslateGemma",
        "validation_pages": 10,
        "validation_method": "structural",
        "image_text_mode": "legacy",
        "compute_backend": "cpu",
        "image_ai_selectable_only": True,
        "image_inpaint_radius": 3,
        "font_pack_dir": "assets/fonts",
        "live_preview_enabled": True,
        "resource_profile": "auto_max",
        "source_lang": "English",
        "target_lang": "Portugu\u00eas Brasileiro",
        "sort_order": "smallest_first",
        "custom_order": [],
        "max_batch_chars": 2200,
        "ollama_timeout_sec": 300,
        "ollama_options": {
            "temperature": 0.4,
            "top_p": 0.9,
            "num_ctx": 8192,
        },
        "original_mappings": {},
        "validation_mode": "25%",
        "fidelity_threshold": 90,
        "retranslate_queue": [],
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            return {**defaults, **stored}
        except Exception:
            pass
    return defaults


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def write_control(ctrl: dict):
    with open(CONTROL_FILE, "w", encoding="utf-8") as f:
        json.dump(ctrl, f, indent=2)


def read_control() -> dict:
    if CONTROL_FILE.exists():
        try:
            with open(CONTROL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"command": "idle", "model": load_config().get("model_name", "TranslateGemma")}


def read_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"status": "idle"}


def write_state(state: dict):
    """Escreve estado da pipeline para arquivo."""
    state["last_update"] = datetime.now().isoformat()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.error("Erro ao escrever state: %s", e)


def is_process_alive(proc) -> bool:
    return proc is not None and proc.poll() is None


def start_pipeline(retranslate: str = None):
    global _pipeline_process
    with _lock:
        if is_process_alive(_pipeline_process):
            return {"ok": False, "error": "Pipeline já está rodando"}
        # Guard secundário: verificar se pipeline estado indica execução recente
        state = read_state()
        if state.get("status") in ("running", "paused"):
            last = state.get("last_update", "")
            if last:
                try:
                    dt = datetime.fromisoformat(last)
                    if (datetime.now() - dt).total_seconds() < 30:
                        return {"ok": False, "error": "Pipeline parece estar rodando (estado recente)"}
                except Exception:
                    pass
        cfg = load_config()
        write_control({"command": "run", "model": cfg["model_name"]})
        cmd = [PYTHON_EXE, PIPELINE_SCRIPT]
        if retranslate:
            cmd += ["--retranslate", retranslate]
        _pipeline_process = subprocess.Popen(
            cmd, cwd=str(ENGINE_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        log.info("Pipeline iniciado (PID=%d)", _pipeline_process.pid)
        return {"ok": True, "pid": _pipeline_process.pid}


def stop_pipeline():
    global _pipeline_process
    with _lock:
        write_control({"command": "stop", "model": load_config().get("model_name", "")})
        if is_process_alive(_pipeline_process):
            try:
                if os.name == "nt":
                    _pipeline_process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    _pipeline_process.terminate()
            except Exception:
                pass
            _pipeline_process = None
        return {"ok": True}


def pause_pipeline():
    ctrl = read_control()
    ctrl["command"] = "pause"
    write_control(ctrl)
    return {"ok": True}


def resume_pipeline():
    ctrl = read_control()
    ctrl["command"] = "run"
    write_control(ctrl)
    return {"ok": True}


def start_validator():
    global _validator_process
    with _lock:
        if is_process_alive(_validator_process):
            return {"ok": False, "error": "Validador já está rodando"}
        _validator_process = subprocess.Popen(
            [PYTHON_EXE, VALIDATOR_SCRIPT], cwd=str(ENGINE_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        log.info("Validador iniciado (PID=%d)", _validator_process.pid)
        return {"ok": True}


def stop_validator():
    global _validator_process
    with _lock:
        if is_process_alive(_validator_process):
            try:
                _validator_process.terminate()
            except Exception:
                pass
            _validator_process = None
        return {"ok": True}


def queue_retranslate(translated_name: str) -> dict:
    """Queue a book for retranslation as next in queue."""
    books = get_books_data()
    orig_name = books["mapping"].get(translated_name)
    if not orig_name:
        return {"ok": False, "error": "Original não encontrado no mapeamento"}

    orig_path = ENGLISH_DIR / orig_name
    if not orig_path.exists():
        return {"ok": False, "error": f"Arquivo original não encontrado: {orig_name}"}

    # Copy original back to input
    dest = INPUT_DIR / orig_name
    shutil.copy2(str(orig_path), str(dest))

    # Remove old translation from output
    trans_path = OUTPUT_DIR / translated_name
    if trans_path.exists():
        trans_path.unlink()
        log.info("Removida tradução anterior: %s", translated_name)

    # Add to retranslate queue in config
    cfg = load_config()
    rq = cfg.get("retranslate_queue", [])
    if orig_name not in rq:
        rq.append(orig_name)
    cfg["retranslate_queue"] = rq
    save_config(cfg)

    # If pipeline not running, start it
    if not is_process_alive(_pipeline_process):
        start_pipeline()
        start_validator()
        return {"ok": True, "message": f"'{orig_name}' adicionado como próximo na fila. Pipeline iniciado."}

    return {"ok": True, "message": f"'{orig_name}' adicionado como próximo na fila de tradução."}


# =====================================================================
# DATA GATHERING
# =====================================================================

def get_ollama_status() -> dict:
    cfg = load_config()
    url = cfg.get("ollama_url", "http://localhost:11434")
    try:
        r = urllib.request.urlopen(f"{url}/api/tags", timeout=5)
        data = json.loads(r.read())
        models = []
        for m in data.get("models", []):
            models.append({
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "modified_at": m.get("modified_at", ""),
            })
        return {"connected": True, "models": models, "url": url}
    except Exception as e:
        return {"connected": False, "models": [], "url": url, "error": str(e)}


def get_books_data() -> dict:
    """Collect all book data from directories and logs."""

    def list_pdfs(directory, sort_mode="name_asc"):
        if not directory.exists():
            return []
        items = []
        for f in directory.glob("*.pdf"):
            stat = f.stat()
            items.append({
                "name": f.name,
                "size_mb": round(stat.st_size / 1048576, 2),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "_mtime": stat.st_mtime,
            })
        if sort_mode == "mtime_desc":
            items.sort(key=lambda x: (x["_mtime"], x["name"].lower()), reverse=True)
        else:
            items.sort(key=lambda x: x["name"].lower())
        for item in items:
            item.pop("_mtime", None)
        return items

    # Parse translation log for mappings
    mapping = {}  # translated_name -> original_name
    timing = {}   # original_name -> {start, end, duration}
    if TRANSLATION_LOG.exists():
        try:
            text = TRANSLATION_LOG.read_text(encoding="utf-8", errors="replace")
            # Parse ALL log entries (not just last run) to preserve timing data
            current_orig = None
            current_start = None
            for line in text.split("\n"):
                m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Abrindo PDF: (.+)", line)
                if m:
                    current_start = m.group(1)
                    current_orig = m.group(2).strip()

                m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*PDF traduzido salvo: (.+)", line)
                if m and current_orig:
                    end_time = m.group(1)
                    if current_start:
                        try:
                            t0 = datetime.strptime(current_start, "%Y-%m-%d %H:%M:%S")
                            t1 = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                            timing[current_orig] = {
                                "start": current_start,
                                "end": end_time,
                                "duration_sec": (t1 - t0).total_seconds(),
                            }
                        except Exception:
                            pass

                m = re.search(r"->\s+Traduzido:\s+(.+\.pdf)", line)
                if m and current_orig:
                    mapping[m.group(1).strip()] = current_orig
        except Exception:
            pass

    # Parse validation log
    validations = {}
    if VALIDATION_LOG.exists():
        try:
            val_text = VALIDATION_LOG.read_text(encoding="utf-8", errors="replace")
            blocks = val_text.split("=" * 60)
            for block in blocks:
                val_m = re.search(r"VALIDATING: (.+)", block)
                res_m = re.search(r"RESULT: (PASS|FAIL) \(rate=(\d+)%\)", block)
                if val_m and res_m:
                    validations[val_m.group(1).strip()] = {
                        "result": res_m.group(1),
                        "rate": int(res_m.group(2)),
                    }
        except Exception:
            pass

    # Merge manual original mappings from config
    cfg = load_config()
    manual_mappings = cfg.get("original_mappings", {})
    for trans_name, orig_name in manual_mappings.items():
        mapping[trans_name] = orig_name

    # Build combined book list
    translated = []
    for f in list_pdfs(OUTPUT_DIR, sort_mode="mtime_desc"):
        orig_name = mapping.get(f["name"], "")
        val = validations.get(f["name"], None)
        t = timing.get(orig_name, {})
        translated.append({
            **f,
            "original_name": orig_name,
            "validation": val,
            "timing": t,
        })

    return {
        "input": list_pdfs(INPUT_DIR),
        "translating": list_pdfs(TRANSLATING_DIR),
        "translated": translated,
        "originals": list_pdfs(ENGLISH_DIR),
        "counts": {
            "input": len(list_pdfs(INPUT_DIR)),
            "translating": len(list_pdfs(TRANSLATING_DIR)),
            "translated": len(list_pdfs(OUTPUT_DIR)),
            "originals": len(list_pdfs(ENGLISH_DIR)),
        },
        "mapping": mapping,
        "validations": validations,
    }


def get_in_progress_preview_info(state: dict) -> dict:
    preview_name = (state or {}).get("preview_pdf")
    if preview_name:
        try:
            target = (TRANSLATING_DIR / preview_name).resolve()
            if str(target).startswith(str(TRANSLATING_DIR.resolve())) and target.exists():
                return {
                    "available": True,
                    "filename": target.name,
                    "url": f"/pdf/in-progress/{quote(target.name)}",
                }
        except Exception:
            pass

    # Fallback: latest partial translated file in translating dir.
    try:
        candidates = sorted(
            TRANSLATING_DIR.glob("*_PT.pdf"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            latest = candidates[0]
            return {
                "available": True,
                "filename": latest.name,
                "url": f"/pdf/in-progress/{quote(latest.name)}",
            }
    except Exception:
        pass

    return {"available": False, "filename": "", "url": ""}


def get_full_status() -> dict:
    """Combine all status into one payload for the dashboard."""
    state = read_state()
    ctrl = read_control()
    cfg = load_config()
    books = get_books_data()
    ollama = get_ollama_status()
    preview = get_in_progress_preview_info(state)

    # Determine effective status
    pipeline_alive = is_process_alive(_pipeline_process)
    validator_alive = is_process_alive(_validator_process)

    effective_status = state.get("status", "idle")
    # Se pipeline não está rodando e estava "completed", reset para idle
    if not pipeline_alive and effective_status == "completed":
        effective_status = "idle"
        write_state({"status": "idle"})
    elif not pipeline_alive and effective_status in ("running", "paused"):
        effective_status = "idle"
        write_state({"status": "idle"})
    if ctrl.get("command") == "pause" and pipeline_alive:
        effective_status = "paused"

    # Calculate ETA
    eta_str = None
    completed = books["counts"]["translated"]
    total = completed + books["counts"]["input"] + books["counts"]["translating"]

    total_time = sum(
        b.get("timing", {}).get("duration_sec", 0) for b in books["translated"]
    )
    total_size = sum(b["size_mb"] for b in books["translated"] if b.get("timing", {}).get("duration_sec"))

    if total_size > 0 and total_time > 0:
        sec_per_mb = total_time / total_size
        remaining_size = sum(b["size_mb"] for b in books["input"])
        # Add current book remaining
        cur = state.get("current_book")
        if cur and cur.get("start_time"):
            try:
                started = datetime.fromisoformat(cur["start_time"])
                elapsed = (datetime.now() - started).total_seconds()
                est_total = cur.get("size_mb", 1) * sec_per_mb
                remaining_size += max(0, (est_total - elapsed)) / sec_per_mb if sec_per_mb > 0 else 0
            except Exception:
                pass
        eta_seconds = remaining_size * sec_per_mb
        eta_str = _fmt_duration(eta_seconds)
        finish_time = (datetime.now() + timedelta(seconds=eta_seconds)).strftime("%d/%m %H:%M")
    else:
        sec_per_mb = None
        eta_str = None
        finish_time = None
        # Estimar a partir do progresso de páginas do livro atual
        cur = state.get("current_book")
        cur_page = state.get("current_page", 0)
        total_pages = state.get("total_pages", 0)
        if cur and cur.get("start_time") and cur_page > 0 and total_pages > 0:
            try:
                started = datetime.fromisoformat(cur["start_time"])
                elapsed = (datetime.now() - started).total_seconds()
                sec_per_page = elapsed / cur_page
                remaining_pages = total_pages - cur_page
                remaining_cur = remaining_pages * sec_per_page
                # Estimar sec_per_mb a partir do livro atual
                cur_size = cur.get("size_mb", 1)
                if cur_size > 0 and total_pages > 0:
                    pages_per_mb = total_pages / cur_size
                    sec_per_mb = sec_per_page * pages_per_mb
                # Tempo restante dos livros na fila
                remaining_queue = sum(b["size_mb"] for b in books["input"]) * sec_per_mb if sec_per_mb else 0
                total_remaining = remaining_cur + remaining_queue
                eta_str = _fmt_duration(total_remaining)
                finish_time = (datetime.now() + timedelta(seconds=total_remaining)).strftime("%d/%m %H:%M")
            except Exception:
                pass
        if eta_str is None:
            eta_str = "Calculando..."
            finish_time = "--"

    # Current book elapsed
    cur_elapsed = None
    cur = state.get("current_book")
    if cur and cur.get("start_time"):
        try:
            started = datetime.fromisoformat(cur["start_time"])
            cur_elapsed = (datetime.now() - started).total_seconds()
        except Exception:
            pass

    # Tempo total gasto: livros completos + livro atual em progresso
    total_elapsed = total_time + (cur_elapsed or 0)

    # Tempo desde o início da pipeline
    pipeline_elapsed = None
    pipeline_start = state.get("pipeline_start")
    if pipeline_start and effective_status in ("running", "paused"):
        try:
            pipeline_elapsed = (datetime.now() - datetime.fromisoformat(pipeline_start)).total_seconds()
        except Exception:
            pass

    return {
        "status": effective_status,
        "pipeline_alive": pipeline_alive,
        "validator_alive": validator_alive,
        "state": state,
        "control": ctrl,
        "config": cfg,
        "books": books,
        "preview": preview,
        "ollama": ollama,
        "stats": {
            "completed": completed,
            "total": total,
            "total_time_sec": total_time,
            "total_elapsed_sec": total_elapsed,
            "pipeline_elapsed_sec": pipeline_elapsed,
            "sec_per_mb": round(sec_per_mb, 1) if sec_per_mb else None,
            "eta_str": eta_str,
            "finish_time": finish_time,
            "current_elapsed_sec": cur_elapsed,
        },
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }


def _fmt_duration(seconds):
    if seconds is None:
        return "--"
    seconds = max(0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s"


def parse_multipart_form_data(content_type: str, body: bytes) -> list[dict]:
    """Parse multipart/form-data without depending on the removed cgi module."""
    raw_message = (
        f"Content-Type: {content_type}\r\n"
        "MIME-Version: 1.0\r\n\r\n"
    ).encode("utf-8") + body
    message = BytesParser(policy=EMAIL_POLICY).parsebytes(raw_message)
    if not message.is_multipart():
        raise ValueError("Expected multipart/form-data body")

    parts = []
    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() != "form-data":
            continue
        parts.append({
            "name": part.get_param("name", header="content-disposition"),
            "filename": part.get_filename(),
            "content": part.get_payload(decode=True) or b"",
        })
    return parts


def revalidate_book(translated_name: str) -> dict:
    """Trigger revalidation of a single book."""
    cfg = load_config()
    books = get_books_data()
    orig_name = books["mapping"].get(translated_name)
    if not orig_name:
        return {"ok": False, "error": "Original n\u00e3o encontrado no mapeamento"}

    orig_path = ENGLISH_DIR / orig_name
    trans_path = OUTPUT_DIR / translated_name
    if not orig_path.exists() or not trans_path.exists():
        return {"ok": False, "error": "Arquivos PDF n\u00e3o encontrados"}

    # Import and run validation
    sys.path.insert(0, str(ENGINE_DIR))
    from validator import validate_book

    val_mode = cfg.get("validation_mode", "25%")
    val_method = cfg.get("validation_method", "structural")
    fidelity = cfg.get("fidelity_threshold", 90)
    result = validate_book(str(orig_path), str(trans_path),
                           mode=val_mode, method=val_method,
                           fidelity_threshold=fidelity)

    # Log to validation report
    with open(VALIDATION_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"VALIDATING: {translated_name}\n")
        f.write(f"ORIGINAL: {orig_name}\n")
        f.write(f"METHOD: {val_method} | MODE: {val_mode} | THRESHOLD: {fidelity}%\n")
        rate = result.get("pass_rate", 0)
        status = "PASS" if result.get("overall_pass") else "FAIL"
        f.write(f"RESULT: {status} (rate={rate:.0%})\n")
        f.write(f"VALIDATED: {translated_name}\n")

    return {"ok": True, "result": result}


# =====================================================================
# HTTP SERVER
# =====================================================================

class DashboardHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # API routes
        if path == "/api/status":
            return self._json(get_full_status())
        if path == "/api/ollama":
            return self._json(get_ollama_status())
        if path == "/api/books":
            return self._json(get_books_data())
        if path == "/api/config":
            return self._json(load_config())

        # Serve PDF files
        if path.startswith("/pdf/translated/"):
            fname = unquote(path[len("/pdf/translated/"):])
            target = (OUTPUT_DIR / fname).resolve()
            if not str(target).startswith(str(OUTPUT_DIR.resolve())):
                return self._error(403, "Forbidden")
            return self._serve_pdf(target)
        if path.startswith("/pdf/original/"):
            fname = unquote(path[len("/pdf/original/"):])
            target = (ENGLISH_DIR / fname).resolve()
            if not str(target).startswith(str(ENGLISH_DIR.resolve())):
                return self._error(403, "Forbidden")
            return self._serve_pdf(target)
        if path == "/pdf/in-progress":
            preview = get_in_progress_preview_info(read_state())
            if not preview.get("available"):
                return self._error(404, "No in-progress PDF")
            target = (TRANSLATING_DIR / preview.get("filename", "")).resolve()
            if not str(target).startswith(str(TRANSLATING_DIR.resolve())):
                return self._error(403, "Forbidden")
            return self._serve_pdf(target)
        if path.startswith("/pdf/in-progress/"):
            fname = unquote(path[len("/pdf/in-progress/"):])
            target = (TRANSLATING_DIR / fname).resolve()
            if not str(target).startswith(str(TRANSLATING_DIR.resolve())):
                return self._error(403, "Forbidden")
            return self._serve_pdf(target)

        # Serve static files
        if path == "/" or path == "/index.html":
            return self._serve_file(STATIC_DIR / "index.html", "text/html")

        # Any other static file
        static_path = STATIC_DIR / path.lstrip("/")
        if static_path.exists() and static_path.is_file():
            mime = mimetypes.guess_type(str(static_path))[0] or "application/octet-stream"
            return self._serve_file(static_path, mime)

        self._error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/upload-pdfs":
            return self._handle_upload_pdfs()

        body = self._read_body()

        if path == "/api/start":
            retranslate = body.get("retranslate") if body else None
            result = start_pipeline(retranslate=retranslate)
            # Also start validator
            start_validator()
            return self._json(result)

        if path == "/api/stop":
            r1 = stop_pipeline()
            return self._json(r1)

        if path == "/api/pause":
            return self._json(pause_pipeline())

        if path == "/api/resume":
            return self._json(resume_pipeline())

        if path == "/api/model":
            if not body or "model" not in body:
                return self._error(400, "Missing 'model'")
            cfg = load_config()
            cfg["model_name"] = body["model"]
            save_config(cfg)
            # Update control file too
            ctrl = read_control()
            ctrl["model"] = body["model"]
            write_control(ctrl)
            return self._json({"ok": True, "model": body["model"]})

        if path == "/api/retranslate":
            if not body or "filename" not in body:
                return self._error(400, "Missing 'filename'")
            result = queue_retranslate(body["filename"])
            return self._json(result)

        if path == "/api/revalidate":
            if not body or "filename" not in body:
                return self._error(400, "Missing 'filename'")
            result = revalidate_book(body["filename"])
            return self._json(result)

        if path == "/api/add-pdfs":
            if not body or "files" not in body:
                return self._error(400, "Missing 'files'")
            added = []
            for fpath in body["files"]:
                src = Path(fpath)
                if src.exists() and src.suffix.lower() == ".pdf":
                    dest = INPUT_DIR / src.name
                    shutil.copy2(str(src), str(dest))
                    added.append(src.name)
            return self._json({"ok": True, "added": added})

        if path == "/api/open-directory":
            target = body.get("directory", "translated") if body else "translated"
            dirs = {
                "translated": OUTPUT_DIR,
                "input": INPUT_DIR,
                "originals": ENGLISH_DIR,
            }
            d = dirs.get(target, OUTPUT_DIR)
            if os.name == "nt":
                os.startfile(str(d))
            return self._json({"ok": True})

        if path == "/api/config":
            if body:
                cfg = load_config()
                cfg.update(body)
                save_config(cfg)
                return self._json({"ok": True})
            return self._error(400, "No data")

        if path == "/api/start-validator":
            return self._json(start_validator())

        if path == "/api/stop-validator":
            return self._json(stop_validator())

        if path == "/api/set-original":
            if not body or "translated" not in body or "original" not in body:
                return self._error(400, "Missing 'translated' or 'original'")
            cfg = load_config()
            mappings = cfg.get("original_mappings", {})
            if body["original"]:
                mappings[body["translated"]] = body["original"]
            elif body["translated"] in mappings:
                del mappings[body["translated"]]
            cfg["original_mappings"] = mappings
            save_config(cfg)
            return self._json({"ok": True})

        if path == "/api/order":
            if not body:
                return self._error(400, "No data")
            cfg = load_config()
            if "sort_order" in body:
                cfg["sort_order"] = body["sort_order"]
            if "custom_order" in body:
                cfg["custom_order"] = body["custom_order"]
            save_config(cfg)
            return self._json({"ok": True})

        self._error(404, "Not found")

    # -- Helpers --

    @staticmethod
    def _is_client_disconnect(exc: BaseException) -> bool:
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return True
        return isinstance(exc, OSError) and getattr(exc, "winerror", None) in {10053, 10054}

    def _send_bytes(self, code: int, body: bytes, content_type: str, extra_headers: Optional[dict] = None):
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(body))
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if body:
                self.wfile.write(body)
            return True
        except OSError as exc:
            if self._is_client_disconnect(exc):
                return False
            raise

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        return self._send_bytes(
            200,
            body,
            "application/json; charset=utf-8",
            {"Access-Control-Allow-Origin": "*"},
        )

    def _error(self, code, msg):
        body = json.dumps({"error": msg}).encode("utf-8")
        return self._send_bytes(code, body, "application/json")

    def _serve_file(self, path: Path, mime: str):
        if not path.exists():
            return self._error(404, "File not found")
        data = path.read_bytes()
        return self._send_bytes(200, data, f"{mime}; charset=utf-8")

    def _serve_pdf(self, path: Path):
        if not path.exists():
            return self._error(404, "PDF not found")
        data = path.read_bytes()
        return self._send_bytes(
            200,
            data,
            "application/pdf",
            {"Content-Disposition": f'inline; filename="{path.name}"'},
        )

    def _handle_upload_pdfs(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type.lower():
            return self._error(400, "Expected multipart/form-data")

        file_fields = []
        try:
            import cgi  # type: ignore
        except ModuleNotFoundError:
            cgi = None

        if cgi is not None:
            try:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        "REQUEST_METHOD": "POST",
                        "CONTENT_TYPE": content_type,
                    },
                    keep_blank_values=True,
                )
            except Exception as e:
                return self._error(400, f"Invalid multipart data: {e}")

            if "files" not in form:
                return self._error(400, "Missing 'files'")

            raw_file_fields = form["files"]
            if not isinstance(raw_file_fields, list):
                raw_file_fields = [raw_file_fields]

            file_fields = [
                {
                    "filename": getattr(item, "filename", None),
                    "file": getattr(item, "file", None),
                    "content": None,
                }
                for item in raw_file_fields
            ]
        else:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return self._error(400, "Empty multipart body")
            try:
                parsed_fields = parse_multipart_form_data(content_type, self.rfile.read(length))
            except Exception as e:
                return self._error(400, f"Invalid multipart data: {e}")
            file_fields = [field for field in parsed_fields if field.get("name") == "files"]
            if not file_fields:
                return self._error(400, "Missing 'files'")

        added = []
        overwritten = []
        skipped = []
        errors = []

        for item in file_fields:
            if not item.get("filename"):
                skipped.append("<sem-nome>")
                errors.append("Arquivo sem nome foi ignorado.")
                continue

            safe_name = Path(item["filename"]).name.strip()
            if not safe_name:
                skipped.append("<sem-nome>")
                errors.append("Arquivo sem nome foi ignorado.")
                continue

            if Path(safe_name).suffix.lower() != ".pdf":
                skipped.append(safe_name)
                errors.append(f"Arquivo ignorado (não é PDF): {safe_name}")
                continue

            file_obj = item.get("file")
            file_bytes = item.get("content")
            if file_obj is None and file_bytes is None:
                skipped.append(safe_name)
                errors.append(f"Arquivo inválido: {safe_name}")
                continue

            dest = INPUT_DIR / safe_name
            already_exists = dest.exists()

            try:
                with open(dest, "wb") as out:
                    if file_obj is not None:
                        shutil.copyfileobj(file_obj, out)
                    else:
                        out.write(file_bytes or b"")
                if already_exists:
                    overwritten.append(safe_name)
                else:
                    added.append(safe_name)
            except Exception as e:
                errors.append(f"Erro ao salvar '{safe_name}': {e}")

        return self._json({
            "ok": True,
            "added": added,
            "overwritten": overwritten,
            "skipped": skipped,
            "errors": errors,
        })

    def _read_body(self) -> Optional[dict]:
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            try:
                return json.loads(self.rfile.read(length))
            except Exception:
                pass
        return None

    def do_OPTIONS(self):
        self._send_bytes(
            200,
            b"",
            "text/plain; charset=utf-8",
            {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )

    def log_message(self, format, *args):
        pass  # Suppress request logs


def get_server_port() -> int:
    raw = os.environ.get("TUP_PORT", "8050").strip()
    try:
        port = int(raw)
    except ValueError:
        port = 8050
    if port < 1 or port > 65535:
        port = 8050
    return port


def main():
    ensure_previous_lang_dir()
    port = get_server_port()
    print(f"\n{'='*60}")
    print(f"  TRADUTOR UNIVERSAL DE PDF - Dashboard")
    print(f"  http://localhost:{port}")
    print(f"{'='*60}\n")
    # Criar pastas necessárias
    for d in [INPUT_DIR, TRANSLATING_DIR, OUTPUT_DIR, ENGLISH_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Inicializar arquivo de estado
    write_state({"status": "idle"})

    try:
        server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    except OSError as e:
        log.error("Nao foi possivel iniciar o servidor na porta %d: %s", port, e)
        return
    # Write port to file for the launcher to read
    (ENGINE_DIR / "server_port.txt").write_text(str(port))

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
        stop_pipeline()
        stop_validator()
        server.server_close()


if __name__ == "__main__":
    main()
