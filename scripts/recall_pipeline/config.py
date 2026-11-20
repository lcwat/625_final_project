"""Central configuration. Everything here can be overridden by environment
variables (loaded from the repo-root .env by python-dotenv)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

# ---- input files -------------------------------------------------------
MOHSEN_DIR = REPO_ROOT / "mohsen_files"
MASTER_FILE = MOHSEN_DIR / "Ao25_MasterFile_FreeRecall_MD.xlsx"
RUBRIC_FILES = {
    "Bean": MOHSEN_DIR / "Bean_Rubric_Workbook.xlsx",
    "Oscar": MOHSEN_DIR / "Oscar_Rubric_Workbook.xlsx",
    "Shaun": MOHSEN_DIR / "Shaun_Rubric_Workbook.xlsx",
    "Summer": MOHSEN_DIR / "Summer_Rubric_Workbook.xlsx",
}
SLIDESHOWS = list(RUBRIC_FILES)
EXPECTED_EVENT_COUNTS = {"Bean": 18, "Oscar": 17, "Shaun": 17, "Summer": 9}

# Master-file sheet name per session. Column headers are upper-case there.
FREE_RECALL_SHEETS = {1: "S1 FreeRecall", 2: "S2 Free Recall", 3: "S3 FreeRecall"}

# ---- outputs -----------------------------------------------------------
OUTPUT_DIR = REPO_ROOT / "model_output"
DB_PATH = Path(os.getenv("RECALL_DB", OUTPUT_DIR / "recall_scoring.sqlite"))

# ---- model / API -------------------------------------------------------
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.1"))
MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "16384"))
# Optional thinking budget; leave unset to use the model default.
THINKING_BUDGET = os.getenv("GEMINI_THINKING_BUDGET")

# Context cache lifetime. Long enough to cover a full run; caches are deleted
# explicitly at the end of a run anyway.
CACHE_TTL_SECONDS = int(os.getenv("GEMINI_CACHE_TTL", str(2 * 60 * 60)))
CACHE_DISPLAY_PREFIX = os.getenv("GEMINI_CACHE_PREFIX", "ao25-freerecall")

# ---- concurrency / retries --------------------------------------------
WORKERS = int(os.getenv("RECALL_WORKERS", "8"))
REQUESTS_PER_MINUTE = int(os.getenv("RECALL_RPM", "60"))
MAX_ATTEMPTS = int(os.getenv("RECALL_MAX_ATTEMPTS", "6"))
BACKOFF_BASE_SECONDS = float(os.getenv("RECALL_BACKOFF_BASE", "2"))
BACKOFF_MAX_SECONDS = float(os.getenv("RECALL_BACKOFF_MAX", "90"))

# A tag written into every result row so repeated runs (different prompt
# versions, models, temperatures) can coexist in one database.
RUN_TAG = os.getenv("RECALL_RUN_TAG", "default")
