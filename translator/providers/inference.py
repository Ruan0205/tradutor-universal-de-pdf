from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import Protocol
import urllib.request

from translator.settings import Settings


@dataclass(frozen=True)
class TranslationRequest:
    block_id: str
    text: str
    source_lang: str = "English"
    target_lang: str = "Brazilian Portuguese"
    glossary_terms: tuple[dict[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TranslationResult:
    block_id: str
    translated_text: str
    provider: str
    model: str
    confidence: float
    warnings: list[str]


class InferenceProvider(Protocol):
    name: str
    model: str

    def translate(self, request: TranslationRequest) -> TranslationResult:
        ...

    def health(self) -> dict:
        ...


class MockProvider:
    name = "mock"

    def __init__(self, model: str = "mock-translation"):
        self.model = model

    def translate(self, request: TranslationRequest) -> TranslationResult:
        text = request.text.strip()
        translated = text if not text else f"[pt-BR] {text}"
        return TranslationResult(request.block_id, translated, self.name, self.model, 1.0, [])

    def health(self) -> dict:
        return {"ok": True, "provider": self.name, "model": self.model}


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        temperature: float = 0.2,
        timeout: int = 300,
        retries: int = 3,
        reasoning_mode: str = "off",
        max_output_tokens: int | None = None,
        context_tokens: int | None = None,
        num_gpu: int | None = 0,
        keep_alive: str | None = "24h",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.retries = retries
        self.reasoning_mode = reasoning_mode.strip().lower()
        self.max_output_tokens = max_output_tokens
        self.context_tokens = context_tokens
        self.num_gpu = num_gpu
        self.keep_alive = keep_alive

    def translate(self, request: TranslationRequest) -> TranslationResult:
        system = (
            "You are a professional English to Brazilian Portuguese translator. "
            "Return only valid JSON matching this schema: "
            "{\"block_id\":\"string\",\"translated_text\":\"string\",\"preserved_terms\":[],\"warnings\":[],\"confidence\":0.0}. "
            "Preserve RPG proper nouns and conventional untranslated terms. "
            "Use the glossary exactly when a listed term appears. "
            "Keep tables, numbers, dice notation, stat blocks, labels, and line breaks as stable as possible. "
            "Adapt phrasing when needed so the translated text remains concise enough to fit the original layout."
        )
        user = json.dumps(
            {
                "block_id": request.block_id,
                "source_lang": request.source_lang,
                "target_lang": request.target_lang,
                "glossary_terms": list(request.glossary_terms),
                "text": request.text,
            },
            ensure_ascii=False,
        )
        response = self._chat(system, user)
        parsed = _extract_json(response)
        translated = str(parsed.get("translated_text") or request.text)
        confidence = float(parsed.get("confidence") or 0.75)
        warnings = [str(item) for item in parsed.get("warnings", [])]
        return TranslationResult(request.block_id, translated, self.name, self.model, confidence, warnings)

    def health(self) -> dict:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as response:
                data = json.loads(response.read())
            models = [item.get("name") for item in data.get("models", [])]
            return {"ok": True, "provider": self.name, "model": self.model, "models": models}
        except Exception as exc:
            return {"ok": False, "provider": self.name, "model": self.model, "error": str(exc)}

    def _chat(self, system: str, user: str) -> str:
        options: dict[str, float | int] = {"temperature": self.temperature}
        if self.max_output_tokens:
            options["num_predict"] = self.max_output_tokens
        if self.context_tokens:
            options["num_ctx"] = self.context_tokens
        if self.num_gpu is not None:
            options["num_gpu"] = self.num_gpu
        request_data: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": options,
        }
        if self.keep_alive:
            request_data["keep_alive"] = self.keep_alive
        if self.reasoning_mode in {"off", "false", "0", "no"}:
            request_data["think"] = False
        elif self.reasoning_mode in {"on", "true", "1", "yes"}:
            request_data["think"] = True
        payload = json.dumps(request_data).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/api/chat",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    data = json.loads(response.read())
                return str(data.get("message", {}).get("content", ""))
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(2**attempt)
        raise RuntimeError(f"Ollama request failed: {last_error}")


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, model: str, api_key: str | None = None, *, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def translate(self, request: TranslationRequest) -> TranslationResult:
        glossary_text = ""
        if request.glossary_terms:
            glossary_text = "\nGlossary: " + json.dumps(list(request.glossary_terms), ensure_ascii=False)
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Translate to Brazilian Portuguese and return only the translated text. "
                            "Preserve RPG proper nouns, table structure, numbers, and dice notation."
                        ),
                    },
                    {"role": "user", "content": request.text + glossary_text},
                ],
                "temperature": 0.2,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/v1/chat/completions", data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            data = json.loads(response.read())
        translated = data["choices"][0]["message"]["content"].strip()
        return TranslationResult(request.block_id, translated, self.name, self.model, 0.8, [])

    def health(self) -> dict:
        return {"ok": True, "provider": self.name, "model": self.model}


class LlamaCppProvider(OpenAICompatibleProvider):
    name = "llama.cpp"


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json\n", "", 1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def make_inference_provider(settings: Settings) -> InferenceProvider:
    provider = settings.llm_provider.strip().lower()
    if provider == "ollama":
        return OllamaProvider(
            settings.llm_base_url,
            settings.llm_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
            retries=settings.llm_max_retries,
            reasoning_mode=settings.llm_reasoning_mode,
            max_output_tokens=settings.llm_max_output_tokens,
            context_tokens=settings.llm_context_tokens,
            num_gpu=settings.llm_num_gpu,
            keep_alive=settings.llm_keep_alive,
        )
    if provider in {"llama.cpp", "llamacpp", "llama"}:
        return LlamaCppProvider(settings.llm_base_url, settings.llm_model, timeout=settings.llm_timeout_seconds)
    if provider in {"openai-compatible", "openai"}:
        return OpenAICompatibleProvider(settings.llm_base_url, settings.llm_model, timeout=settings.llm_timeout_seconds)
    return MockProvider(settings.llm_model if provider == "mock" else "mock-translation")
