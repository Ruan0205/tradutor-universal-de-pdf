from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image


class GoogleTranslateImagesError(RuntimeError):
    """Raised when the Google Translate Images browser flow cannot complete."""


@dataclass(frozen=True)
class ImageTranslationResult:
    image_bytes: bytes
    provider: str
    source_lang: str
    target_lang: str
    from_cache: bool = False


class GoogleTranslateImagesProvider:
    """Best-effort automation for the Google Translate Images web flow.

    Google does not expose a stable public "Translate Images" API equivalent to
    the web UI. This provider uses Playwright with a real browser, caches
    successful image translations, and raises explicit errors when the UI cannot
    be automated instead of pretending that a local OCR fallback was Google.
    """

    name = "google_translate_images"

    def __init__(
        self,
        *,
        enabled: bool = True,
        cache_dir: Optional[Path | str] = None,
        headless: bool = True,
        timeout_ms: int = 120_000,
        source_lang: str = "en",
        target_lang: str = "pt",
    ) -> None:
        self.enabled = enabled
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.source_lang = source_lang
        self.target_lang = target_lang
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def health(self) -> dict:
        if not self.enabled:
            return {"ok": False, "provider": self.name, "error": "disabled"}
        try:
            import playwright.sync_api  # noqa: F401
        except Exception as exc:
            return {"ok": False, "provider": self.name, "error": f"playwright unavailable: {exc}"}
        return {"ok": True, "provider": self.name}

    def translate_pil_image(
        self,
        image: Image.Image,
        *,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
    ) -> Optional[Image.Image]:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        result = self.translate_image_bytes(
            buffer.getvalue(),
            source_lang=source_lang,
            target_lang=target_lang,
        )
        if result is None:
            return None
        return Image.open(io.BytesIO(result.image_bytes)).convert("RGB")

    def translate_image_bytes(
        self,
        image_bytes: bytes,
        *,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
    ) -> Optional[ImageTranslationResult]:
        if not self.enabled:
            return None
        src = self._normalize_lang(source_lang or self.source_lang)
        dst = self._normalize_lang(target_lang or self.target_lang)
        cache_path = self._cache_path(image_bytes, src, dst)
        if cache_path and cache_path.exists():
            return ImageTranslationResult(
                image_bytes=cache_path.read_bytes(),
                provider=self.name,
                source_lang=src,
                target_lang=dst,
                from_cache=True,
            )

        translated = self._translate_with_browser(image_bytes, src, dst)
        if cache_path:
            cache_path.write_bytes(translated)
        return ImageTranslationResult(
            image_bytes=translated,
            provider=self.name,
            source_lang=src,
            target_lang=dst,
            from_cache=False,
        )

    def _cache_path(self, image_bytes: bytes, source_lang: str, target_lang: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        digest = hashlib.sha256()
        digest.update(b"google-translate-images-v1")
        digest.update(source_lang.encode("utf-8"))
        digest.update(b"\0")
        digest.update(target_lang.encode("utf-8"))
        digest.update(b"\0")
        digest.update(image_bytes)
        return self.cache_dir / f"{digest.hexdigest()}.png"

    def _translate_with_browser(self, image_bytes: bytes, source_lang: str, target_lang: str) -> bytes:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise GoogleTranslateImagesError(
                "Playwright/Chromium is not installed; run `python -m playwright install chromium`."
            ) from exc

        with tempfile.TemporaryDirectory(prefix="google_translate_images_") as tmp:
            input_path = Path(tmp) / "input.png"
            input_path.write_bytes(image_bytes)
            url = f"https://translate.google.com/?sl={source_lang}&tl={target_lang}&op=images"

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                try:
                    page = browser.new_page(viewport={"width": 1400, "height": 1000})
                    page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                    file_input = page.locator("input[type='file']").first
                    file_input.wait_for(state="attached", timeout=self.timeout_ms)
                    file_input.set_input_files(str(input_path))
                    return self._capture_translated_image(page, PlaywrightTimeoutError)
                finally:
                    browser.close()

    def _capture_translated_image(self, page, timeout_error) -> bytes:
        page.wait_for_timeout(2_500)
        deadline = max(5_000, self.timeout_ms)
        selectors = [
            "canvas",
            "img[src^='blob:']",
            "img[src^='data:']",
            "[role='main'] img",
            "main img",
        ]

        last_error: Optional[Exception] = None
        for selector in selectors:
            try:
                page.wait_for_selector(selector, timeout=min(15_000, deadline))
                candidates = page.locator(selector)
                count = candidates.count()
            except Exception as exc:
                last_error = exc
                continue

            best = None
            best_area = 0.0
            for idx in range(count):
                element = candidates.nth(idx)
                try:
                    box = element.bounding_box()
                except Exception:
                    continue
                if not box:
                    continue
                area = float(box.get("width", 0)) * float(box.get("height", 0))
                if area > best_area and box.get("width", 0) >= 64 and box.get("height", 0) >= 64:
                    best = element
                    best_area = area
            if best is None:
                continue
            try:
                return best.screenshot(type="png", timeout=self.timeout_ms)
            except timeout_error as exc:
                last_error = exc
                continue

        raise GoogleTranslateImagesError(
            "Could not capture translated image from Google Translate Images UI."
        ) from last_error

    @staticmethod
    def _normalize_lang(lang: str) -> str:
        raw = (lang or "").strip().lower()
        mapping = {
            "english": "en",
            "ingles": "en",
            "inglês": "en",
            "portuguese": "pt",
            "portugues": "pt",
            "português": "pt",
            "portugues brasileiro": "pt",
            "português brasileiro": "pt",
            "brazilian portuguese": "pt",
            "pt-br": "pt",
        }
        return mapping.get(raw, raw or "auto")
