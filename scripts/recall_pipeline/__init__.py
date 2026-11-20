"""Parallel LLM scoring pipeline for EEG free-recall transcripts.

Modules:
    config   - paths, model name, tunables (env-overridable)
    data     - load participant transcripts from the master workbook
    rubric   - load event codebooks from the rubric workbooks
    schema   - Pydantic models the LLM must fill (enforced via response_schema)
    prompt   - scoring rules + codebook rendering for the system instruction
    db       - SQLite job queue and results store
    caching  - Gemini context caches (one per slideshow)
    scorer   - one API call per (participant, session, slideshow) with retries
    runner   - thread-pool execution with a shared rate limiter
    export   - results -> long CSV / summary CSV / Excel workbooks
"""
