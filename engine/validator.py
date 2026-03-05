#!/usr/bin/env python3
"""
Validador de Tradução - Compara PDFs originais com traduzidos.
Suporta métodos: structural, char_count, hybrid.
Suporta modos de páginas: all, 50%, 25%, ou número fixo.
Pode ser usado standalone ou pelo continuous_validator.
"""

import json
import random
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

import fitz

ENGINE_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = ENGINE_DIR.parent
BASE_DIR = PROJECT_DIR

CONFIG_FILE = ENGINE_DIR / "config.json"
OUTPUT_DIR = BASE_DIR / "traduzidos"
ENGLISH_DIR = BASE_DIR / "em-inges"
REPORT_FILE = BASE_DIR / "validation_report.log"
TRANSLATION_LOG = BASE_DIR / "translation.log"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# =====================================================================
# BLOCK EXTRACTION
# =====================================================================

def get_text_blocks(page: fitz.Page) -> List[dict]:
    """Extract basic text blocks from a page."""
    d = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    blocks = []
    for b in d.get("blocks", []):
        if b.get("type") != 0:
            continue
        lines = b.get("lines", [])
        if not lines:
            continue
        text = " ".join(
            "".join(s.get("text", "") for s in l.get("spans", []))
            for l in lines
        ).strip()
        if not text:
            continue
        rect = fitz.Rect(b["bbox"])
        sizes = []
        for l in lines:
            for s in l.get("spans", []):
                t = s.get("text", "").strip()
                if t:
                    sizes.append(s.get("size", 10))
        avg_size = sum(sizes) / len(sizes) if sizes else 10.0
        blocks.append({
            "rect": rect,
            "text": text,
            "avg_size": avg_size,
            "char_count": len(text),
        })
    return blocks


def get_detailed_blocks(page: fitz.Page) -> List[dict]:
    """Extract detailed text blocks including font names, colors, and flags."""
    d = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    blocks = []
    for b in d.get("blocks", []):
        if b.get("type") != 0:
            continue
        lines = b.get("lines", [])
        if not lines:
            continue
        text = " ".join(
            "".join(s.get("text", "") for s in l.get("spans", []))
            for l in lines
        ).strip()
        if not text:
            continue
        rect = fitz.Rect(b["bbox"])
        fonts = {}
        colors = {}
        sizes = []
        flags_map = {}
        for l in lines:
            for s in l.get("spans", []):
                t = s.get("text", "").strip()
                if not t:
                    continue
                font = s.get("font", "")
                color = s.get("color", 0)
                size = s.get("size", 10)
                fl = s.get("flags", 0)
                char_count = len(t)
                fonts[font] = fonts.get(font, 0) + char_count
                colors[color] = colors.get(color, 0) + char_count
                flags_map[fl] = flags_map.get(fl, 0) + char_count
                sizes.append(size)
        avg_size = sum(sizes) / len(sizes) if sizes else 10.0
        dominant_font = max(fonts, key=fonts.get) if fonts else ""
        dominant_color = max(colors, key=colors.get) if colors else 0
        dominant_flags = max(flags_map, key=flags_map.get) if flags_map else 0
        blocks.append({
            "rect": rect,
            "text": text,
            "avg_size": avg_size,
            "char_count": len(text),
            "fonts": fonts,
            "colors": colors,
            "dominant_font": dominant_font,
            "dominant_color": dominant_color,
            "dominant_flags": dominant_flags,
        })
    return blocks


# =====================================================================
# HELPERS
# =====================================================================

def classify_font(font_name: str) -> str:
    """Classify font into category for comparison."""
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


def color_int_to_rgb(color_int) -> tuple:
    """Convert integer color to (R, G, B) tuple (0-255 range)."""
    if isinstance(color_int, int):
        r = (color_int >> 16) & 255
        g = (color_int >> 8) & 255
        b = color_int & 255
        return (r, g, b)
    return (0, 0, 0)


