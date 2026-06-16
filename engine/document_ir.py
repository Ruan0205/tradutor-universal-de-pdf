#!/usr/bin/env python3
"""
Canonical intermediate representation for translated documents.

The goal of Document IR is to give every pipeline stage the same stable
structure instead of letting OCR, PDF extraction, translation, validation, and
rendering each invent their own representation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any, Dict, List, Optional


DOCUMENT_IR_VERSION = "0.1.0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(*parts: object) -> str:
    """Create a deterministic, URL/file-friendly id from human-readable parts."""
    raw = "-".join(str(part) for part in parts if part is not None)
    raw = raw.strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    return raw.strip("-") or "unknown"


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def to_list(self) -> List[float]:
        return [self.x0, self.y0, self.x1, self.y1]

    @classmethod
    def from_any(cls, value: Any) -> "BBox":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(float(value["x0"]), float(value["y0"]), float(value["x1"]), float(value["y1"]))
        if isinstance(value, (list, tuple)) and len(value) == 4:
            return cls(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
        raise ValueError(f"Invalid bbox: {value!r}")


@dataclass
class Provenance:
    source: str
    tool: str
    tool_version: Optional[str] = None
    confidence: Optional[float] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class TextStyle:
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    font_category: Optional[str] = None
    color: Optional[List[int]] = None
    bold: bool = False
    italic: bool = False
    alignment: Optional[str] = None


@dataclass
class IRTextLine:
    line_id: str
    bbox: BBox
    original_text: str = ""
    translated_text: Optional[str] = None
    style: TextStyle = field(default_factory=TextStyle)
    source: str = "digital_text"
    ocr_confidence: Optional[float] = None
    translation_confidence: Optional[float] = None
    provenance: List[Provenance] = field(default_factory=list)


@dataclass
class IRTableCell:
    cell_id: str
    bbox: BBox
    row_index: int
    column_index: int
    row_span: int = 1
    column_span: int = 1
    original_text: str = ""
    translated_text: Optional[str] = None
    confidence: Optional[float] = None
    provenance: List[Provenance] = field(default_factory=list)


@dataclass
class IRTable:
    table_id: str
    bbox: BBox
    cells: List[IRTableCell] = field(default_factory=list)
    source: str = "layout_detection"
    confidence: Optional[float] = None
    provenance: List[Provenance] = field(default_factory=list)


@dataclass
class IRImage:
    image_id: str
    bbox: BBox
    xref: Optional[int] = None
    path: Optional[str] = None
    has_text: bool = False
    translated_path: Optional[str] = None
    confidence: Optional[float] = None
    provenance: List[Provenance] = field(default_factory=list)


@dataclass
class IRBlock:
    block_id: str
    type: str
    bbox: BBox
    lines: List[IRTextLine] = field(default_factory=list)
    original_text: str = ""
    translated_text: Optional[str] = None
    language: Optional[str] = None
    reading_order: Optional[int] = None
    status: str = "new"
    source: str = "digital_text"
    ocr_confidence: Optional[float] = None
    translation_provider: Optional[str] = None
    translation_model: Optional[str] = None
    translation_confidence: Optional[float] = None
    warnings: List[str] = field(default_factory=list)
    provenance: List[Provenance] = field(default_factory=list)


@dataclass
class IRPage:
    page_id: str
    page_number: int
    width: float
    height: float
    rotation: int = 0
    classification: List[str] = field(default_factory=list)
    blocks: List[IRBlock] = field(default_factory=list)
    tables: List[IRTable] = field(default_factory=list)
    images: List[IRImage] = field(default_factory=list)
    headers: List[IRBlock] = field(default_factory=list)
    footers: List[IRBlock] = field(default_factory=list)
    notes: List[IRBlock] = field(default_factory=list)
    provenance: List[Provenance] = field(default_factory=list)


@dataclass
class IRDocument:
    document_id: str
    source_path: str
    checksum: str
    pages: List[IRPage] = field(default_factory=list)
    ir_version: str = DOCUMENT_IR_VERSION
    source_language: Optional[str] = None
    target_language: Optional[str] = "pt-BR"
    title: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    tool_versions: Dict[str, str] = field(default_factory=dict)
    glossary_id: Optional[str] = None
    translation_memory_id: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IRDocument":
        version = data.get("ir_version")
        if version != DOCUMENT_IR_VERSION:
            raise ValueError(f"Unsupported Document IR version: {version!r}")

        pages = []
        for page_data in data.get("pages", []):
            pages.append(_page_from_dict(page_data))
        document = cls(
            document_id=data["document_id"],
            source_path=data["source_path"],
            checksum=data["checksum"],
            pages=pages,
            ir_version=version,
            source_language=data.get("source_language"),
            target_language=data.get("target_language"),
            title=data.get("title"),
            created_at=data.get("created_at", utc_now_iso()),
            updated_at=data.get("updated_at", utc_now_iso()),
            tool_versions=dict(data.get("tool_versions", {})),
            glossary_id=data.get("glossary_id"),
            translation_memory_id=data.get("translation_memory_id"),
            history=list(data.get("history", [])),
        )
        return document

    @classmethod
    def from_json(cls, raw: str) -> "IRDocument":
        return cls.from_dict(json.loads(raw))


def _provenance_from_dict(data: Dict[str, Any]) -> Provenance:
    return Provenance(
        source=data["source"],
        tool=data["tool"],
        tool_version=data.get("tool_version"),
        confidence=data.get("confidence"),
        notes=list(data.get("notes", [])),
    )


def _style_from_dict(data: Dict[str, Any]) -> TextStyle:
    return TextStyle(
        font_name=data.get("font_name"),
        font_size=data.get("font_size"),
        font_category=data.get("font_category"),
        color=data.get("color"),
        bold=bool(data.get("bold", False)),
        italic=bool(data.get("italic", False)),
        alignment=data.get("alignment"),
    )


def _line_from_dict(data: Dict[str, Any]) -> IRTextLine:
    return IRTextLine(
        line_id=data["line_id"],
        bbox=BBox.from_any(data["bbox"]),
        original_text=data.get("original_text", ""),
        translated_text=data.get("translated_text"),
        style=_style_from_dict(data.get("style", {})),
        source=data.get("source", "digital_text"),
        ocr_confidence=data.get("ocr_confidence"),
        translation_confidence=data.get("translation_confidence"),
        provenance=[_provenance_from_dict(p) for p in data.get("provenance", [])],
    )


def _block_from_dict(data: Dict[str, Any]) -> IRBlock:
    return IRBlock(
        block_id=data["block_id"],
        type=data["type"],
        bbox=BBox.from_any(data["bbox"]),
        lines=[_line_from_dict(line) for line in data.get("lines", [])],
        original_text=data.get("original_text", ""),
        translated_text=data.get("translated_text"),
        language=data.get("language"),
        reading_order=data.get("reading_order"),
        status=data.get("status", "new"),
        source=data.get("source", "digital_text"),
        ocr_confidence=data.get("ocr_confidence"),
        translation_provider=data.get("translation_provider"),
        translation_model=data.get("translation_model"),
        translation_confidence=data.get("translation_confidence"),
        warnings=list(data.get("warnings", [])),
        provenance=[_provenance_from_dict(p) for p in data.get("provenance", [])],
    )


def _cell_from_dict(data: Dict[str, Any]) -> IRTableCell:
    return IRTableCell(
        cell_id=data["cell_id"],
        bbox=BBox.from_any(data["bbox"]),
        row_index=int(data["row_index"]),
        column_index=int(data["column_index"]),
        row_span=int(data.get("row_span", 1)),
        column_span=int(data.get("column_span", 1)),
        original_text=data.get("original_text", ""),
        translated_text=data.get("translated_text"),
        confidence=data.get("confidence"),
        provenance=[_provenance_from_dict(p) for p in data.get("provenance", [])],
    )


def _table_from_dict(data: Dict[str, Any]) -> IRTable:
    return IRTable(
        table_id=data["table_id"],
        bbox=BBox.from_any(data["bbox"]),
        cells=[_cell_from_dict(cell) for cell in data.get("cells", [])],
        source=data.get("source", "layout_detection"),
        confidence=data.get("confidence"),
        provenance=[_provenance_from_dict(p) for p in data.get("provenance", [])],
    )


def _image_from_dict(data: Dict[str, Any]) -> IRImage:
    return IRImage(
        image_id=data["image_id"],
        bbox=BBox.from_any(data["bbox"]),
        xref=data.get("xref"),
        path=data.get("path"),
        has_text=bool(data.get("has_text", False)),
        translated_path=data.get("translated_path"),
        confidence=data.get("confidence"),
        provenance=[_provenance_from_dict(p) for p in data.get("provenance", [])],
    )


def _page_from_dict(data: Dict[str, Any]) -> IRPage:
    return IRPage(
        page_id=data["page_id"],
        page_number=int(data["page_number"]),
        width=float(data["width"]),
        height=float(data["height"]),
        rotation=int(data.get("rotation", 0)),
        classification=list(data.get("classification", [])),
        blocks=[_block_from_dict(block) for block in data.get("blocks", [])],
        tables=[_table_from_dict(table) for table in data.get("tables", [])],
        images=[_image_from_dict(image) for image in data.get("images", [])],
        headers=[_block_from_dict(block) for block in data.get("headers", [])],
        footers=[_block_from_dict(block) for block in data.get("footers", [])],
        notes=[_block_from_dict(block) for block in data.get("notes", [])],
        provenance=[_provenance_from_dict(p) for p in data.get("provenance", [])],
    )
