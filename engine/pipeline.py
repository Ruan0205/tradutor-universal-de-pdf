#!/usr/bin/env python3
"""
Pipeline de Tradução de PDFs - Inglês -> Português Brasileiro
Usa Ollama para tradução de alta qualidade.
Suporta controle externo (pause/stop/resume) via arquivo de controle.
Escreve estado em tempo real para o dashboard.
"""

import io
import json
import logging
import os
import re
import shutil
import sys
import time
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # pymupdf
import numpy as np
from PIL import Image, ImageDraw, ImageFont
try:
    import cv2
except Exception:
    cv2 = None

# =====================================================================
# CONFIGURAÇÃO - lida do config.json
# =====================================================================

ENGINE_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = ENGINE_DIR.parent
BASE_DIR = PROJECT_DIR

CONFIG_FILE = ENGINE_DIR / "config.json"
CONTROL_FILE = ENGINE_DIR / "pipeline_control.json"
STATE_FILE = ENGINE_DIR / "pipeline_state.json"

DEFAULT_CONFIG = {
    "ollama_url": "http://localhost:11434",
    "model_name": "TranslateGemma",
    "base_dir": str(BASE_DIR),
    "scanned_page_char_threshold": 30,
    "render_dpi": 300,
    "min_font_size": 5.0,
    "min_font_ratio": 0.65,
    "min_translatable_chars": 3,
    "max_batch_size": 10,
    "ollama_timeout_sec": 300,
    "source_lang": "English",
    "target_lang": "Português Brasileiro",
    "sort_order": "smallest_first",
    "custom_order": [],
    "validation_method": "structural",
    "image_text_mode": "legacy",
    "compute_backend": "cpu",
    "image_ai_selectable_only": True,
    "image_inpaint_radius": 3,
    "font_pack_dir": "assets/fonts",
    "ollama_options": {
        "temperature": 0.4,
        "top_p": 0.9,
        "num_ctx": 8192,
    },
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            stored = json.load(f)
        cfg = {**DEFAULT_CONFIG, **stored}
    else:
        cfg = dict(DEFAULT_CONFIG)
        save_config(cfg)
    return cfg


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


CFG = load_config()

# SEMPRE usar diretório real calculado dinamicamente, nunca confiar no config
# (o config pode ter path de outra máquina/disco)
CFG["base_dir"] = str(BASE_DIR)

INPUT_DIR = BASE_DIR / "livros-para-traduzir"
TRANSLATING_DIR = BASE_DIR / "traduzindo"
OUTPUT_DIR = BASE_DIR / "traduzidos"
PREVIOUS_LANG_DIR = BASE_DIR / "na-lingua-anterior"
LEGACY_PREVIOUS_LANG_DIR = BASE_DIR / "em-inges"
ENGLISH_DIR = PREVIOUS_LANG_DIR  # Compatibilidade interna com código existente
LOG_FILE = BASE_DIR / "translation.log"


def ensure_previous_lang_dir():
    """Garante a pasta atual e migra conteúdo legado de em-inges/ quando existir."""
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

# =====================================================================
# LOGGING
# =====================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("pipeline")

# =====================================================================
# CONTROLE EXTERNO (pause/stop/resume/model switch)
# =====================================================================


def read_control() -> dict:
    """Lê arquivo de controle. Retorna dict com command e model."""
    default = {"command": "run", "model": CFG["model_name"]}
    if not CONTROL_FILE.exists():
        write_control(default)
        return default
    try:
        with open(CONTROL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_control(ctrl: dict):
    with open(CONTROL_FILE, "w", encoding="utf-8") as f:
        json.dump(ctrl, f, indent=2)


def write_state(state: dict):
    """Escreve estado atual do pipeline para o dashboard ler."""
    state["last_update"] = datetime.now().isoformat()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def check_control(translator_engine=None) -> str:
    """Verifica controle. Pausa se necessário. Retorna 'run' ou 'stop'."""
    while True:
        ctrl = read_control()
        cmd = ctrl.get("command", "run")

        # Troca de modelo em tempo real
        new_model = ctrl.get("model", CFG["model_name"])
        if translator_engine and new_model != translator_engine.model:
            log.info("Trocando modelo de %s para %s", translator_engine.model, new_model)
            translator_engine.model = new_model
            translator_engine.cache.clear()

        if cmd == "stop":
            return "stop"
        if cmd == "pause":
            write_state({"status": "paused", **_get_base_state()})
            time.sleep(2)
            continue
        return "run"


_pipeline_state = {
    "status": "idle",
    "current_book": None,
    "current_page": 0,
    "total_pages": 0,
    "book_index": 0,
    "total_books": 0,
    "pipeline_start": None,
    "model": CFG["model_name"],
    "completed_books": [],
}


def _get_base_state() -> dict:
    return dict(_pipeline_state)


def update_state(**kwargs):
    _pipeline_state.update(kwargs)
    write_state(_pipeline_state)


# =====================================================================
# PROMPTS DE TRADUÇÃO (dinâmicos por idioma)
# =====================================================================

def make_system_prompt():
    src = CFG.get("source_lang", "English")
    tgt = CFG.get("target_lang", "Português Brasileiro")
    return (
        f"You are a professional {src}-to-{tgt} translator "
        "specializing in tabletop RPG books (D&D 3.5 / d20 System). "
        "Rules you MUST follow:\n"
        "1. Return ONLY the translated text. No explanations, alternatives, "
        "notes, markdown formatting or extra commentary.\n"
        f"2. Keep the following terms in {src}: proper nouns, game-mechanic "
        "terms (feat names, spell names, class names, prestige class names, "
        "ability score names like Strength/Dexterity/Constitution/Intelligence/"
        "Wisdom/Charisma, skill names, item names), abbreviations and acronyms "
        "(HP, AC, DC, CR, XP, HD, BAB, DM, NPC, PC, etc.).\n"
        f"3. Translate all descriptive, explanatory and flavor text into fluent, "
        f"natural {tgt}.\n"
        "4. Preserve any numbering, bullet points, or structural formatting "
        "present in the source text.\n"
        "5. If the source text is a single word or very short label that is a "
        "game term, return it unchanged.\n"
        "6. Never add quotation marks, asterisks, or any wrapper around the "
        "translation that was not in the original."
    )


def make_batch_prompt():
    src = CFG.get("source_lang", "English")
    tgt = CFG.get("target_lang", "Português Brasileiro")
    return (
        f"You are a professional {src}-to-{tgt} translator "
        "specializing in tabletop RPG books (D&D 3.5 / d20 System).\n"
        "Rules:\n"
        "1. Translate each numbered segment [1], [2], etc. separately.\n"
        "2. Return the translations with the EXACT same [N] labels.\n"
        f"3. Keep game terms in {src}: feat/spell/class/skill/item names, "
        "ability scores, abbreviations (HP, AC, DC, CR, XP, HD, BAB, etc.).\n"
        f"4. Translate descriptive text to fluent {tgt}.\n"
        "5. Do NOT add explanations, alternatives, or markdown.\n"
        "6. If a segment is a game term or very short label, return it unchanged.\n"
        "7. Preserve the exact count of segments: same number in, same number out."
    )


# =====================================================================
# MOTOR DE TRADUÇÃO
# =====================================================================

class TranslationEngine:
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = (base_url or CFG["ollama_url"]).rstrip("/")
        self.model = model or CFG["model_name"]
        self.cache: Dict[str, str] = {}
        self._verify_connection()

    def _verify_connection(self):
        try:
            r = urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=10)
            data = json.loads(r.read())
            names = [m["name"] for m in data.get("models", [])]
            if not any(self.model.lower() in n.lower() for n in names):
                log.warning("Modelo '%s' não encontrado. Disponíveis: %s", self.model, names)
            else:
                log.info("Ollama conectado. Modelo '%s' disponível.", self.model)
        except Exception as e:
            log.error("Falha ao conectar ao Ollama em %s: %s", self.base_url, e)
            raise

    def translate(self, text: str) -> str:
        text = text.strip()
        if not text:
            return text
        if text in self.cache:
            return self.cache[text]
        if not self._should_translate(text):
            self.cache[text] = text
            return text
        translated = self._call_ollama(text)
        self.cache[text] = translated
        return translated

    def translate_batch(self, texts: List[str]) -> List[str]:
        if not texts:
            return []
        indices_to_translate = []
        results = list(texts)
        for i, t in enumerate(texts):
            stripped = t.strip()
            if stripped in self.cache:
                results[i] = self.cache[stripped]
            elif not self._should_translate(stripped):
                self.cache[stripped] = stripped
            else:
                indices_to_translate.append(i)
        if not indices_to_translate:
            return results
        max_batch = max(1, int(CFG.get("max_batch_size", 10)))
        max_batch_chars = max(400, int(CFG.get("max_batch_chars", 2200)))
        for batch_indices in self._chunk_indices_by_chars(indices_to_translate, texts, max_batch, max_batch_chars):
            batch_texts = [texts[i].strip() for i in batch_indices]
            translated_batch = self._translate_batch_call(batch_texts)
            for j, idx in enumerate(batch_indices):
                if j < len(translated_batch):
                    results[idx] = translated_batch[j]
                    self.cache[texts[idx].strip()] = translated_batch[j]
                else:
                    results[idx] = self.translate(texts[idx])
        return results

    @staticmethod
    def _chunk_indices_by_chars(indices: List[int], texts: List[str], max_items: int, max_chars: int) -> List[List[int]]:
        chunks: List[List[int]] = []
        current: List[int] = []
        cur_chars = 0
        for idx in indices:
            t = (texts[idx] or "").strip()
            t_chars = max(1, len(t))
            hit_item_limit = len(current) >= max_items
            hit_char_limit = current and (cur_chars + t_chars > max_chars)
            if hit_item_limit or hit_char_limit:
                chunks.append(current)
                current = []
                cur_chars = 0
            current.append(idx)
            cur_chars += t_chars
        if current:
            chunks.append(current)
        return chunks

    def _translate_batch_call(self, texts: List[str]) -> List[str]:
        tgt = CFG.get("target_lang", "Português Brasileiro")
        segments = [f"[{i}] {t}" for i, t in enumerate(texts, 1)]
        prompt = f"Translate each numbered segment to {tgt}:\n\n" + "\n".join(segments)
        try:
            response = self._call_api(make_batch_prompt(), prompt)
        except Exception as e:
            if len(texts) > 1:
                mid = len(texts) // 2
                log.warning(
                    "Batch grande falhou (%d itens): %s. Dividindo em lotes menores.",
                    len(texts),
                    e,
                )
                return self._translate_batch_call(texts[:mid]) + self._translate_batch_call(texts[mid:])
            log.warning("Falha em tradução individual de lote: %s", e)
            return [self._call_ollama(texts[0])]
        parsed = self._parse_batch_response(response, len(texts))
        if parsed is not None:
            return parsed
        parsed = self._parse_batch_simple(response, len(texts))
        if parsed is not None:
            return parsed
        log.warning("Batch parsing falhou, traduzindo individualmente (%d itens)", len(texts))
        return [self._call_ollama(t) for t in texts]

    def _parse_batch_response(self, response: str, expected: int) -> Optional[List[str]]:
        pattern = r"\[(\d+)\]\s*(.*?)(?=\[\d+\]|\Z)"
        matches = re.findall(pattern, response, re.DOTALL)
        if len(matches) < expected:
            return None
        result = {}
        for num_str, text in matches:
            idx = int(num_str)
            if 1 <= idx <= expected:
                result[idx] = self._clean_response(text.strip())
        if len(result) == expected:
            return [result[i] for i in range(1, expected + 1)]
        return None

    def _parse_batch_simple(self, response: str, expected: int) -> Optional[List[str]]:
        lines = [l.strip() for l in response.strip().split("\n") if l.strip()]
        cleaned = []
        for line in lines:
            line = re.sub(r"^\[\d+\]\s*", "", line)
            if line:
                cleaned.append(line)
        if len(cleaned) == expected:
            return [self._clean_response(c) for c in cleaned]
        return None

    def translate_title(self, title: str) -> str:
        tgt = CFG.get("target_lang", "Português Brasileiro")
        src = CFG.get("source_lang", "English")
        prompt_text = (
            f"Translate this RPG book title to {tgt}. "
            f"Keep game-specific proper nouns in {src}. "
            f"Return ONLY the translated title:\n{title}"
        )
        try:
            return self._call_api(make_system_prompt(), prompt_text).strip().strip('"').strip("'")
        except Exception:
            return title

    @staticmethod
    def _should_translate(text: str) -> bool:
        stripped = text.strip()
        if len(stripped) < CFG["min_translatable_chars"]:
            return False
        if re.fullmatch(r"[\d\s\-\u2013\u2014.,:;!?()\[\]{}/|@#$%^&*+=<>~`'\"]+", stripped):
            return False
        if re.fullmatch(r"[A-Z][A-Z0-9\-_]+", stripped):
            return False
        return True

    def _call_ollama(self, text: str) -> str:
        tgt = CFG.get("target_lang", "Português Brasileiro")
        user_message = f"Translate to {tgt}:\n{text}"
        try:
            return self._call_api(make_system_prompt(), user_message)
        except Exception as e:
            log.error("Falha em traducao individual; mantendo texto original: %s", e)
            return text

    def _call_api(self, system_msg: str, user_msg: str, retries: int = 3) -> str:
        timeout_sec = int(CFG.get("ollama_timeout_sec", 300))
        timeout_sec = max(60, min(timeout_sec, 1800))
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "options": CFG.get("ollama_options", {"temperature": 0.4, "top_p": 0.9, "num_ctx": 8192}),
        }).encode("utf-8")
        for attempt in range(retries):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/api/chat",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                r = urllib.request.urlopen(req, timeout=timeout_sec)
                result = json.loads(r.read())
                response = result.get("message", {}).get("content", "").strip()
                return self._clean_response(response)
            except Exception as e:
                if attempt < retries - 1:
                    log.warning("Tentativa %d falhou: %s. Retentando...", attempt + 1, e)
                    time.sleep(2 ** attempt)
                else:
                    log.error("API falhou após %d tentativas: %s", retries, e)
                    raise RuntimeError(f"Ollama API falhou: {e}") from e

    @staticmethod
    def _clean_response(text: str) -> str:
        text = re.sub(r"```[a-z]*\n?", "", text)
        text = text.replace("**", "").replace("__", "")
        if len(text) > 2 and text[0] in ('"', "'", "\u201c") and text[-1] in ('"', "'", "\u201d"):
            text = text[1:-1]
        return text.strip()