def colors_similar(c1, c2, tolerance=30) -> bool:
    """Check if two colors are similar within tolerance."""
    r1, g1, b1 = color_int_to_rgb(c1) if isinstance(c1, int) else c1
    r2, g2, b2 = color_int_to_rgb(c2) if isinstance(c2, int) else c2
    return (abs(r1 - r2) <= tolerance
            and abs(g1 - g2) <= tolerance
            and abs(b1 - b2) <= tolerance)


def is_likely_english(text: str) -> bool:
    """Check if text appears to be English (untranslated)."""
    words = text.lower().split()
    if len(words) < 4:
        return False
    en_words = {"the", "of", "and", "to", "a", "in", "is", "that", "for",
                "it", "with", "as", "was", "on", "are", "be", "this", "have",
                "from", "or", "an", "at", "by", "not", "but", "what", "all",
                "were", "when", "can", "there", "their", "which", "each",
                "she", "he", "do", "has", "his", "her", "its", "they",
                "you", "your", "if", "will", "may", "must", "should"}
    count = sum(1 for w in words if w in en_words)
    return count / len(words) > 0.25


def rects_overlap(r1, r2) -> bool:
    """Check if two rectangles overlap significantly."""
    inter = r1 & r2
    if inter.is_empty:
        return False
    area1 = r1.width * r1.height
    area2 = r2.width * r2.height
    inter_area = inter.width * inter.height
    if area1 > 0 and inter_area / area1 > 0.2:
        return True
    if area2 > 0 and inter_area / area2 > 0.2:
        return True
    return False


# =====================================================================
# TABLE DETECTION
# =====================================================================

def _detect_table_regions(blocks: list) -> list:
    """Detect table-like regions by finding clusters of aligned blocks."""
    if len(blocks) < 4:
        return []

    # Group blocks by similar Y positions (rows)
    rows = {}
    for b in blocks:
        y_key = round(b["rect"].y0 / 5) * 5
        if y_key not in rows:
            rows[y_key] = []
        rows[y_key].append(b)

    table_rows = {k: v for k, v in rows.items() if len(v) >= 3}
    if len(table_rows) < 2:
        return []

    tables = []
    sorted_keys = sorted(table_rows.keys())
    current_table = list(table_rows[sorted_keys[0]])
    prev_y = sorted_keys[0]

    for y_key in sorted_keys[1:]:
        if y_key - prev_y < 30:
            current_table.extend(table_rows[y_key])
        else:
            if len(current_table) >= 6:
                tables.append(current_table)
            current_table = list(table_rows[y_key])
        prev_y = y_key

    if len(current_table) >= 6:
        tables.append(current_table)

    return tables


# =====================================================================
# PAGE VALIDATION
# =====================================================================

def validate_page(orig_page, trans_page, page_num, method="structural") -> dict:
    """Validate a single page using the specified method."""
    if method == "hybrid":
        return _validate_page_hybrid(orig_page, trans_page, page_num)
    elif method == "char_count":
        return _validate_page_char_count(orig_page, trans_page, page_num)
    else:
        return _validate_page_structural(orig_page, trans_page, page_num)


