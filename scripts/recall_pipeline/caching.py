"""Gemini context caches: the scoring rules + one slideshow's codebook are
uploaded once and referenced by handle on every subsequent call.

If a cache cannot be created (content below the model's minimum cacheable
size, model without cache support, etc.) the pipeline falls back to sending
the same system instruction inline, so results are identical either way.
"""
from __future__ import annotations

import logging

from google import genai
from google.genai import types

from . import config
from .prompt import build_system_instruction
from .rubric import Codebook

log = logging.getLogger(__name__)


def create_cache(client: genai.Client, codebook: Codebook, run_tag: str,
                 model: str = config.MODEL) -> str | None:
    """Create a cache for one slideshow. Returns the cache name, or None on failure."""
    system = build_system_instruction(codebook)
    display = f"{config.CACHE_DISPLAY_PREFIX}-{run_tag}-{codebook.slideshow.lower()}"
    try:
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                display_name=display,
                system_instruction=system,
                ttl=f"{config.CACHE_TTL_SECONDS}s",
            ),
        )
    except Exception as exc:  # noqa: BLE001 - we want to fall back on anything
        log.warning("Cache creation failed for %s (%s); falling back to inline prompt.",
                    codebook.slideshow, exc)
        return None
    tokens = getattr(getattr(cache, "usage_metadata", None), "total_token_count", None)
    log.info("Created cache %s for %s (%s tokens)", cache.name, codebook.slideshow, tokens)
    return cache.name


def delete_cache(client: genai.Client, cache_name: str) -> bool:
    try:
        client.caches.delete(name=cache_name)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not delete cache %s: %s", cache_name, exc)
        return False


def cache_exists(client: genai.Client, cache_name: str) -> bool:
    try:
        client.caches.get(name=cache_name)
        return True
    except Exception:  # noqa: BLE001
        return False
