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
from PIL import Image, ImageDraw, ImageFont

# =====================================================================
# CONFIGURAÇÃO - lida do config.json
# =====================================================================

ENGINE_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = ENGINE_DIR.parent
BASE_DIR = PROJECT_DIR.parent  # testecode/

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
    "source_lang": "English",
    "target_lang": "Português Brasileiro",
    "sort_order": "smallest_first",
    "custom_order": [],
    "ollama_options": {
        "temperature": 0.2,
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

INPUT_DIR = Path(CFG["base_dir"]) / "livros-para-traduzir"
TRANSLATING_DIR = Path(CFG["base_dir"]) / "traduzindo"
OUTPUT_DIR = Path(CFG["base_dir"]) / "traduzidos"
ENGLISH_DIR = Path(CFG["base_dir"]) / "em-inges"
LOG_FILE = Path(CFG["base_dir"]) / "translation.log"

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
        max_batch = CFG["max_batch_size"]
        for batch_start in range(0, len(indices_to_translate), max_batch):
            batch_indices = indices_to_translate[batch_start:batch_start + max_batch]
            batch_texts = [texts[i].strip() for i in batch_indices]
            translated_batch = self._translate_batch_call(batch_texts)
            for j, idx in enumerate(batch_indices):
                if j < len(translated_batch):
                    results[idx] = translated_batch[j]
                    self.cache[texts[idx].strip()] = translated_batch[j]
                else:
                    results[idx] = self.translate(texts[idx])
        return results

    def _translate_batch_call(self, texts: List[str]) -> List[str]:
        tgt = CFG.get("target_lang", "Português Brasileiro")
        segments = [f"[{i}] {t}" for i, t in enumerate(texts, 1)]
        prompt = f"Translate each numbered segment to {tgt}:\n\n" + "\n".join(segments)
        response = self._call_api(make_batch_prompt(), prompt)
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
        return self._call_api(make_system_prompt(), prompt_text).strip().strip('"').strip("'")

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
        return self._call_api(make_system_prompt(), user_message)

    def _call_api(self, system_msg: str, user_msg: str, retries: int = 3) -> str:
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "options": CFG.get("ollama_options", {"temperature": 0.2, "top_p": 0.9, "num_ctx": 8192}),
        }).encode("utf-8")
        for attempt in range(retries):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/api/chat",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                r = urllib.request.urlopen(req, timeout=180)
                result = json.loads(r.read())
                response = result.get("message", {}).get("content", "").strip()
                return self._clean_response(response)
            except Exception as e:
                if attempt < retries - 1:
                    log.warning("Tentativa %d falhou: %s. Retentando...", attempt + 1, e)
                    time.sleep(2 ** attempt)
                else:
                    log.error("API falhou após %d tentativas: %s", retries, e)
                    return user_msg.split("\n", 1)[-1]

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
        from rapidocr_onnxruntime import RapidOCR
        self.ocr = RapidOCR()
        log.info("RapidOCR inicializado.")

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

    def translate_pdf(self, input_path: Path, output_path: Path,
                      progress_callback=None):
        log.info("Abrindo PDF: %s", input_path.name)
        doc = fitz.open(str(input_path))
        total = doc.page_count

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
                    self._translate_image_blocks(doc, page)
            except Exception:
                log.error("Erro pag %d:\n%s", page_idx + 1, traceback.format_exc())

            if progress_callback:
                progress_callback(page_idx + 1, total)

        doc.save(str(output_path), garbage=4, deflate=True)
        doc.close()
        log.info("PDF traduzido salvo: %s", output_path.name)
        return "completed"

    def _translate_text_page(self, page: fitz.Page):
        try:
            page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        except Exception:
            return
        block_infos = []
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            lines = block.get("lines", [])
            if not lines:
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
            block_infos.append((block_rect, block_text, style))
        if not block_infos:
            return
        original_texts = [b[1] for b in block_infos]
        translated_texts = self.translator.translate_batch(original_texts)
        changes = []
        for i, (rect, orig, style) in enumerate(block_infos):
            trans = translated_texts[i] if i < len(translated_texts) else orig
            if trans and trans != orig:
                changes.append((rect, trans, style))
        if not changes:
            return
        for rect, _, _ in changes:
            page.add_redact_annot(rect)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        for rect, text, style in changes:
            self._insert_block_text(page, rect, text, style)

    def _translate_image_blocks(self, doc: fitz.Document, page: fitz.Page):
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
            valid_results = [r for r in ocr_results
                           if len(r) >= 2 and TranslationEngine._should_translate(r[1])]
            if not valid_results:
                continue
            ocr_texts = [r[1] for r in valid_results]
            translations = self.translator.translate_batch(ocr_texts)
            try:
                pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            except Exception:
                continue
            draw = ImageDraw.Draw(pil_img)
            modified = False
            for idx, result in enumerate(valid_results):
                trans = translations[idx] if idx < len(translations) else result[1]
                if trans == result[1]:
                    continue
                bbox_points = result[0]
                xs = [p[0] for p in bbox_points]
                ys = [p[1] for p in bbox_points]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
                if (x1 - x0) < 5 or (y1 - y0) < 5:
                    continue
                text_color = self._sample_text_color(pil_img, x0, y0, x1, y1)
                bg = self._sample_background_color(pil_img, x0, y0, x1, y1)
                draw.rectangle([x0, y0, x1, y1], fill=bg)
                font_size = max(8, int((y1 - y0) * 0.75))
                pil_font = self._get_pil_font(font_size)
                self._draw_fitted_text(draw, trans, x0, y0, x1, y1, pil_font, font_size, fill_color=text_color)
                modified = True
            if modified:
                buf = io.BytesIO()
                pil_img.save(buf, format="PNG")
                try:
                    page.replace_image(xref, stream=buf.getvalue())
                except Exception as e:
                    log.warning("Não substituiu imagem xref=%d: %s", xref, e)

    def _translate_scanned_page(self, doc, page, page_idx):
        mat = fitz.Matrix(CFG["render_dpi"] / 72, CFG["render_dpi"] / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("png")
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        ocr_results = self.ocr.ocr_image(img_bytes)
        if not ocr_results:
            return
        valid_results = [r for r in ocr_results
                        if len(r) >= 2 and TranslationEngine._should_translate(r[1])]
        if not valid_results:
            return
        ocr_texts = [r[1] for r in valid_results]
        translations = self.translator.translate_batch(ocr_texts)
        draw = ImageDraw.Draw(pil_img)
        modified = False
        for idx, result in enumerate(valid_results):
            trans = translations[idx] if idx < len(translations) else result[1]
            if trans == result[1]:
                continue
            bbox_points = result[0]
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            box_h = y1 - y0
            if box_h < 3:
                continue
            text_color = self._sample_text_color(pil_img, x0, y0, x1, y1)
            bg = self._sample_background_color(pil_img, x0, y0, x1, y1)
            draw.rectangle([x0, y0, x1, y1], fill=bg)
            font_size = max(8, int(box_h * 0.78))
            pil_font = self._get_pil_font(font_size)
            self._draw_fitted_text(draw, trans, x0, y0, x1, y1, pil_font, font_size, fill_color=text_color)
            modified = True
        if modified:
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            page.clean_contents()
            page_rect = page.rect
            page.add_redact_annot(page_rect)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)
            page.insert_image(page_rect, stream=buf.getvalue())

    # -- Utilitários --

    def _extract_block_text(self, lines: list) -> str:
        parts = []
        for line in lines:
            line_text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if line_text:
                parts.append(line_text)
        return " ".join(parts)

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

    def _insert_block_text(self, page, rect, text, style):
        font_name = get_fallback_font(style["font"], style.get("flags", 0))
        original_size = style["size"]
        color = style["color"]
        min_size = max(CFG["min_font_size"], original_size * CFG["min_font_ratio"])
        current_size = original_size
        while current_size >= min_size:
            rc = page.insert_textbox(
                rect, text,
                fontname=font_name, fontsize=current_size,
                color=color, align=fitz.TEXT_ALIGN_LEFT,
            )
            if rc >= 0:
                return
            current_size -= 0.5
        page.insert_textbox(
            rect, text,
            fontname=font_name, fontsize=min_size,
            color=color, align=fitz.TEXT_ALIGN_LEFT,
        )

    def _draw_fitted_text(self, draw, text, x0, y0, x1, y1, font, base_size, fill_color="black"):
        box_w = x1 - x0
        box_h = y1 - y0
        current_size = base_size
        while current_size >= 6:
            test_font = self._get_pil_font(current_size)
            bbox = draw.textbbox((0, 0), text, font=test_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            if tw <= box_w * 1.05 and th <= box_h * 1.1:
                draw.text((x0 + 1, y0), text, fill=fill_color, font=test_font)
                return
            current_size -= 1
        tiny_font = self._get_pil_font(max(6, current_size))
        draw.text((x0 + 1, y0), text, fill=fill_color, font=tiny_font)

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
        margin = 2
        samples = []
        for px, py in [
            (max(0, int(x0) - margin), max(0, int(y0) - margin)),
            (min(w - 1, int(x1) + margin), max(0, int(y0) - margin)),
            (max(0, int(x0) - margin), min(h - 1, int(y1) + margin)),
            (min(w - 1, int(x1) + margin), min(h - 1, int(y1) + margin)),
        ]:
            samples.append(img.getpixel((px, py)))
        return tuple(int(sum(c[i] for c in samples) / len(samples)) for i in range(3))

    @staticmethod
    def _sample_text_color(img, x0, y0, x1, y1):
        """Sample the dominant text (dark) color from the original image region."""
        x0i, y0i, x1i, y1i = int(x0), int(y0), int(x1), int(y1)
        w, h = img.size
        x0i, y0i = max(0, x0i), max(0, y0i)
        x1i, y1i = min(w - 1, x1i), min(h - 1, y1i)
        if x1i <= x0i or y1i <= y0i:
            return "black"
        pixels = []
        step_y = max(1, (y1i - y0i) // 10)
        step_x = max(1, (x1i - x0i) // 10)
        for py in range(y0i, y1i + 1, step_y):
            for px in range(x0i, x1i + 1, step_x):
                pixels.append(img.getpixel((px, py)))
        if not pixels:
            return "black"
        avg_brightness = sum(sum(p[:3]) for p in pixels) / (len(pixels) * 3)
        dark_pixels = [p for p in pixels if sum(p[:3]) / 3 < avg_brightness * 0.7]
        if not dark_pixels or len(dark_pixels) < 3:
            return "black"
        r = int(sum(p[0] for p in dark_pixels) / len(dark_pixels))
        g = int(sum(p[1] for p in dark_pixels) / len(dark_pixels))
        b = int(sum(p[2] for p in dark_pixels) / len(dark_pixels))
        return (r, g, b)

    @staticmethod
    def _get_pil_font(size: int, bold=False, italic=False):
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
        for d in (INPUT_DIR, TRANSLATING_DIR, OUTPUT_DIR, ENGLISH_DIR):
            d.mkdir(parents=True, exist_ok=True)
        self.translator = TranslationEngine()
        self.ocr = OCREngine()
        self.pdf_translator = PDFTranslator(self.translator, self.ocr)

    def run(self, retranslate_file: str = None):
        """Executa o pipeline. Se retranslate_file, retraduz apenas esse livro."""
        write_control({"command": "run", "model": self.translator.model})
        self._recover_translating_dir()

        if retranslate_file:
            result = self._retranslate_single(retranslate_file)
            update_state(status="idle")
            return result

        pdfs = self._get_sorted_pdfs()
        if not pdfs:
            log.info("Nenhum PDF encontrado em %s", INPUT_DIR)
            update_state(status="idle", total_books=0)
            return

        update_state(
            status="running",
            total_books=len(pdfs),
            pipeline_start=datetime.now().isoformat(),
            model=self.translator.model,
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

            ctrl = check_control(self.translator)
            if ctrl == "stop":
                log.info("Pipeline parado pelo usuário.")
                update_state(status="idle")
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
                    update_state(status="idle")
                    return
                completed.append(pdf_path.name)
                update_state(completed_books=completed, book_just_completed=pdf_path.name)
            except Exception:
                log.error("ERRO '%s':\n%s", pdf_path.name, traceback.format_exc())
                self._recover_translating_dir()

        update_state(status="idle")
        log.info("\n" + "=" * 60)
        log.info("PIPELINE CONCLUÍDO")
        log.info("=" * 60)

    def _retranslate_single(self, filename: str):
        """Retraduz um único livro (move de traduzidos/em-inges de volta)."""
        # Procurar o original em em-inges/
        orig = ENGLISH_DIR / filename
        if not orig.exists():
            # Talvez o arquivo esteja em traduzidos com nome PT
            log.error("Arquivo original não encontrado: %s", filename)
            update_state(status="idle")
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
        )

        try:
            self._process_single_book(dest)
        except Exception:
            log.error("ERRO retraduzindo '%s':\n%s", filename, traceback.format_exc())

        update_state(status="idle")

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
        update_state(total_pages=total_pages, current_page=0)

        translated_temp = TRANSLATING_DIR / f"{pdf_path.stem}_PT.pdf"

        def on_progress(current, total):
            update_state(current_page=current, total_pages=total)

        result = self.pdf_translator.translate_pdf(working_path, translated_temp,
                                                   progress_callback=on_progress)
        if result == "stopped":
            # Recuperar arquivo
            dest = INPUT_DIR / pdf_path.name
            if not dest.exists():
                shutil.move(str(working_path), str(dest))
            self._cleanup_translating_dir()
            return "stopped"

        pt_title = self._generate_pt_filename(pdf_path.stem)
        pt_filename = self._sanitize_filename(f"{pt_title} traduzido por Tradutor Universal de PDFs.pdf")
        final_path = OUTPUT_DIR / pt_filename
        shutil.move(str(translated_temp), str(final_path))
        log.info("  -> Traduzido: %s", pt_filename)

        english_path = ENGLISH_DIR / pdf_path.name
        shutil.move(str(working_path), str(english_path))
        log.info("  -> Original -> em-inges/")
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
                    shutil.move(str(f), str(dest))
                    log.info("Recuperado de traduzindo/: %s", f.name)
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
