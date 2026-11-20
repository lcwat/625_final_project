"""Parallel execution: prepare the provider once per slideshow, then fan jobs
out over a thread pool. `workers=1` is the serial baseline."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config
from .db import Store
from .prompt import build_system_instruction
from .providers import make_provider
from .rubric import load_all_codebooks
from .scorer import RateLimiter, ScoringError, score_transcript

log = logging.getLogger(__name__)


def prepare_handles(provider, store: Store, systems: dict[str, str], run_tag: str) -> dict[str, str | None]:
    """Create (or reuse) one cache handle per slideshow. None = rubric sent inline."""
    handles: dict[str, str | None] = {}
    existing = store.get_caches(run_tag, provider.name)
    for slideshow, system in systems.items():
        h = existing.get(slideshow)
        if h and provider.handle_exists(h):
            log.info("Reusing %s cache %s for %s", provider.name, h, slideshow)
        else:
            h = provider.prepare(system, slideshow, run_tag)
            if h:
                store.save_cache(run_tag, provider.name, slideshow, h, provider.model)
        handles[slideshow] = h
    return handles


def cleanup_handles(provider, store: Store, run_tag: str) -> None:
    for _, h in store.get_caches(run_tag, provider.name).items():
        provider.cleanup(h)
    store.delete_cache_rows(run_tag, provider.name)


def run(store: Store, run_tag: str = config.RUN_TAG, provider_name: str = config.PROVIDER,
        model: str | None = None, workers: int = config.WORKERS, rpm: int = config.REQUESTS_PER_MINUTE,
        use_cache: bool = True, keep_caches: bool = False, retry_failed: bool = True,
        limit: int | None = None) -> dict:
    """Score every pending job for `run_tag`. Returns a summary dict."""
    jobs = store.pending_jobs(run_tag, include_failed=retry_failed)
    if limit:
        jobs = jobs[:limit]
    if not jobs:
        log.info("No pending jobs for run_tag=%s", run_tag)
        return {"done": 0, "failed": 0, "elapsed_s": 0.0}

    codebooks = load_all_codebooks()
    systems = {s: build_system_instruction(cb) for s, cb in codebooks.items()}
    provider = make_provider(provider_name, model, use_cache)
    handles = prepare_handles(provider, store, systems, run_tag)
    limiter = RateLimiter(rpm)
    done = failed = 0
    t0 = time.monotonic()

    def work(job):
        s = job["slideshow"]
        outcome = score_transcript(provider, codebooks[s], systems[s], job["transcript"], handles.get(s), limiter)
        store.save_result(run_tag, job, outcome, job["attempts"] + outcome.attempts)
        return outcome

    log.info("Scoring %d jobs: provider=%s model=%s workers=%d rpm<=%d cache=%s",
             len(jobs), provider.name, provider.model, workers, rpm,
             "explicit" if any(handles.values()) else ("automatic" if provider.name == "azure" else "none"))
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(work, job): job for job in jobs}
            for fut in as_completed(futures):
                job = futures[fut]
                try:
                    o = fut.result()
                    done += 1
                    remembered = sum(bool(e.unique_details) for e in o.result.events)
                    log.info("[%d/%d] %s ok: %d/%d events remembered, %d flags, %.1fs, cached=%s",
                             done + failed, len(jobs), job["job_id"], remembered, len(o.result.events),
                             len(o.flags), o.meta.get("latency_s", 0), o.meta.get("cached_tokens"))
                except ScoringError as exc:
                    failed += 1
                    store.mark_failed(run_tag, job["job_id"], job["attempts"] + config.MAX_ATTEMPTS, str(exc))
                    log.error("[%d/%d] %s FAILED: %s", done + failed, len(jobs), job["job_id"], exc)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    store.mark_failed(run_tag, job["job_id"], job["attempts"] + 1, repr(exc))
                    log.exception("[%d/%d] %s crashed", done + failed, len(jobs), job["job_id"])
    finally:
        if not keep_caches:
            cleanup_handles(provider, store, run_tag)

    elapsed = time.monotonic() - t0
    log.info("Finished: %d done, %d failed in %.1fs (%.1f s/job wall-clock)",
             done, failed, elapsed, elapsed / max(done + failed, 1))
    return {"done": done, "failed": failed, "elapsed_s": round(elapsed, 1)}
