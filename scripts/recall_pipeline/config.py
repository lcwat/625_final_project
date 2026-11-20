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

# Mohsen's scoring rules, copied from the PDF, sent as the model's instructions.
RULES_FILE = REPO_ROOT / "prompts" / "scoring_rules.md"

# Master-file sheet name per session (the cleaned free-recall sheets, ~41
# participants; the "Transcriptions" sheets cover only about a dozen).
FREE_RECALL_SHEETS = {1: "S1 FreeRecall", 2: "S2 Free Recall", 3: "S3 FreeRecall"}
# Cells shorter than this are placeholders ("x", "N/A", "MISSING"), not recall.
MIN_TRANSCRIPT_CHARS = 25

# ---- outputs -----------------------------------------------------------
OUTPUT_DIR = REPO_ROOT / "model_output"
DB_PATH = Path(os.getenv("RECALL_DB", OUTPUT_DIR / "recall_scoring.sqlite"))

# ---- provider / model --------------------------------------------------
# "azure" (Azure OpenAI), "openai" (platform.openai.com) or "gemini" (Google AI
# Studio). Auto-detected from which key is present, in that order; override
# with RECALL_PROVIDER or --provider.
if os.getenv("AZURE_OPENAI_API_KEY"):
    _default_provider = "azure"
elif os.getenv("OPENAI_API_KEY"):
    _default_provider = "openai"
else:
    _default_provider = "gemini"
PROVIDER = os.getenv("RECALL_PROVIDER", _default_provider).lower()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.0"))
GEMINI_THINKING_BUDGET = os.getenv("GEMINI_THINKING_BUDGET")  # unset = model default
GEMINI_CACHE_TTL_SECONDS = int(os.getenv("GEMINI_CACHE_TTL", str(2 * 60 * 60)))
GEMINI_CACHE_DISPLAY_PREFIX = os.getenv("GEMINI_CACHE_PREFIX", "ao25-freerecall")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")          # https://<resource>.openai.azure.com
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5")   # deployment name, not model name
AZURE_OPENAI_REASONING_EFFORT = os.getenv("AZURE_OPENAI_REASONING_EFFORT", "medium")  # gpt-5 / o-series only
AZURE_OPENAI_TEMPERATURE = os.getenv("AZURE_OPENAI_TEMPERATURE")   # leave unset for reasoning models

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")                       # model name on platform.openai.com
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")                          # leave unset for api.openai.com
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", AZURE_OPENAI_REASONING_EFFORT)
OPENAI_TEMPERATURE = os.getenv("OPENAI_TEMPERATURE")                    # leave unset for reasoning models

_DEFAULT_MODEL = {"azure": AZURE_OPENAI_DEPLOYMENT, "openai": OPENAI_MODEL, "gemini": GEMINI_MODEL}
MODEL = os.getenv("RECALL_MODEL", _DEFAULT_MODEL.get(PROVIDER, GEMINI_MODEL))
MAX_OUTPUT_TOKENS = int(os.getenv("RECALL_MAX_OUTPUT_TOKENS", "16384"))

# ---- concurrency / retries --------------------------------------------
WORKERS = int(os.getenv("RECALL_WORKERS", "8"))
REQUESTS_PER_MINUTE = int(os.getenv("RECALL_RPM", "60"))
MAX_ATTEMPTS = int(os.getenv("RECALL_MAX_ATTEMPTS", "6"))
BACKOFF_BASE_SECONDS = float(os.getenv("RECALL_BACKOFF_BASE", "2"))
BACKOFF_MAX_SECONDS = float(os.getenv("RECALL_BACKOFF_MAX", "90"))

# A tag written into every result row so repeated runs (different providers,
# models, prompt versions) can coexist in one database.
RUN_TAG = os.getenv("RECALL_RUN_TAG", "default")