# =====================================================================
# MOTOR DE OCR
# =====================================================================

class OCREngine:
    def __init__(self):
        self.backend = "cpu"
        self.provider_hint = "CPUExecutionProvider"
        self._build_engine()

    def _build_engine(self):
        from rapidocr_onnxruntime import RapidOCR

        requested_backend = str(CFG.get("compute_backend", "cpu")).strip().lower()
        if requested_backend not in {"cpu", "gpu"}:
            requested_backend = "cpu"

        kwargs = {}
        if requested_backend == "gpu":
            # On Windows, DirectML is the most compatible GPU path (incluindo AMD).
            if os.name == "nt":
                kwargs["use_dml"] = True
            else:
                kwargs["use_cuda"] = True

        try:
            self.ocr = RapidOCR(**kwargs)
            self.backend = requested_backend
            self.provider_hint = self._detect_provider()
            log.info(
                "RapidOCR inicializado (backend=%s, provider=%s).",
                self.backend,
                self.provider_hint,
            )
            if requested_backend == "gpu" and self.provider_hint.lower().startswith("cpuexecutionprovider"):
                log.warning(
                    "GPU foi solicitado, mas o provider ativo do OCR permaneceu em CPU. "
                    "Verifique onnxruntime-directml/cuda para aceleração real."
                )
            return
        except Exception as e:
            if requested_backend != "gpu":
                raise
            log.warning(
                "Falha ao iniciar RapidOCR com GPU (%s). Fallback para CPU.",
                e,
            )
            self.ocr = RapidOCR()
            self.backend = "cpu"
            self.provider_hint = self._detect_provider()
            log.info(
                "RapidOCR inicializado em fallback CPU (provider=%s).",
                self.provider_hint,
            )

    def _detect_provider(self) -> str:
        providers = []
        for part_name in ("text_det", "text_cls", "text_rec"):
            part = getattr(self.ocr, part_name, None)
            infer_wrapper = getattr(part, "session", None)
            session = getattr(infer_wrapper, "session", None)
            if session is None:
                continue
            try:
                cur = session.get_providers()
                if cur:
                    providers.append(cur[0])
            except Exception:
                continue
        if providers:
            return providers[0]
        return "CPUExecutionProvider"

    def ensure_backend(self):
        requested_backend = str(CFG.get("compute_backend", "cpu")).strip().lower()
        if requested_backend not in {"cpu", "gpu"}:
            requested_backend = "cpu"
        if requested_backend != self.backend:
            log.info(
                "Alteracao de backend OCR detectada (%s -> %s). Reinicializando OCR.",
                self.backend,
                requested_backend,
            )
            self._build_engine()

    def ocr_image(self, img_bytes: bytes) -> list:
        try:
            result, _ = self.ocr(img_bytes)
            return result if result else []
        except Exception as e:
            log.warning("OCR falhou: %s", e)
            return []

    @staticmethod
    def page_is_scanned(page: fitz.Page) -> bool:
        text = page.get_text("text")
        real_chars = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
        return real_chars < CFG["scanned_page_char_threshold"]


