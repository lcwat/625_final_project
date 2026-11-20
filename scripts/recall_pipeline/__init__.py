"""LLM scoring pipeline for EEG free-recall transcripts (serial or parallel).

Modules:
    config      - paths, provider/model selection, tunables (env-overridable)
    data        - load participant transcripts from the master workbook
    rubric      - load event codebooks from the rubric workbooks
    schema      - Pydantic models the model must fill (strict structured output)
    prompt      - Mohsen's scoring rules (prompts/scoring_rules.md) + codebook
    validation  - structural checks (retry) and content flags (human review)
    providers   - Gemini (explicit context cache) and Azure OpenAI (auto cache)
    scorer      - one model call per transcript with retries + rate limiter
    runner      - thread-pool execution; workers=1 is the serial baseline
    db          - SQLite job queue and results store (resumable runs)
    export      - results -> scoring-long / summary / run-stats CSV, xlsx
"""
