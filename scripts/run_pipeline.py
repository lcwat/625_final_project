"""Command-line entry point for the free-recall scoring pipeline.

    python scripts/run_pipeline.py init   [--sessions 1] [--slideshows Summer] [--participants 101 102]
    python scripts/run_pipeline.py run    [--provider azure|openai|gemini] [--model NAME] [--workers 8] [--rpm 60] [--limit 5]
    python scripts/run_pipeline.py status
    python scripts/run_pipeline.py export [--excel]
    python scripts/run_pipeline.py preview --participant 101 --session 1 --slideshow Summer
    python scripts/run_pipeline.py clean-caches

`run --workers 1` is the serial baseline; raise --workers for the parallel run.
All commands accept --run-tag (default from RECALL_RUN_TAG or "default") so you
can keep several provider/model/prompt configurations side by side in one database.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recall_pipeline import config  # noqa: E402
from recall_pipeline.data import load_transcripts  # noqa: E402
from recall_pipeline.db import Store  # noqa: E402


def cmd_init(args, store: Store) -> None:
    ts = load_transcripts(sessions=args.sessions, slideshows=args.slideshows, participants=args.participants)
    added = store.add_jobs(ts, args.run_tag)
    print(f"Loaded {len(ts)} transcripts; {added} new jobs added to run '{args.run_tag}'.")
    print("Status:", store.job_counts(args.run_tag))


def cmd_status(args, store: Store) -> None:
    counts = store.job_counts(args.run_tag)
    print(f"Run '{args.run_tag}': {counts or 'no jobs'}")
    failed = [j for j in store.pending_jobs(args.run_tag) if j["status"] == "failed"]
    for j in failed[:20]:
        print(f"  failed {j['job_id']} after {j['attempts']} attempts: {j['last_error'][:160]}")
    if len(failed) > 20:
        print(f"  ... and {len(failed) - 20} more")


def cmd_run(args, store: Store) -> None:
    from recall_pipeline.runner import run  # lazy: needs the provider SDK

    summary = run(store, run_tag=args.run_tag, provider_name=args.provider, model=args.model,
                  workers=args.workers, rpm=args.rpm, use_cache=not args.no_cache, keep_caches=args.keep_caches,
                  retry_failed=not args.skip_failed, limit=args.limit)
    print("Run summary:", summary)
    print("Status:", store.job_counts(args.run_tag))


def cmd_export(args, store: Store) -> None:
    from recall_pipeline.export import export

    for p in export(store, run_tag=args.run_tag, out_dir=args.out_dir, excel=args.excel, coder_id=args.coder_id):
        print("wrote", p)


def cmd_preview(args, store: Store) -> None:
    """Print the exact prompt that would be sent for one job (no API call)."""
    from recall_pipeline.prompt import build_system_instruction, build_user_message, prompt_version
    from recall_pipeline.rubric import load_codebook

    ts = load_transcripts(sessions=[args.session], slideshows=[args.slideshow], participants=[args.participant])
    if not ts:
        sys.exit("no transcript found for that participant/session/slideshow")
    cb = load_codebook(args.slideshow)
    system = build_system_instruction(cb)
    user = build_user_message(ts[0].slideshow, ts[0].text)
    print("=" * 30, "SYSTEM INSTRUCTION (identical for every transcript of this slideshow; cached)", "=" * 30)
    print(system)
    print("=" * 30, "USER MESSAGE (per call)", "=" * 30)
    print(user)
    print("=" * 80)
    print(f"prompt version {prompt_version()}; approx tokens: system={len(system) // 4:,}, user={len(user) // 4:,}")


def cmd_clean_caches(args, store: Store) -> None:
    from recall_pipeline.providers import make_provider
    from recall_pipeline.runner import cleanup_handles

    cleanup_handles(make_provider(args.provider), store, args.run_tag)
    print("caches removed for run", args.run_tag)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-tag", default=config.RUN_TAG)
    p.add_argument("--db", default=str(config.DB_PATH))
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="load transcripts into the job table")
    s.add_argument("--sessions", type=int, nargs="*")
    s.add_argument("--slideshows", nargs="*", choices=config.SLIDESHOWS)
    s.add_argument("--participants", type=int, nargs="*")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("status", help="show job counts and failures")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("run", help="score pending jobs (serial with --workers 1, parallel otherwise)")
    s.add_argument("--provider", default=config.PROVIDER, choices=["azure", "openai", "gemini"])
    s.add_argument("--model", help="Azure deployment name, OpenAI model name, or Gemini model name (default from .env)")
    s.add_argument("--workers", type=int, default=config.WORKERS)
    s.add_argument("--rpm", type=int, default=config.REQUESTS_PER_MINUTE)
    s.add_argument("--limit", type=int, help="score at most N jobs (smoke test)")
    s.add_argument("--no-cache", action="store_true", help="Gemini: send the rubric inline instead of a context cache")
    s.add_argument("--keep-caches", action="store_true", help="Gemini: leave context caches alive after the run")
    s.add_argument("--skip-failed", action="store_true", help="do not retry jobs that previously failed")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("export", help="write CSV (and optionally Excel) deliverables")
    s.add_argument("--out-dir", default=str(config.OUTPUT_DIR))
    s.add_argument("--excel", action="store_true")
    s.add_argument("--coder-id", help="CoderID column value (default: the model/deployment name)")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("preview", help="print the prompt for one job without calling the API")
    s.add_argument("--participant", type=int, required=True)
    s.add_argument("--session", type=int, default=1)
    s.add_argument("--slideshow", required=True, choices=config.SLIDESHOWS)
    s.set_defaults(func=cmd_preview)

    s = sub.add_parser("clean-caches", help="delete any context caches recorded for this run")
    s.add_argument("--provider", default=config.PROVIDER, choices=["azure", "openai", "gemini"])
    s.set_defaults(func=cmd_clean_caches)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpcore", "openai", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    store = Store(Path(args.db))
    args.func(args, store)


if __name__ == "__main__":
    main()