# =====================================================================
# GERENCIADOR DE FONTES
# =====================================================================

BUILTIN_FONTS = {
    "helv", "heit", "hebo", "hebi",
    "tiro", "tiit", "tibo", "tibi",
    "cour", "coit", "cobo", "cobi",
    "symb", "zadb",
}


def classify_font(font_name: str) -> str:
    if not font_name:
        return "sans"
    fl = font_name.lower()
    mono_kw = ("courier", "consola", "mono", "fixed", "typewriter", "cour")
    serif_kw = ("times", "georgia", "garamond", "palatino", "book", "roman",
                "serif", "cambria", "tiro", "minion", "caslon", "baskerville")
    symbol_kw = ("symbol", "wingding", "zapf", "dingbat", "webding")
    if any(k in fl for k in symbol_kw):
        return "symbol"
    if any(k in fl for k in mono_kw):
        return "mono"
    if any(k in fl for k in serif_kw):
        return "serif"
    return "sans"


def detect_font_style(font_name: str, flags: int = 0) -> Tuple[bool, bool]:
    fl = font_name.lower() if font_name else ""
    is_bold = "bold" in fl or "black" in fl or "heavy" in fl or bool(flags & (1 << 18))
    is_italic = "italic" in fl or "oblique" in fl or bool(flags & (1 << 1))
    return is_bold, is_italic


def get_fallback_font(font_name: str, flags: int = 0) -> str:
    category = classify_font(font_name)
    is_bold, is_italic = detect_font_style(font_name, flags)
    if category == "symbol":
        return "symb"
    elif category == "mono":
        if is_bold and is_italic: return "cobi"
        if is_bold: return "cobo"
        if is_italic: return "coit"
        return "cour"
    elif category == "serif":
        if is_bold and is_italic: return "tibi"
        if is_bold: return "tibo"
        if is_italic: return "tiit"
        return "tiro"
    else:
        if is_bold and is_italic: return "hebi"
        if is_bold: return "hebo"
        if is_italic: return "heit"
        return "helv"


def get_windows_font_path(bold=False, italic=False) -> str:
    fonts_dir = Path("C:/Windows/Fonts")
    if bold and italic:
        candidates = ["arialbi.ttf", "timesbi.ttf"]
    elif bold:
        candidates = ["arialbd.ttf", "timesbd.ttf"]
    elif italic:
        candidates = ["ariali.ttf", "timesi.ttf"]
    else:
        candidates = ["arial.ttf", "times.ttf"]
    for c in candidates:
        p = fonts_dir / c
        if p.exists():
            return str(p)
    for f in fonts_dir.glob("*.ttf"):
        return str(f)
    return ""


# =====================================================================
# TRADUTOR DE PDF
# =====================================================================

