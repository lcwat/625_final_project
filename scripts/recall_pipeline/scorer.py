"""Score one transcript with one model call, with retries and a shared rate limiter."""
from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass

from pydantic import ValidationError

from . import config
from .prompt import build_user_message, prompt_version
from .providers import CacheGone, ProviderError, Response
from .rubric import Codebook
from .schema import ScoringResult
from .validation import content_flags, structural_problems

log = logging.getLogger(__name__)


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
    result: ScoringResult
    raw_json: str
    meta: dict
    flags: list[str]
    attempts: int


def score_transcript(provider, codebook: Codebook, system_instruction: str, transcript: str,
                     handle: str | None, limiter: RateLimiter | None = None) -> ScoreOutcome:
    """One model call (with retries). Raises ScoringError if it ultimately fails."""
    user_message = build_user_message(codebook.slideshow, transcript)
    codebook_ids = codebook.event_ids
    delay = config.BACKOFF_BASE_SECONDS
    last_error = "unknown"

    for attempt in range(1, config.MAX_ATTEMPTS + 1):
        if limiter:
            limiter.wait()
        t0 = time.monotonic()
        wait_hint = 0.0
        try:
            resp: Response = provider.generate(system_instruction, user_message, handle)
            latency = time.monotonic() - t0
            result = ScoringResult.model_validate_json(resp.text)
            problems = structural_problems(result, codebook_ids)
            if problems:
                raise ValueError("; ".join(problems))
            order = {i: n for n, i in enumerate(codebook_ids)}
            result.events.sort(key=lambda e: order[e.event_id.strip()])
            meta = {"provider": provider.name, "model": provider.model, "prompt_version": prompt_version(),
                    "used_cache": resp.used_cache, "latency_s": round(latency, 2), **resp.usage}
            return ScoreOutcome(result, result.model_dump_json(), meta, content_flags(result, transcript), attempt)

        except CacheGone as exc:
            log.warning("Cache %s gone (%s); continuing with the rubric inline.", handle, exc)
            handle = None
            continue
        except ProviderError as exc:
            raise ScoringError(str(exc)) from exc
        except (ValidationError, ValueError) as exc:
            last_error = f"bad output: {str(exc)[:300]}"
        except Exception as exc:  # noqa: BLE001 - API / network errors
            hint = provider.retry_after(exc)
            last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            if hint is None:
                raise ScoringError(last_error) from exc
            wait_hint = hint

        if attempt < config.MAX_ATTEMPTS:
            sleep_for = max(wait_hint, min(delay, config.BACKOFF_MAX_SECONDS) * (0.5 + random.random()))
            log.info("Attempt %d/%d failed (%s); retrying in %.1fs", attempt, config.MAX_ATTEMPTS,
                     last_error[:120], sleep_for)
            time.sleep(sleep_for)
            delay *= 2

    raise ScoringError(f"gave up after {config.MAX_ATTEMPTS} attempts: {last_error}")