def _validate_page_structural(orig_page, trans_page, page_num) -> dict:
    """Standard structural validation - block counts, sizes, overlaps."""
    report = {"page": page_num, "issues": [], "stats": {}, "pass": True}
    orig_blocks = get_text_blocks(orig_page)
    trans_blocks = get_text_blocks(trans_page)
    report["stats"]["orig_blocks"] = len(orig_blocks)
    report["stats"]["trans_blocks"] = len(trans_blocks)

    # Block count ratio
    if len(orig_blocks) > 0:
        ratio = len(trans_blocks) / len(orig_blocks)
        if ratio < 0.5:
            report["issues"].append(f"BLOCK_COUNT_LOW: ratio={ratio:.2f}")
            report["pass"] = False

    # Untranslated text check
    untranslated_count = 0
    total_translatable = 0
    for tb in trans_blocks:
        words = tb["text"].split()
        if len(words) < 4:
            continue
        total_translatable += 1
        if is_likely_english(tb["text"]):
            untranslated_count += 1

    if total_translatable > 0:
        untrans_ratio = untranslated_count / total_translatable
        report["stats"]["untranslated_ratio"] = round(untrans_ratio, 3)
        if untrans_ratio > 0.3:
            report["issues"].append(f"HIGH_UNTRANSLATED: {untrans_ratio:.0%}")
            report["pass"] = False

    # Font size check
    if orig_blocks and trans_blocks:
        orig_avg = sum(b["avg_size"] for b in orig_blocks) / len(orig_blocks)
        trans_avg = sum(b["avg_size"] for b in trans_blocks) / len(trans_blocks)
        size_ratio = trans_avg / orig_avg if orig_avg > 0 else 1.0
        report["stats"]["font_size_ratio"] = round(size_ratio, 3)
        if size_ratio < 0.6:
            report["issues"].append(f"FONT_TOO_SMALL: ratio={size_ratio:.2f}")
            report["pass"] = False

    # Overlapping blocks
    overlap_count = 0
    for i in range(len(trans_blocks)):
        for j in range(i + 1, len(trans_blocks)):
            if rects_overlap(trans_blocks[i]["rect"], trans_blocks[j]["rect"]):
                overlap_count += 1
    report["stats"]["overlapping_blocks"] = overlap_count
    if overlap_count > 3:
        report["issues"].append(f"OVERLAPPING: {overlap_count} pairs")
        report["pass"] = False

    # Empty page check
    if len(orig_blocks) > 3 and len(trans_blocks) == 0:
        report["issues"].append("EMPTY_PAGE")
        report["pass"] = False

    # Character count ratio
    orig_chars = sum(b["char_count"] for b in orig_blocks)
    trans_chars = sum(b["char_count"] for b in trans_blocks)
    report["stats"]["orig_chars"] = orig_chars
    report["stats"]["trans_chars"] = trans_chars
    if orig_chars > 50:
        char_ratio = trans_chars / orig_chars
        report["stats"]["char_ratio"] = round(char_ratio, 3)
        if char_ratio < 0.3:
            report["issues"].append(f"CHAR_COUNT_LOW: ratio={char_ratio:.2f}")
            report["pass"] = False

    if not report["issues"]:
        report["issues"].append("OK")
    return report


def _validate_page_char_count(orig_page, trans_page, page_num) -> dict:
    """Simple character count validation."""
    report = {"page": page_num, "issues": [], "stats": {}, "pass": True}
    orig_blocks = get_text_blocks(orig_page)
    trans_blocks = get_text_blocks(trans_page)

    orig_chars = sum(b["char_count"] for b in orig_blocks)
    trans_chars = sum(b["char_count"] for b in trans_blocks)
    report["stats"]["orig_chars"] = orig_chars
    report["stats"]["trans_chars"] = trans_chars

    if orig_chars > 30:
        char_ratio = trans_chars / orig_chars
        report["stats"]["char_ratio"] = round(char_ratio, 3)
        if char_ratio < 0.3 or char_ratio > 3.0:
            report["issues"].append(f"CHAR_RATIO_BAD: {char_ratio:.2f}")
            report["pass"] = False

    if len(orig_blocks) > 3 and len(trans_blocks) == 0:
        report["issues"].append("EMPTY_PAGE")
        report["pass"] = False

    if not report["issues"]:
        report["issues"].append("OK")
    return report