class PDFTranslator:
    def __init__(self, translator: TranslationEngine, ocr_engine: OCREngine):
        self.translator = translator
        self.ocr = ocr_engine
        self._font_pack_cache_key = ""
        self._image_font_paths = []
        self._image_font_choice_cache: Dict[Tuple[int, int, int], Optional[str]] = {}
        self._refresh_image_font_candidates(force=True)

    def translate_pdf(self, input_path: Path, output_path: Path,
                      progress_callback=None):
        self._refresh_image_font_candidates()
        log.info("Abrindo PDF: %s", input_path.name)
        doc = fitz.open(str(input_path))
        total = doc.page_count
        live_preview_enabled = bool(CFG.get("live_preview_enabled", True))

        for page_idx in range(total):
            # Verificar controle externo a cada página
            cmd = check_control(self.translator)
            if cmd == "stop":
                log.info("Pipeline parado pelo usuário na página %d", page_idx)
                doc.save(str(output_path), garbage=4, deflate=True)
                doc.close()
                return "stopped"

            page = doc[page_idx]
            try:
                if self.ocr.page_is_scanned(page):
                    self._translate_scanned_page(doc, page, page_idx)
                else:
                    self._translate_text_page(page)
                    self._translate_image_blocks(doc, page, is_scanned=False)
            except Exception:
                log.error("Erro pag %d:\n%s", page_idx + 1, traceback.format_exc())

            if progress_callback:
                progress_callback(page_idx + 1, total)
            if live_preview_enabled:
                self._save_live_preview(doc, output_path)

        doc.save(str(output_path), garbage=4, deflate=True)
        doc.close()
        log.info("PDF traduzido salvo: %s", output_path.name)
        return "completed"

    @staticmethod
    def _save_live_preview(doc: fitz.Document, output_path: Path):
        tmp_path = output_path.with_suffix(".preview.tmp.pdf")
        try:
            doc.save(str(tmp_path), garbage=1, deflate=True)
            os.replace(str(tmp_path), str(output_path))
        except Exception as e:
            log.warning("Falha ao salvar preview parcial: %s", e)
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    def _translate_text_page(self, page: fitz.Page):
        try:
            page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        except Exception:
            return
        layout_mode = self._get_layout_mode()
        image_rects = self._get_page_image_rects(page) if layout_mode == "hybrid" else []
        block_infos = []
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            lines = block.get("lines", [])
            if not lines:
                continue
            line_texts = self._extract_line_texts(lines)
            table_like = self._is_table_like_block(line_texts)
            if table_like:
                # Preserve table layout better: translate line-by-line inside table-like blocks.
                for line in lines:
                    line_text = "".join(s.get("text", "") for s in line.get("spans", []))
                    line_text = re.sub(r"\s+", " ", line_text).strip()
                    if not line_text:
                        continue
                    line_bbox = line.get("bbox") or block.get("bbox")
                    line_rect = fitz.Rect(line_bbox)
                    if line_rect.is_empty or line_rect.is_infinite:
                        continue
                    if line_rect.width < 5 or line_rect.height < 3:
                        continue
                    style = self._get_dominant_style([line])
                    style["line_count"] = 1
                    style["line_lengths"] = [max(1, len(line_text))]
                    style["line_height_ratio"] = self._estimate_line_height_ratio([line], style["size"], line_rect, 1)
                    style["over_image"] = self._rect_overlaps_any(line_rect, image_rects)
                    style["is_table_like"] = True
                    block_infos.append((line_rect, line_text, style))
                continue
            block_text = self._extract_block_text(lines).strip()
            if not block_text:
                continue
            block_rect = fitz.Rect(block["bbox"])
            if block_rect.is_empty or block_rect.is_infinite:
                continue
            if block_rect.width < 5 or block_rect.height < 3:
                continue
            style = self._get_dominant_style(lines)
            style["line_count"] = max(1, len(line_texts))
            style["line_lengths"] = [max(1, len(t.strip())) for t in line_texts if t.strip()] or [max(1, len(block_text))]
            style["line_height_ratio"] = self._estimate_line_height_ratio(lines, style["size"], block_rect, style["line_count"])
            style["over_image"] = self._rect_overlaps_any(block_rect, image_rects)
            style["is_table_like"] = table_like
            block_infos.append((block_rect, block_text, style))
        if not block_infos:
            return
        original_texts = [b[1] for b in block_infos]
        translated_texts = self.translator.translate_batch(original_texts)
        changes = []
        for i, (rect, orig, style) in enumerate(block_infos):
            trans = translated_texts[i] if i < len(translated_texts) else orig
            trans = self._adapt_text_layout(trans, orig, style, layout_mode)
            if trans and trans != orig:
                changes.append((rect, trans, style))
        if not changes:
            return
        for rect, _, _ in changes:
            page.add_redact_annot(rect)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        for rect, text, style in changes:
            self._insert_block_text(page, rect, text, style, layout_mode)

    def _translate_image_blocks(self, doc: fitz.Document, page: fitz.Page, is_scanned: bool):
        layout_mode = self._get_layout_mode()
        image_mode = self._get_image_text_mode(is_scanned=is_scanned)
        image_list = page.get_images(full=True)
        if not image_list:
            return

        for img_info in image_list:
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue
            img_bytes = base_image.get("image")
            if not img_bytes:
                continue

            ocr_results = self.ocr.ocr_image(img_bytes)
            if not ocr_results:
                continue
            valid_results = [
                r for r in ocr_results
                if len(r) >= 2 and TranslationEngine._should_translate(r[1])
            ]
            if not valid_results:
                continue

            ocr_texts = [r[1] for r in valid_results]
            translations = self.translator.translate_batch(ocr_texts)
            try:
                pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            except Exception:
                continue

            modified = self._render_ocr_text_on_image(
                pil_img=pil_img,
                valid_results=valid_results,
                translations=translations,
                layout_mode=layout_mode,
                image_mode=image_mode,
            )
            if not modified:
                continue

            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            try:
                page.replace_image(xref, stream=buf.getvalue())
            except Exception as e:
                log.warning("Não substituiu imagem xref=%d: %s", xref, e)

    def _translate_scanned_page(self, doc, page, page_idx):
        del doc, page_idx
        layout_mode = self._get_layout_mode()
        # Por padrão, não usa reconstrução IA em página escaneada inteira para evitar custo excessivo.
        image_mode = self._get_image_text_mode(is_scanned=True)
        mat = fitz.Matrix(CFG["render_dpi"] / 72, CFG["render_dpi"] / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("png")
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        ocr_results = self.ocr.ocr_image(img_bytes)
        if not ocr_results:
            return

        valid_results = [
            r for r in ocr_results
            if len(r) >= 2 and TranslationEngine._should_translate(r[1])
        ]
        if not valid_results:
            return

        ocr_texts = [r[1] for r in valid_results]
        translations = self.translator.translate_batch(ocr_texts)
        modified = self._render_ocr_text_on_image(
            pil_img=pil_img,
            valid_results=valid_results,
            translations=translations,
            layout_mode=layout_mode,
            image_mode=image_mode,
        )
        if modified:
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            page.clean_contents()
            page_rect = page.rect
            page.add_redact_annot(page_rect)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)
            page.insert_image(page_rect, stream=buf.getvalue())

    # -- Utilitários --

    @staticmethod
    def _get_image_text_mode(is_scanned: bool) -> str:
        mode = str(CFG.get("image_text_mode", "legacy")).strip().lower()
        if mode not in {"legacy", "ai_rebuild"}:
            mode = "legacy"
        if is_scanned and CFG.get("image_ai_selectable_only", True):
            return "legacy"
        return mode

    def _render_ocr_text_on_image(
        self,
        pil_img: Image.Image,
        valid_results: list,
        translations: list,
        layout_mode: str,
        image_mode: str,
    ) -> bool:
        entries = self._prepare_image_ocr_entries(pil_img, valid_results, translations)
        if not entries:
            return False

        if image_mode == "ai_rebuild" and cv2 is not None:
            self._inpaint_entries_with_ai(pil_img, entries)

        draw = ImageDraw.Draw(pil_img)
        modified = False
        for entry in entries:
            x0, y0, x1, y1 = entry["bbox"]
            if (x1 - x0) < 5 or (y1 - y0) < 5:
                continue

            if image_mode == "legacy" or cv2 is None:
                draw.rectangle([x0, y0, x1, y1], fill=entry["background_color"])

            font_size = max(8, int((y1 - y0) * 0.75))
            preferred_font = self._choose_image_font_path(entry["translated"], x1 - x0, y1 - y0)
            pil_font = self._get_pil_font(font_size, preferred_path=preferred_font)
            self._draw_fitted_text(
                draw,
                entry["translated"],
                x0,
                y0,
                x1,
                y1,
                pil_font,
                font_size,
                fill_color=entry["text_color"],
                source_line_count=entry["source_line_count"],
                mode=layout_mode,
                preferred_font_path=preferred_font,
            )
            modified = True
        return modified

    def _prepare_image_ocr_entries(self, pil_img: Image.Image, valid_results: list, translations: list) -> List[dict]:
        entries: List[dict] = []
        for idx, result in enumerate(valid_results):
            original = str(result[1] if len(result) > 1 else "").strip()
            translated = str(translations[idx] if idx < len(translations) else original).strip()
            if not translated or translated == original:
                continue

            bbox_points = result[0]
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            if (x1 - x0) < 5 or (y1 - y0) < 5:
                continue

            entries.append({
                "points": bbox_points,
                "bbox": (x0, y0, x1, y1),
                "original": original,
                "translated": translated,
                "source_line_count": max(1, len(original.splitlines())),
                "background_color": self._sample_background_color(pil_img, x0, y0, x1, y1),
                "text_color": self._sample_text_color(pil_img, x0, y0, x1, y1),
            })
        return entries

    def _inpaint_entries_with_ai(self, pil_img: Image.Image, entries: List[dict]):
        np_img = np.array(pil_img)
        cv_img = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)
        inpaint_radius = int(CFG.get("image_inpaint_radius", 3))
        inpaint_radius = max(1, min(12, inpaint_radius))

        for entry in entries:
            points = np.array(entry["points"], dtype=np.int32).reshape(-1, 2)
            if points.size == 0:
                continue
            mask = np.zeros(cv_img.shape[:2], dtype=np.uint8)
            cv2.fillPoly(mask, [points], 255)
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.dilate(mask, kernel, iterations=1)
            cv_img = cv2.inpaint(cv_img, mask, inpaint_radius, cv2.INPAINT_TELEA)

        rebuilt = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        pil_img.paste(Image.fromarray(rebuilt))

    def _extract_block_text(self, lines: list) -> str:
        parts = []
        for line in lines:
            line_text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if line_text:
                parts.append(line_text)
        return " ".join(parts)

    def _extract_line_texts(self, lines: list) -> List[str]:
        results: List[str] = []
        for line in lines:
            line_text = "".join(s.get("text", "") for s in line.get("spans", []))
            line_text = re.sub(r"\s+", " ", line_text).strip()
            if line_text:
                results.append(line_text)
        return results

    @staticmethod
    def _is_table_like_block(line_texts: List[str]) -> bool:
        if len(line_texts) < 3:
            return False
        short_lines = sum(1 for ln in line_texts if len(ln) <= 36)
        numeric_lines = sum(1 for ln in line_texts if re.search(r"\d", ln))
        divider_lines = sum(1 for ln in line_texts if any(ch in ln for ch in ("|", ";", ":", "\t")))
        if short_lines >= max(2, int(len(line_texts) * 0.6)) and numeric_lines >= 2:
            return True
        if divider_lines >= 1 and short_lines >= 2:
            return True
        return False

    @staticmethod
    def _estimate_line_height_ratio(lines: list, font_size: float, block_rect: fitz.Rect, line_count: int) -> float:
        heights = []
        for line in lines:
            bbox = line.get("bbox")
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                heights.append(max(1.0, float(bbox[3]) - float(bbox[1])))
        if heights and font_size > 0:
            avg_height = sum(heights) / len(heights)
            return max(1.0, min(1.9, avg_height / font_size))
        if line_count > 0 and font_size > 0:
            approx = (block_rect.height / line_count) / font_size
            return max(1.0, min(1.9, approx))
        return 1.2

    @staticmethod
    def _get_page_image_rects(page: fitz.Page) -> List[fitz.Rect]:
        rects: List[fitz.Rect] = []
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                for r in page.get_image_rects(xref):
                    rects.append(fitz.Rect(r))
            except Exception:
                continue
        return rects

    @staticmethod
    def _rect_overlaps_any(rect: fitz.Rect, others: List[fitz.Rect]) -> bool:
        return any(not (rect & other).is_empty for other in others)

    @staticmethod
    def _get_layout_mode() -> str:
        mode = str(CFG.get("validation_method", "structural")).strip().lower()
        if mode not in {"structural", "char_count", "hybrid"}:
            return "structural"
        return mode

    def _adapt_text_layout(self, translated: str, original: str, style: dict, mode: str) -> str:
        raw = (translated or "").replace("\r\n", "\n")
        normalized_lines = []
        for line in raw.splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            if clean:
                normalized_lines.append(clean)
        text_multiline = "\n".join(normalized_lines) if normalized_lines else re.sub(r"\s+", " ", raw).strip()
        if not text_multiline:
            return original

        line_count = max(1, int(style.get("line_count", 1)))
        line_lengths = style.get("line_lengths") or [max(1, len(original or text_multiline))]
        table_like = bool(style.get("is_table_like"))

        if table_like:
            return self._rewrap_text_with_budgets(
                text=text_multiline,
                line_count=line_count,
                line_budgets=line_lengths,
                expansion=1.08,
                keep_exact_lines=True,
            )

        if mode == "structural":
            return text_multiline.replace("\n", " ")

        if mode == "char_count":
            return self._rewrap_text_with_budgets(
                text=text_multiline.replace("\n", " "),
                line_count=line_count,
                line_budgets=line_lengths,
                expansion=1.05,
                keep_exact_lines=False,
            )

        # hybrid: preserva número de linhas do bloco original e mantém texto no mesmo espaço
        return self._rewrap_text_with_budgets(
            text=text_multiline,
            line_count=line_count,
            line_budgets=line_lengths,
            expansion=1.25,
            keep_exact_lines=True,
        )

    @staticmethod
    def _rewrap_text_with_budgets(text: str, line_count: int, line_budgets: List[int],
                                  expansion: float, keep_exact_lines: bool) -> str:
        words = text.split()
        if not words or line_count <= 1:
            return text.strip()

        budgets = list(line_budgets[:line_count])
        if not budgets:
            budgets = [max(8, len(text) // max(1, line_count))] * line_count
        while len(budgets) < line_count:
            budgets.append(budgets[-1])
        budgets = [max(4, int(b * expansion)) for b in budgets]

        lines = [""] * line_count
        idx = 0
        for word in words:
            if idx >= line_count:
                lines[-1] = (lines[-1] + " " + word).strip()
                continue
            candidate = (lines[idx] + " " + word).strip()
            if not lines[idx] or len(candidate) <= budgets[idx]:
                lines[idx] = candidate
            else:
                idx += 1
                if idx >= line_count:
                    lines[-1] = (lines[-1] + " " + word).strip()
                else:
                    lines[idx] = word

        if keep_exact_lines:
            return "\n".join(lines)

        compact = [ln for ln in lines if ln.strip()]
        return "\n".join(compact) if compact else text.strip()

    def _get_dominant_style(self, lines: list) -> dict:
        styles: Dict[tuple, int] = {}
        for line in lines:
            for span in line.get("spans", []):
                key = (
                    span.get("font", "helv"),
                    round(span.get("size", 10), 1),
                    span.get("color", 0),
                    span.get("flags", 0),
                )
                styles[key] = styles.get(key, 0) + len(span.get("text", "").strip())
        if not styles:
            return {"font": "helv", "size": 10, "color": (0, 0, 0), "flags": 0}
        best = max(styles, key=styles.get)
        return {
            "font": best[0],
            "size": best[1],
            "color": self._int_to_rgb(best[2]),
            "flags": best[3],
        }

    def _insert_block_text(self, page, rect, text, style, mode: str = "structural"):
        font_name = get_fallback_font(style["font"], style.get("flags", 0))
        original_size = style["size"]
        color = style["color"]
        base_ratio = CFG["min_font_ratio"]
        if style.get("is_table_like"):
            base_ratio = max(base_ratio, 0.78)
        elif mode == "structural":
            base_ratio = max(base_ratio, 0.76)
        if mode == "char_count":
            base_ratio = min(base_ratio, 0.62)
        elif mode == "hybrid":
            base_ratio = min(base_ratio, 0.58)
        min_size = max(4.0, CFG["min_font_size"], original_size * base_ratio)
        lineheight = style.get("line_height_ratio", 1.2) if mode == "hybrid" else None

        texts_to_try = [text]
        if mode == "hybrid":
            compact = re.sub(r"\s+", " ", text).replace(" ,", ",").replace(" .", ".").strip()
            if compact and compact != text:
                texts_to_try.append(compact)

        for candidate_text in texts_to_try:
            current_size = original_size
            shrink_step = 0.25 if style.get("is_table_like") or mode == "structural" else 0.5
            while current_size >= min_size:
                kwargs = {
                    "fontname": font_name,
                    "fontsize": current_size,
                    "color": color,
                    "align": fitz.TEXT_ALIGN_LEFT,
                }
                if lineheight is not None:
                    kwargs["lineheight"] = lineheight
                rc = page.insert_textbox(rect, candidate_text, **kwargs)
                if rc >= 0:
                    return
                current_size -= shrink_step

        fallback_kwargs = {
            "fontname": font_name,
            "fontsize": min_size,
            "color": color,
            "align": fitz.TEXT_ALIGN_LEFT,
        }
        if lineheight is not None:
            fallback_kwargs["lineheight"] = lineheight
        page.insert_textbox(rect, texts_to_try[-1], **fallback_kwargs)

    def _draw_fitted_text(self, draw, text, x0, y0, x1, y1, font, base_size,
                          fill_color="black", source_line_count: int = 1, mode: str = "structural",
                          preferred_font_path: Optional[str] = None):
        box_w = x1 - x0
        box_h = y1 - y0
        current_size = base_size
        while current_size >= 6:
            test_font = self._get_pil_font(current_size, preferred_path=preferred_font_path)
            lines = self._layout_image_text(
                draw=draw,
                text=text,
                font=test_font,
                max_width=box_w,
                target_lines=max(1, source_line_count),
                mode=mode,
            )
            if not lines:
                current_size -= 1
                continue

            max_w = max(draw.textlength(line, font=test_font) for line in lines)
            line_h_bbox = draw.textbbox((0, 0), "Ag", font=test_font)
            line_h = max(1, (line_h_bbox[3] - line_h_bbox[1]))
            spacing = max(1, int(current_size * 0.15))
            total_h = len(lines) * line_h + (len(lines) - 1) * spacing

            if max_w <= box_w * 1.05 and total_h <= box_h * 1.1:
                start_y = y0
                if mode == "hybrid" and total_h < box_h:
                    start_y = y0 + max(0, (box_h - total_h) / 2)
                y_cursor = start_y
                for line in lines:
                    draw.text((x0 + 1, y_cursor), line, fill=fill_color, font=test_font)
                    y_cursor += line_h + spacing
                return
            current_size -= 1
        tiny_font = self._get_pil_font(max(6, current_size), preferred_path=preferred_font_path)
        draw.text((x0 + 1, y0), text, fill=fill_color, font=tiny_font)

    @staticmethod
    def _layout_image_text(draw, text: str, font, max_width: float, target_lines: int, mode: str) -> List[str]:
        words = text.split()
        if not words:
            return [text]

        lines: List[str] = []
        current = ""
        for word in words:
            candidate = (current + " " + word).strip()
            if not current or draw.textlength(candidate, font=font) <= max_width * 1.02:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

        if mode == "hybrid":
            while len(lines) > target_lines and len(lines) > 1:
                lines[-2] = (lines[-2] + " " + lines[-1]).strip()
                lines.pop()
            while len(lines) < target_lines:
                idx = max(range(len(lines)), key=lambda i: len(lines[i]))
                parts = lines[idx].split()
                if len(parts) < 2:
                    break
                cut = len(parts) // 2
                lines[idx:idx + 1] = [" ".join(parts[:cut]), " ".join(parts[cut:])]
        return lines

    def _build_image_font_candidates(self) -> List[str]:
        candidates: List[str] = []

        font_pack_dir_cfg = Path(str(CFG.get("font_pack_dir", "assets/fonts")))
        font_pack_dir = font_pack_dir_cfg if font_pack_dir_cfg.is_absolute() else (BASE_DIR / font_pack_dir_cfg)
        if font_pack_dir.exists():
            for ext in ("*.ttf", "*.otf", "*.ttc"):
                for fp in sorted(font_pack_dir.glob(ext)):
                    candidates.append(str(fp))

        win_fonts = Path("C:/Windows/Fonts")
        preferred_names = [
            "arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf",
            "calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf",
            "times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf",
            "consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf",
            "cambria.ttc", "segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf",
        ]
        for name in preferred_names:
            p = win_fonts / name
            if p.exists():
                candidates.append(str(p))

        # Deduplicar mantendo ordem.
        seen = set()
        unique = []
        for path in candidates:
            if path.lower() in seen:
                continue
            seen.add(path.lower())
            unique.append(path)
        return unique

    def _refresh_image_font_candidates(self, force: bool = False):
        cache_key = str(CFG.get("font_pack_dir", "assets/fonts")).strip().lower()
        if not force and cache_key == self._font_pack_cache_key:
            return
        self._font_pack_cache_key = cache_key
        self._image_font_paths = self._build_image_font_candidates()
        self._image_font_choice_cache.clear()

    def _choose_image_font_path(self, text: str, box_w: float, box_h: float) -> Optional[str]:
        if not self._image_font_paths:
            return None
        key = (max(1, len(text)), int(max(1, box_w) // 6), int(max(1, box_h) // 4))
        if key in self._image_font_choice_cache:
            return self._image_font_choice_cache[key]

        probe_text = text[: min(24, len(text))] or "Aa"
        probe_size = max(10, int(min(box_h, 64) * 0.7))
        best_path = None
        best_score = None

        for path in self._image_font_paths[:32]:
            try:
                probe_font = ImageFont.truetype(path, probe_size)
                bbox = probe_font.getbbox(probe_text)
                w = max(1, bbox[2] - bbox[0])
                h = max(1, bbox[3] - bbox[1])
            except Exception:
                continue

            wr = box_w / w
            hr = box_h / h
            score = abs(wr - hr) + abs((w / h) - (max(1, len(probe_text)) / 2.2))
            if best_score is None or score < best_score:
                best_score = score
                best_path = path

        self._image_font_choice_cache[key] = best_path
        return best_path

    @staticmethod
    def _int_to_rgb(color) -> tuple:
        if isinstance(color, (list, tuple)) and len(color) >= 3:
            return tuple(float(c) for c in color[:3])
        if isinstance(color, int):
            r = ((color >> 16) & 255) / 255.0
            g = ((color >> 8) & 255) / 255.0
            b = (color & 255) / 255.0
            return (r, g, b)
        return (0, 0, 0)

    @staticmethod
    def _sample_background_color(img, x0, y0, x1, y1) -> tuple:
        w, h = img.size
        margin = 3
        samples = []
        x0i, y0i, x1i, y1i = int(x0), int(y0), int(x1), int(y1)
        points = [
            (max(0, x0i - margin), max(0, y0i - margin)),
            (min(w - 1, x1i + margin), max(0, y0i - margin)),
            (max(0, x0i - margin), min(h - 1, y1i + margin)),
            (min(w - 1, x1i + margin), min(h - 1, y1i + margin)),
            (max(0, (x0i + x1i) // 2), max(0, y0i - margin)),
            (max(0, (x0i + x1i) // 2), min(h - 1, y1i + margin)),
            (max(0, x0i - margin), max(0, (y0i + y1i) // 2)),
            (min(w - 1, x1i + margin), max(0, (y0i + y1i) // 2)),
        ]
        for px, py in points:
            samples.append(img.getpixel((px, py)))
        return tuple(int(sum(c[i] for c in samples) / len(samples)) for i in range(3))

    @staticmethod
    def _sample_text_color(img, x0, y0, x1, y1):
        """Sample likely foreground color preserving contrast versus local background."""
        x0i, y0i, x1i, y1i = int(x0), int(y0), int(x1), int(y1)
        w, h = img.size
        x0i, y0i = max(0, x0i), max(0, y0i)
        x1i, y1i = min(w - 1, x1i), min(h - 1, y1i)
        if x1i <= x0i or y1i <= y0i:
            return "black"

        bg = PDFTranslator._sample_background_color(img, x0, y0, x1, y1)

        pixels = []
        step_y = max(1, (y1i - y0i) // 10)
        step_x = max(1, (x1i - x0i) // 10)
        for py in range(y0i, y1i + 1, step_y):
            for px in range(x0i, x1i + 1, step_x):
                pixels.append(img.getpixel((px, py)))
        if not pixels:
            return "black"

        by_contrast = sorted(
            pixels,
            key=lambda p: abs(int(p[0]) - int(bg[0])) + abs(int(p[1]) - int(bg[1])) + abs(int(p[2]) - int(bg[2])),
            reverse=True,
        )
        take = by_contrast[: max(3, len(by_contrast) // 3)]
        contrast = sum(abs(int(p[0]) - int(bg[0])) + abs(int(p[1]) - int(bg[1])) + abs(int(p[2]) - int(bg[2])) for p in take) / len(take)
        if contrast < 24:
            # Fallback para preto/branco conforme luminosidade do fundo.
            bg_luma = (bg[0] + bg[1] + bg[2]) / 3
            return (0, 0, 0) if bg_luma > 140 else (245, 245, 245)

        r = int(sum(int(p[0]) for p in take) / len(take))
        g = int(sum(int(p[1]) for p in take) / len(take))
        b = int(sum(int(p[2]) for p in take) / len(take))
        return (r, g, b)

    @staticmethod
    def _get_pil_font(size: int, bold=False, italic=False, preferred_path: Optional[str] = None):
        if preferred_path:
            try:
                return ImageFont.truetype(preferred_path, size)
            except Exception:
                pass

        font_path = get_windows_font_path(bold=bold, italic=italic)
        if font_path:
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()


# =====================================================================
# PIPELINE PRINCIPAL
# =====================================================================

class TranslationPipeline:
    def __init__(self):
        ensure_previous_lang_dir()
        for d in (INPUT_DIR, TRANSLATING_DIR, OUTPUT_DIR, ENGLISH_DIR):
            d.mkdir(parents=True, exist_ok=True)
        self.translator = TranslationEngine()
        self.ocr = OCREngine()
        self.pdf_translator = PDFTranslator(self.translator, self.ocr)

    def run(self, retranslate_file: str = None):
        """Executa o pipeline. Se retranslate_file, retraduz apenas esse livro."""
        write_control({"command": "run", "model": self.translator.model})
        self._recover_translating_dir()
        self.ocr.ensure_backend()

        if retranslate_file:
            result = self._retranslate_single(retranslate_file)
            update_state(status="idle", preview_pdf=None)
            return result

        pdfs = self._get_sorted_pdfs()
        if not pdfs:
            log.info("Nenhum PDF encontrado em %s", INPUT_DIR)
            update_state(status="idle", total_books=0, preview_pdf=None)
            return

        update_state(
            status="running",
            total_books=len(pdfs),
            pipeline_start=datetime.now().isoformat(),
            model=self.translator.model,
            preview_pdf=None,
        )

        log.info("=" * 60)
        log.info("PIPELINE DE TRADUÇÃO INICIADO")
        log.info("Total de livros: %d", len(pdfs))
        log.info("Ordem: menor -> maior")
        log.info("=" * 60)

        completed = []
        for i, (size, pdf_path) in enumerate(pdfs, 1):
            # Reload config to pick up live changes (language, options, order)
            CFG.update(load_config())
            self.ocr.ensure_backend()

            ctrl = check_control(self.translator)
            if ctrl == "stop":
                log.info("Pipeline parado pelo usuário.")
                update_state(status="idle", preview_pdf=None)
                return

            # Handle dynamic file removal
            if not pdf_path.exists():
                log.info("Arquivo removido, pulando: %s", pdf_path.name)
                continue

            size_mb = size / (1024 * 1024)
            log.info(
                "\n[%d/%d] Processando: %s (%.1f MB)",
                i, len(pdfs), pdf_path.name, size_mb,
            )
            update_state(
                status="running",
                book_index=i,
                total_books=len(pdfs),
                current_book={
                    "filename": pdf_path.name,
                    "size_mb": round(size_mb, 2),
                    "start_time": datetime.now().isoformat(),
                },
                current_page=0,
                total_pages=0,
            )
            try:
                result = self._process_single_book(pdf_path)
                if result == "stopped":
                    update_state(status="idle", preview_pdf=None)
                    return
                completed.append(pdf_path.name)
                update_state(completed_books=completed, book_just_completed=pdf_path.name)
            except Exception:
                log.error("ERRO '%s':\n%s", pdf_path.name, traceback.format_exc())
                self._recover_translating_dir()

        update_state(status="idle", preview_pdf=None)
        log.info("\n" + "=" * 60)
        log.info("PIPELINE CONCLUÍDO")
        log.info("=" * 60)

    def _retranslate_single(self, filename: str):
        """Retraduz um único livro (move de traduzidos/na-lingua-anterior de volta)."""
        # Procurar o original em na-lingua-anterior/
        orig = ENGLISH_DIR / filename
        if not orig.exists():
            # Talvez o arquivo esteja em traduzidos com nome PT
            log.error("Arquivo original não encontrado: %s", filename)
            update_state(status="idle", preview_pdf=None)
            return
        # Mover de volta para input
        dest = INPUT_DIR / filename
        shutil.copy2(str(orig), str(dest))
        log.info("Retraduzindo: %s", filename)

        update_state(
            status="running",
            book_index=1,
            total_books=1,
            current_book={"filename": filename, "size_mb": round(orig.stat().st_size / 1048576, 2),
                          "start_time": datetime.now().isoformat()},
            preview_pdf=None,
        )

        try:
            self._process_single_book(dest)
        except Exception:
            log.error("ERRO retraduzindo '%s':\n%s", filename, traceback.format_exc())

        update_state(status="idle", preview_pdf=None)

    def _get_sorted_pdfs(self):
        pt_indicators = [
            "traduzido", "portugu", "personagem", "talentos",
            "pt-br", "pt_br", "traducao",
        ]
        already_done = {f.name for f in ENGLISH_DIR.iterdir() if f.suffix.lower() == ".pdf"}
        pdfs = []
        for f in INPUT_DIR.iterdir():
            if f.suffix.lower() != ".pdf" or not f.is_file():
                continue
            if f.name in already_done:
                continue
            name_lower = f.stem.lower()
            if any(ind in name_lower for ind in pt_indicators):
                log.info("Pulando (parece PT): %s", f.name)
                continue
            pdfs.append((f.stat().st_size, f))
        sort_order = CFG.get("sort_order", "smallest_first")
        custom_order = CFG.get("custom_order", [])
        if sort_order == "largest_first":
            pdfs.sort(key=lambda x: x[0], reverse=True)
        elif sort_order == "custom" and custom_order:
            order_map = {name: i for i, name in enumerate(custom_order)}
            pdfs.sort(key=lambda x: order_map.get(x[1].name, 999999))
        else:  # smallest_first (default)
            pdfs.sort(key=lambda x: x[0])
        # Priority: retranslate queue items come first
        retranslate_queue = CFG.get("retranslate_queue", [])
        if retranslate_queue:
            priority = []
            normal = []
            for item in pdfs:
                if item[1].name in retranslate_queue:
                    priority.append(item)
                else:
                    normal.append(item)
            pdfs = priority + normal
        return pdfs

    def _process_single_book(self, pdf_path: Path) -> str:
        working_path = TRANSLATING_DIR / pdf_path.name
        if pdf_path.parent != TRANSLATING_DIR:
            shutil.move(str(pdf_path), str(working_path))
        log.info("  -> Movido para traduzindo/")

        # Contar páginas para estado
        try:
            doc_check = fitz.open(str(working_path))
            total_pages = doc_check.page_count
            doc_check.close()
        except Exception:
            total_pages = 0
        translated_temp = TRANSLATING_DIR / f"{pdf_path.stem}_PT.pdf"
        update_state(total_pages=total_pages, current_page=0, preview_pdf=translated_temp.name)

        def on_progress(current, total):
            update_state(current_page=current, total_pages=total)

        result = self.pdf_translator.translate_pdf(working_path, translated_temp,
                                                   progress_callback=on_progress)
        if result == "stopped":
            # Recuperar arquivo
            dest = INPUT_DIR / pdf_path.name
            if not dest.exists():
                shutil.move(str(working_path), str(dest))
            update_state(preview_pdf=None)
            self._cleanup_translating_dir()
            return "stopped"

        pt_title = self._generate_pt_filename(pdf_path.stem)
        pt_filename = self._sanitize_filename(f"{pt_title} traduzido por Tradutor Universal de PDFs.pdf")
        final_path = OUTPUT_DIR / pt_filename
        shutil.move(str(translated_temp), str(final_path))
        log.info("  -> Traduzido: %s", pt_filename)

        english_path = ENGLISH_DIR / pdf_path.name
        shutil.move(str(working_path), str(english_path))
        log.info("  -> Original -> na-lingua-anterior/")
        update_state(preview_pdf=None)
        self._cleanup_translating_dir()
        # Remove from retranslate queue if present
        rq = CFG.get("retranslate_queue", [])
        if pdf_path.name in rq:
            rq.remove(pdf_path.name)
            CFG["retranslate_queue"] = rq
            save_config(CFG)
        return "completed"

    def _generate_pt_filename(self, stem: str) -> str:
        clean = re.sub(r"\s*[-\u2013\u2014]\s*", " - ", stem)
        pt_indicators = ["traduzido", "portugu", "personagem", "monstro"]
        if any(ind in clean.lower() for ind in pt_indicators):
            return clean
        try:
            translated = self.translator.translate_title(clean)
            if translated and len(translated) > 3:
                return translated
        except Exception:
            log.warning("Não traduziu título '%s'", stem)
        return clean

    def _recover_translating_dir(self):
        for f in TRANSLATING_DIR.iterdir():
            if f.suffix.lower() == ".pdf" and not f.stem.endswith("_PT"):
                dest = INPUT_DIR / f.name
                if not dest.exists():
                    try:
                        shutil.move(str(f), str(dest))
                        log.info("Recuperado de traduzindo/: %s", f.name)
                    except PermissionError:
                        log.warning("Arquivo em uso, ignorando recuperação: %s", f.name)
        self._cleanup_translating_dir()

    @staticmethod
    def _cleanup_translating_dir():
        for f in TRANSLATING_DIR.iterdir():
            try:
                if f.is_file():
                    f.unlink()
                elif f.is_dir():
                    shutil.rmtree(f)
            except Exception:
                pass

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        for ch in '<>:"/\\|?*':
            name = name.replace(ch, "")
        return name.strip()[:200]


# =====================================================================
# MAIN
# =====================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--retranslate", type=str, default=None,
                        help="Nome do arquivo original para retraduzir")
    args = parser.parse_args()

    try:
        pipeline = TranslationPipeline()
        pipeline.run(retranslate_file=args.retranslate)
    except KeyboardInterrupt:
        log.info("\nInterrompido pelo usuário.")
        update_state(status="stopped")
        sys.exit(1)
    except Exception as e:
        log.error("Erro fatal: %s\n%s", e, traceback.format_exc())
        update_state(status="error", error=str(e))
        sys.exit(1)
