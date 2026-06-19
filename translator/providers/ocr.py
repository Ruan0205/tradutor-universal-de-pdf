from __future__ import annotations

from dataclasses import dataclass
import shutil
from typing import Protocol


@dataclass(frozen=True)
class OCRResult:
    text: str
    bbox: tuple[float, float, float, float]
    confidence: float
    provider: str


class OCRProvider(Protocol):
    name: str

    def health(self) -> dict:
        ...


class RapidOCRProvider:
    name = "rapidocr"

    def health(self) -> dict:
        try:
            import rapidocr_onnxruntime  # noqa: F401
            return {"ok": True, "provider": self.name}
        except Exception as exc:
            return {"ok": False, "provider": self.name, "error": str(exc)}


class TesseractProvider:
    name = "tesseract"

    def health(self) -> dict:
        exe = shutil.which("tesseract")
        return {"ok": bool(exe), "provider": self.name, "executable": exe}


class OCRmyPDFProvider:
    name = "ocrmypdf"

    def health(self) -> dict:
        exe = shutil.which("ocrmypdf")
        return {"ok": bool(exe), "provider": self.name, "executable": exe}