def _validate_page_hybrid(orig_page, trans_page, page_num) -> dict:
    """Enhanced hybrid validation: structural + font + color + table checks."""
    report = {"page": page_num, "issues": [], "stats": {}, "pass": True}

    orig_blocks = get_detailed_blocks(orig_page)
    trans_blocks = get_detailed_blocks(trans_page)
    report["stats"]["orig_blocks"] = len(orig_blocks)
    report["stats"]["trans_blocks"] = len(trans_blocks)

    # === Block count check ===
    if len(orig_blocks) > 0:
        ratio = len(trans_blocks) / len(orig_blocks)
        report["stats"]["block_ratio"] = round(ratio, 3)
        if ratio < 0.5:
            report["issues"].append(f"BLOCK_COUNT_LOW: ratio={ratio:.2f}")
            report["pass"] = False

    # === Untranslated text check ===
    untranslated_count = 0
    total_translatable = 0
    for tb in trans_blocks:
        words = tb["text"].split()
        if len(words) < 4:
            continue
        total_translatable += 1
        if is_likely_english(tb["text"]):
            untranslated_count += 1
    if total_translatable > 0:
        untrans_ratio = untranslated_count / total_translatable
        report["stats"]["untranslated_ratio"] = round(untrans_ratio, 3)
        if untrans_ratio > 0.3:
            report["issues"].append(f"HIGH_UNTRANSLATED: {untrans_ratio:.0%}")
            report["pass"] = False

    # === Font matching check ===
    font_mismatches = 0
    color_mismatches = 0
    matched_count = 0
    for ob in orig_blocks:
        best_match = None
        for tb in trans_blocks:
            if rects_overlap(ob["rect"], tb["rect"]):
                best_match = tb
                break
        if not best_match:
            continue
        matched_count += 1
        # Font category
        orig_cat = classify_font(ob["dominant_font"])
        trans_cat = classify_font(best_match["dominant_font"])
        if orig_cat != trans_cat and orig_cat != "symbol":
            font_mismatches += 1
        # Color
        if not colors_similar(ob["dominant_color"], best_match["dominant_color"]):
            color_mismatches += 1

    report["stats"]["font_mismatches"] = font_mismatches
    report["stats"]["color_mismatches"] = color_mismatches
    report["stats"]["matched_blocks"] = matched_count
    if matched_count > 0 and font_mismatches / matched_count > 0.3:
        report["issues"].append(
            f"FONT_CATEGORY_MISMATCH: {font_mismatches}/{matched_count} blocks"
        )
        report["pass"] = False
    if matched_count > 0 and color_mismatches / matched_count > 0.3:
        report["issues"].append(
            f"COLOR_MISMATCH: {color_mismatches}/{matched_count} blocks"
        )
        report["pass"] = False

    # === Font size check ===
    if orig_blocks and trans_blocks:
        orig_avg = sum(b["avg_size"] for b in orig_blocks) / len(orig_blocks)
        trans_avg = sum(b["avg_size"] for b in trans_blocks) / len(trans_blocks)
        size_ratio = trans_avg / orig_avg if orig_avg > 0 else 1.0
        report["stats"]["font_size_ratio"] = round(size_ratio, 3)
        if size_ratio < 0.6:
            report["issues"].append(f"FONT_TOO_SMALL: ratio={size_ratio:.2f}")
            report["pass"] = False

    # === Overlapping blocks ===
    overlap_count = 0
    for i in range(len(trans_blocks)):
        for j in range(i + 1, len(trans_blocks)):
            if rects_overlap(trans_blocks[i]["rect"], trans_blocks[j]["rect"]):
                overlap_count += 1
    report["stats"]["overlapping_blocks"] = overlap_count
    if overlap_count > 3:
        report["issues"].append(f"OVERLAPPING: {overlap_count} pairs")
        report["pass"] = False

    # === Table structure check ===
    orig_tables = _detect_table_regions(orig_blocks)
    trans_tables = _detect_table_regions(trans_blocks)
    report["stats"]["orig_tables"] = len(orig_tables)
    report["stats"]["trans_tables"] = len(trans_tables)
    if orig_tables and not trans_tables:
        report["issues"].append("TABLE_MISSING: Original had tables, translation doesn't")
        report["pass"] = False
    elif orig_tables and trans_tables:
        for ot in orig_tables:
            ot_count = len(ot)
            best_tt = None
            best_overlap = 0
            for tt in trans_tables:
                overlap = sum(
                    1 for ob in ot for tb in tt
                    if rects_overlap(ob["rect"], tb["rect"])
                )
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_tt = tt
            if best_tt:
                tt_count = len(best_tt)
                if ot_count > 0 and tt_count / ot_count < 0.5:
                    report["issues"].append(
                        f"TABLE_CONTENT_LOW: orig={ot_count} trans={tt_count} cells"
                    )
                    report["pass"] = False

    # === Character count ratio ===
    orig_chars = sum(b["char_count"] for b in orig_blocks)
    trans_chars = sum(b["char_count"] for b in trans_blocks)
    report["stats"]["orig_chars"] = orig_chars
    report["stats"]["trans_chars"] = trans_chars
    if orig_chars > 50:
        char_ratio = trans_chars / orig_chars
        report["stats"]["char_ratio"] = round(char_ratio, 3)
        if char_ratio < 0.3:
            report["issues"].append(f"CHAR_COUNT_LOW: ratio={char_ratio:.2f}")
            report["pass"] = False

    # === Empty page check ===
    if len(orig_blocks) > 3 and len(trans_blocks) == 0:
        report["issues"].append("EMPTY_PAGE")
        report["pass"] = False

    if not report["issues"]:
        report["issues"].append("OK")
    return report


