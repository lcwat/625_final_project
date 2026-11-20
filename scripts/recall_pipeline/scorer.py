"""Score one transcript with one API call, with retries and a shared rate limiter."""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from . import config
from .prompt import PROMPT_VERSION, build_system_instruction, build_user_content
from .rubric import Codebook
from .schema import SlideshowScore

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class RateLimiter:
    """Simple token bucket shared across worker threads (requests per minute)."""

    def __init__(self, rpm: int):
        self.interval = 60.0 / max(rpm, 1)
        self._lock = threading.Lock()
        self._next = time.monotonic()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._next > now:
                sleep_for = self._next - now
                self._next += self.interval
            else:
                sleep_for = 0.0
                self._next = now + self.interval
        if sleep_for:
            time.sleep(sleep_for)


class ScoringError(Exception):
    """Raised when a job cannot be scored after all attempts."""


@dataclass
class ScoreOutcome:
    parsed: dict
    raw_json: str
    meta: dict
    attempts: int


def _status_of(exc: Exception) -> int | None:
    for attr in ("code", "status_code", "status"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    return None


def _usage(response) -> dict:
    u = getattr(response, "usage_metadata", None)
    if u is None:
        return {}
    return {
        "prompt_tokens": getattr(u, "prompt_token_count", None),
        "cached_tokens": getattr(u, "cached_content_token_count", None),
        "output_tokens": getattr(u, "candidates_token_count", None),
        "thinking_tokens": getattr(u, "thoughts_token_count", None),
    }


def _validate(parsed: SlideshowScore, codebook: Codebook, participant_id: int) -> list[str]:
    """Semantic checks beyond the JSON schema. Returns a list of problems."""
    problems = []
    got = [e.event_id for e in parsed.events]
    if got != codebook.event_ids:
        problems.append(f"event ids {got} != codebook {codebook.event_ids}")
    if parsed.participant_id != participant_id:
        problems.append(f"participant_id {parsed.participant_id} != {participant_id}")
    for e in parsed.events:
        if e.event_remembered != bool(e.unique_details):
            problems.append(f"event {e.event_id}: event_remembered inconsistent with unique_details")
        for name in ("gist", "objects", "actions", "persons", "locations", "goals", "other_details"):
            cm = getattr(e, name)
            if len(cm.recalled) != len(cm.evidence):
                problems.append(f"event {e.event_id}: {name} recalled/evidence length mismatch")
    return problems


def score_transcript(
    client: genai.Client,
    codebook: Codebook,
    participant_id: int,
    session: int,
    transcript: str,
    cache_name: str | None,
    limiter: RateLimiter | None = None,
    model: str = config.MODEL,
) -> ScoreOutcome:
    """One API call (with retries). Raises ScoringError if it ultimately fails."""
    contents = build_user_content(participant_id, session, codebook.slideshow, transcript)
    cfg = dict(
        temperature=config.TEMPERATURE,
        max_output_tokens=config.MAX_OUTPUT_TOKENS,
        response_mime_type="application/json",
        response_schema=SlideshowScore,
    )
    if config.THINKING_BUDGET is not None:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=int(config.THINKING_BUDGET))
    if cache_name:
        cfg["cached_content"] = cache_name
    else:
        cfg["system_instruction"] = build_system_instruction(codebook)
    gen_config = types.GenerateContentConfig(**cfg)

    delay = config.BACKOFF_BASE_SECONDS
    last_error = "unknown"
    for attempt in range(1, config.MAX_ATTEMPTS + 1):
        if limiter:
            limiter.wait()
        t0 = time.monotonic()
        try:
            response = client.models.generate_content(model=model, contents=contents, config=gen_config)
            latency = time.monotonic() - t0
            raw = response.text or ""
            parsed = SlideshowScore.model_validate_json(raw)
            problems = _validate(parsed, codebook, participant_id)
            if problems:
                raise ValueError("semantic validation: " + "; ".join(problems))
            meta = {"model": model, "prompt_version": PROMPT_VERSION,
                    "used_cache": bool(cache_name), "latency_s": round(latency, 2), **_usage(response)}
            return ScoreOutcome(parsed.model_dump(), raw, meta, attempt)

        except (errors.APIError,) as exc:
            status = _status_of(exc)
            last_error = f"API {status}: {getattr(exc, 'message', exc)}"
            if status is not None and status not in RETRYABLE_STATUS:
                # e.g. 400 bad request, 404 cache expired -> not worth retrying blindly
                if status == 404 and cache_name:
                    log.warning("Cache %s gone (404); retrying inline.", cache_name)
                    cfg.pop("cached_content", None)
                    cfg["system_instruction"] = build_system_instruction(codebook)
                    gen_config = types.GenerateContentConfig(**cfg)
                    cache_name = None
                    continue
                raise ScoringError(last_error) from exc
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = f"bad output: {str(exc)[:500]}"
        except Exception as exc:  # noqa: BLE001 - network hiccups etc.
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < config.MAX_ATTEMPTS:
            sleep_for = min(delay, config.BACKOFF_MAX_SECONDS) * (0.5 + random.random())
            log.info("Attempt %d/%d failed (%s); retrying in %.1fs", attempt, config.MAX_ATTEMPTS,
                     last_error[:120], sleep_for)
            time.sleep(sleep_for)
            delay *= 2

    raise ScoringError(f"gave up after {config.MAX_ATTEMPTS} attempts: {last_error}")
