"""Model providers behind one small interface.

    provider.prepare(system_instruction, slideshow, run_tag) -> handle | None
    provider.generate(system_instruction, user_message, handle)  -> Response
    provider.retry_after(exc) -> seconds | None   (None = not retryable)
    provider.cleanup(handle)

GeminiProvider   Google AI Studio via google-genai. `prepare` uploads the rules +
                 codebook once as a context cache; `generate` references it.
AzureProvider    Azure OpenAI via the openai SDK. Prompt caching is automatic for
                 repeated prefixes, so `prepare` returns None; usage reports how
                 many prompt tokens were served from cache.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field

from . import config
from .schema import ScoringResult

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass
class Response:
    text: str
    usage: dict = field(default_factory=dict)   # prompt_tokens, cached_tokens, output_tokens, thinking_tokens
    used_cache: bool = False


class ProviderError(Exception):
    """A provider failure that should not be retried."""


class CacheGone(Exception):
    """The cache handle no longer exists; the caller should fall back to inline."""


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str = config.GEMINI_MODEL, use_cache: bool = True):
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise SystemExit("GEMINI_API_KEY is not set. Put it in a .env file at the repo root.")
        from google import genai  # imported here so the azure path does not need it
        self._genai = genai
        self._key = key
        self.model = model
        self.use_cache = use_cache
        self._local = threading.local()

    def _client(self):
        c = getattr(self._local, "client", None)
        if c is None:  # one client per worker thread
            c = self._genai.Client(api_key=self._key)
            self._local.client = c
        return c

    # -- caching ---------------------------------------------------------
    def prepare(self, system_instruction: str, slideshow: str, run_tag: str) -> str | None:
        if not self.use_cache:
            return None
        from google.genai import types
        try:
            cache = self._client().caches.create(
                model=self.model,
                config=types.CreateCachedContentConfig(
                    display_name=f"{config.GEMINI_CACHE_DISPLAY_PREFIX}-{run_tag}-{slideshow.lower()}",
                    system_instruction=system_instruction,
                    ttl=f"{config.GEMINI_CACHE_TTL_SECONDS}s",
                ),
            )
        except Exception as exc:  # noqa: BLE001 - fall back on anything (too small, unsupported...)
            log.warning("Gemini cache creation failed for %s (%s); sending the rubric inline.", slideshow, exc)
            return None
        tokens = getattr(getattr(cache, "usage_metadata", None), "total_token_count", None)
        log.info("Created Gemini cache %s for %s (%s tokens)", cache.name, slideshow, tokens)
        return cache.name

    def handle_exists(self, handle: str) -> bool:
        try:
            self._client().caches.get(name=handle)
            return True
        except Exception:  # noqa: BLE001
            return False

    def cleanup(self, handle: str | None) -> None:
        if not handle:
            return
        try:
            self._client().caches.delete(name=handle)
            log.info("Deleted Gemini cache %s", handle)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not delete Gemini cache %s: %s", handle, exc)

    # -- generation ------------------------------------------------------
    def generate(self, system_instruction: str, user_message: str, handle: str | None) -> Response:
        from google.genai import errors, types
        cfg = dict(
            temperature=config.GEMINI_TEMPERATURE,
            max_output_tokens=config.MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            response_schema=ScoringResult,
        )
        if config.GEMINI_THINKING_BUDGET is not None:
            cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=int(config.GEMINI_THINKING_BUDGET))
        if handle:
            cfg["cached_content"] = handle
        else:
            cfg["system_instruction"] = system_instruction
        try:
            r = self._client().models.generate_content(
                model=self.model, contents=user_message, config=types.GenerateContentConfig(**cfg))
        except errors.APIError as exc:
            if handle and getattr(exc, "code", None) == 404:
                raise CacheGone(str(exc)) from exc
            raise
        u = getattr(r, "usage_metadata", None)
        usage = {} if u is None else {
            "prompt_tokens": getattr(u, "prompt_token_count", None),
            "cached_tokens": getattr(u, "cached_content_token_count", None),
            "output_tokens": getattr(u, "candidates_token_count", None),
            "thinking_tokens": getattr(u, "thoughts_token_count", None),
        }
        return Response(r.text or "", usage, used_cache=bool(handle))

    def retry_after(self, exc: Exception) -> float | None:
        from google.genai import errors
        if isinstance(exc, errors.APIError):
            return 0.0 if getattr(exc, "code", None) in RETRYABLE_STATUS else None
        return 0.0  # connection hiccups and the like


# ---------------------------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------------------------


class AzureProvider:
    name = "azure"

    def __init__(self, model: str = config.AZURE_OPENAI_DEPLOYMENT, use_cache: bool = True):
        key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = config.AZURE_OPENAI_ENDPOINT
        if not key or not endpoint:
            raise SystemExit("AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT must be set in the repo-root .env.")
        self.model = model  # the deployment name
        self.use_cache = use_cache  # informational: Azure caches prefixes automatically
        endpoint = endpoint.strip().rstrip("/")
        if "/openai/v1" in endpoint:
            # New Foundry portal form: https://<resource>.services.ai.azure.com/openai/v1/responses
            # The v1 API takes no api-version; use the plain OpenAI client with a base_url.
            from openai import OpenAI
            base_url = endpoint.split("/openai/v1")[0] + "/openai/v1/"
            self._client = OpenAI(api_key=key, base_url=base_url, max_retries=0)
            self.endpoint_style = "v1"
        else:
            # Classic form: https://<resource>.openai.azure.com (+ api-version query parameter)
            from openai import AzureOpenAI
            self._client = AzureOpenAI(api_key=key, azure_endpoint=endpoint,
                                       api_version=config.AZURE_OPENAI_API_VERSION, max_retries=0)
            self.endpoint_style = "classic"
        log.info("Azure OpenAI client: %s endpoint, deployment %s", self.endpoint_style, model)

    def prepare(self, system_instruction: str, slideshow: str, run_tag: str) -> None:
        return None  # automatic prefix caching; nothing to create

    def handle_exists(self, handle: str) -> bool:
        return False

    def cleanup(self, handle) -> None:
        return None

    def generate(self, system_instruction: str, user_message: str, handle=None) -> Response:
        kwargs = dict(
            model=self.model,
            messages=[{"role": "system", "content": system_instruction},
                      {"role": "user", "content": user_message}],
            response_format=ScoringResult,
            max_completion_tokens=config.MAX_OUTPUT_TOKENS,
        )
        if config.AZURE_OPENAI_REASONING_EFFORT:
            kwargs["reasoning_effort"] = config.AZURE_OPENAI_REASONING_EFFORT
        if config.AZURE_OPENAI_TEMPERATURE is not None:
            kwargs["temperature"] = float(config.AZURE_OPENAI_TEMPERATURE)
        completion = self._client.chat.completions.parse(**kwargs)
        choice = completion.choices[0]
        if getattr(choice.message, "refusal", None):
            raise ProviderError(f"model refused: {choice.message.refusal}")
        if choice.finish_reason == "length":
            raise ValueError("response truncated (finish_reason=length); raise RECALL_MAX_OUTPUT_TOKENS")
        u = completion.usage
        pd_ = getattr(u, "prompt_tokens_details", None)
        cd_ = getattr(u, "completion_tokens_details", None)
        cached = getattr(pd_, "cached_tokens", None) if pd_ else None
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", None),
            "cached_tokens": cached,
            "output_tokens": getattr(u, "completion_tokens", None),
            "thinking_tokens": getattr(cd_, "reasoning_tokens", None) if cd_ else None,
        }
        return Response(choice.message.content or "", usage, used_cache=bool(cached))

    def retry_after(self, exc: Exception) -> float | None:
        import openai
        if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
            return 0.0
        if isinstance(exc, openai.APIStatusError):
            if exc.status_code not in RETRYABLE_STATUS:
                return None
            hdr = exc.response.headers.get("retry-after") if exc.response is not None else None
            try:
                return float(hdr) if hdr else 0.0
            except ValueError:
                return 0.0
        return 0.0


def make_provider(name: str = config.PROVIDER, model: str | None = None, use_cache: bool = True):
    name = name.lower()
    if name == "gemini":
        return GeminiProvider(model or config.GEMINI_MODEL, use_cache)
    if name == "azure":
        return AzureProvider(model or config.AZURE_OPENAI_DEPLOYMENT, use_cache)
    raise SystemExit(f"unknown provider {name!r}; use 'gemini' or 'azure'")