# =====================================================================
# BOOK VALIDATION
# =====================================================================

def _resolve_page_count(mode, total_pages: int) -> int:
    """Convert validation mode to actual page count."""
    if isinstance(mode, int):
        return min(mode, total_pages)
    mode_str = str(mode).strip().lower()
    if mode_str == "all":
        return total_pages
    if mode_str == "50%":
        return max(1, total_pages // 2)
    if mode_str == "25%":
        return max(1, total_pages // 4)
    try:
        return min(int(mode_str), total_pages)
    except (ValueError, TypeError):
        return max(1, total_pages // 4)


def validate_book(orig_path: str, trans_path: str, mode="25%",
                  method: str = "structural",
                  fidelity_threshold: int = 90) -> dict:
    """
    Validate a translated book against the original.

    Args:
        orig_path: Path to original PDF
        trans_path: Path to translated PDF
        mode: "all", "50%", "25%", or integer number of pages
        method: "structural", "char_count", or "hybrid"
        fidelity_threshold: Pass threshold percentage (0-100)
    """
    orig_doc = fitz.open(orig_path)
    trans_doc = fitz.open(trans_path)

    result = {
        "original": Path(orig_path).name,
        "translated": Path(trans_path).name,
        "orig_pages": orig_doc.page_count,
        "trans_pages": trans_doc.page_count,
        "method": method,
        "mode": str(mode),
        "fidelity_threshold": fidelity_threshold,
        "page_reports": [],
        "overall_pass": True,
        "summary": "",
    }

    if orig_doc.page_count != trans_doc.page_count:
        result["overall_pass"] = False
        result["pass_rate"] = 0.0
        result["summary"] = (
            f"PAGE_COUNT_MISMATCH: {orig_doc.page_count} vs {trans_doc.page_count}"
        )
        orig_doc.close()
        trans_doc.close()
        return result

    total = orig_doc.page_count
    num_pages = _resolve_page_count(mode, total)

    if num_pages >= total:
        pages = list(range(total))
    else:
        pages = sorted(random.sample(range(total), num_pages))

    failed_pages = 0
    for page_idx in pages:
        report = validate_page(orig_doc[page_idx], trans_doc[page_idx],
                               page_idx + 1, method=method)
        result["page_reports"].append(report)
        if not report["pass"]:
            failed_pages += 1

    total_checked = len(pages)
    pass_rate = ((total_checked - failed_pages) / total_checked
                 if total_checked else 1.0)
    result["pages_checked"] = total_checked
    result["pages_failed"] = failed_pages
    result["pass_rate"] = round(pass_rate, 3)

    threshold_decimal = fidelity_threshold / 100.0
    result["overall_pass"] = pass_rate >= threshold_decimal
    result["summary"] = (
        f"{'PASS' if result['overall_pass'] else 'FAIL'}: "
        f"rate={pass_rate:.0%} (threshold={fidelity_threshold}%)"
    )

    orig_doc.close()
    trans_doc.close()
    return result


# =====================================================================
# MAPPING & LOG UTILITIES
# =====================================================================

def match_original_to_translated():
    mapping = {}
    if not TRANSLATION_LOG.exists():
        return mapping
    current_original = None
    with open(TRANSLATION_LOG, "r", encoding="utf-8") as f:
        for line in f:
            m = re.search(r"Processando:\s+(.+\.pdf)", line)
            if m:
                current_original = m.group(1).strip()
            m = re.search(r"->\s+Traduzido:\s+(.+\.pdf)", line)
            if m and current_original:
                mapping[m.group(1).strip()] = current_original
                current_original = None
    return mapping


def get_validated_set() -> set:
    validated = set()
    if REPORT_FILE.exists():
        with open(REPORT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VALIDATED:"):
                    validated.add(line.split("VALIDATED:", 1)[1].strip())
    return validated


def log_result(text: str):
    print(text)
    with open(REPORT_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")


# =====================================================================
# CONTINUOUS VALIDATOR
# =====================================================================

def continuous_validate():
    """Monitor and validate new translations."""
    print("=" * 60)
    print("CONTINUOUS VALIDATION MONITOR")
    print(f"Watching: {OUTPUT_DIR}")
    print("=" * 60)

    validated = get_validated_set()
    total_passed = 0
    total_failed = 0

    while True:
        cfg = load_config()
        val_mode = cfg.get("validation_mode", "25%")
        val_method = cfg.get("validation_method", "structural")
        fidelity = cfg.get("fidelity_threshold", 90)

        mapping = match_original_to_translated()
        new_books = [f for f in OUTPUT_DIR.glob("*.pdf")
                     if f.name not in validated]

        if not new_books:
            time.sleep(30)
            continue

        for trans_file in new_books:
            orig_name = mapping.get(trans_file.name)
            if not orig_name:
                time.sleep(10)
                continue

            orig_path = ENGLISH_DIR / orig_name
            if not orig_path.exists():
                validated.add(trans_file.name)
                continue

            log_result(f"\n{'='*60}")
            log_result(f"VALIDATING: {trans_file.name}")
            log_result(f"ORIGINAL: {orig_name}")
            log_result(
                f"METHOD: {val_method} | MODE: {val_mode} | "
                f"THRESHOLD: {fidelity}%"
            )

            try:
                result = validate_book(
                    str(orig_path), str(trans_file),
                    mode=val_mode, method=val_method,
                    fidelity_threshold=fidelity,
                )
                rate_pct = round(result.get("pass_rate", 0) * 100)
                status = "PASS" if result["overall_pass"] else "FAIL"

                if result["overall_pass"]:
                    total_passed += 1
                else:
                    total_failed += 1

                log_result(f"RESULT: {status} (rate={rate_pct}%)")
                log_result(f"VALIDATED: {trans_file.name}")
                validated.add(trans_file.name)

                if result.get("pass_rate", 1.0) < 0.5:
                    log_result(
                        f"\n*** CRITICAL FAILURE: {trans_file.name} ***"
                    )
                    return False

            except Exception as e:
                log_result(f"ERROR validating {trans_file.name}: {e}")
                validated.add(trans_file.name)

            log_result(
                f"PROGRESS: {len(validated)} validated, "
                f"{total_passed} passed, {total_failed} failed"
            )

        time.sleep(30)


# =====================================================================
# MAIN
# =====================================================================

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        orig = sys.argv[1]
        trans = sys.argv[2]
        mode = sys.argv[3] if len(sys.argv) > 3 else "25%"
        method = sys.argv[4] if len(sys.argv) > 4 else "structural"
        threshold = int(sys.argv[5]) if len(sys.argv) > 5 else 90
        result = validate_book(orig, trans, mode=mode, method=method,
                               fidelity_threshold=threshold)
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if result["overall_pass"] else 1)
    else:
        continuous_validate()
