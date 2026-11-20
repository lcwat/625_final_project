"""Parallel execution: build caches once, then fan jobs out over a thread pool."""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai

from . import caching, config
from .db import Store
from .rubric import Codebook, load_all_codebooks
from .scorer import RateLimiter, ScoringError, score_transcript

log = logging.getLogger(__name__)


def make_client() -> genai.Client:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set. Put it in a .env file at the repo root.")
    return genai.Client(api_key=key)


class _ClientPool:
    """One genai.Client per worker thread (httpx clients are not meant to be shared
    across threads under heavy concurrency)."""

    def __init__(self):
        self._local = threading.local()

    def get(self) -> genai.Client:
        c = getattr(self._local, "client", None)
        if c is None:
            c = make_client()
            self._local.client = c
        return c


def ensure_caches(client: genai.Client, store: Store, codebooks: dict[str, Codebook],
                  run_tag: str, use_cache: bool = True, model: str = config.MODEL) -> dict[str, str | None]:
    """Return {slideshow: cache_name or None}. Reuses caches recorded for this run
    if they still exist server-side; creates the rest."""
    names: dict[str, str | None] = {s: None for s in codebooks}
    if not use_cache:
        return names
    existing = store.get_caches(run_tag)
    for slideshow, cb in codebooks.items():
        name = existing.get(slideshow)
        if name and caching.cache_exists(client, name):
            names[slideshow] = name
            log.info("Reusing cache %s for %s", name, slideshow)
            continue
        name = caching.create_cache(client, cb, run_tag, model=model)
        names[slideshow] = name
        if name:
            store.save_cache(run_tag, slideshow, name, model)
    return names


def cleanup_caches(client: genai.Client, store: Store, run_tag: str) -> None:
    for slideshow, name in store.get_caches(run_tag).items():
        if caching.delete_cache(client, name):
            log.info("Deleted cache %s (%s)", name, slideshow)
    store.delete_cache_rows(run_tag)


def run(store: Store, run_tag: str = config.RUN_TAG, workers: int = config.WORKERS,
        rpm: int = config.REQUESTS_PER_MINUTE, use_cache: bool = True, keep_caches: bool = False,
        retry_failed: bool = True, limit: int | None = None, model: str = config.MODEL) -> dict:
    """Score every pending job for `run_tag`. Returns a summary dict."""
    codebooks = load_all_codebooks()
    jobs = store.pending_jobs(run_tag, include_failed=retry_failed)
    if limit:
        jobs = jobs[:limit]
    if not jobs:
        log.info("No pending jobs for run_tag=%s", run_tag)
        return {"done": 0, "failed": 0, "elapsed_s": 0.0}

    client = make_client()
    caches = ensure_caches(client, store, codebooks, run_tag, use_cache=use_cache, model=model)
    limiter = RateLimiter(rpm)
    pool = _ClientPool()
    done = failed = 0
    t0 = time.monotonic()

    def work(job):
        cb = codebooks[job["slideshow"]]
        outcome = score_transcript(
            pool.get(), cb, job["participant_id"], job["session"], job["transcript"],
            caches.get(job["slideshow"]), limiter, model=model,
        )
        store.save_result(run_tag, job, outcome.parsed, outcome.raw_json, outcome.meta,
                          job["attempts"] + outcome.attempts)
        return outcome

    log.info("Scoring %d jobs with %d workers at <=%d rpm (model=%s, cache=%s)",
             len(jobs), workers, rpm, model, any(caches.values()))
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(work, job): job for job in jobs}
            for fut in as_completed(futures):
                job = futures[fut]
                try:
                    outcome = fut.result()
                    done += 1
                    remembered = sum(1 for e in outcome.parsed["events"] if e["event_remembered"])
                    log.info("[%d/%d] %s ok: %d/%d events remembered, %.1fs",
                             done + failed, len(jobs), job["job_id"], remembered,
                             len(outcome.parsed["events"]), outcome.meta.get("latency_s", 0))
                except ScoringError as exc:
                    failed += 1
                    store.mark_failed(run_tag, job["job_id"], job["attempts"] + config.MAX_ATTEMPTS, str(exc))
                    log.error("[%d/%d] %s FAILED: %s", done + failed, len(jobs), job["job_id"], exc)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    store.mark_failed(run_tag, job["job_id"], job["attempts"] + 1, repr(exc))
                    log.exception("[%d/%d] %s crashed", done + failed, len(jobs), job["job_id"])
    finally:
        if use_cache and not keep_caches:
            cleanup_caches(client, store, run_tag)

    elapsed = time.monotonic() - t0
    log.info("Finished: %d done, %d failed in %.1fs (%.1f s/job wall-clock)",
             done, failed, elapsed, elapsed / max(done + failed, 1))
    return {"done": done, "failed": failed, "elapsed_s": round(elapsed, 1)}
