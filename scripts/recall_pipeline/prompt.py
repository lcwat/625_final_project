"""Build the model's instructions: Mohsen's scoring rules (prompts/scoring_rules.md,
verbatim from the PDF, HTML review comments stripped) followed by one slideshow's
event codebook. That text is identical for every transcript of a slideshow, so
providers can cache it. The transcript goes in the user message.

PROMPT_VERSION is derived from the rules file so edits are tracked in results.
"""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache

from . import config
from .rubric import Codebook

PROMPT_LAYOUT_VERSION = "2"  # bump when the way rules/codebook/user message are assembled changes


@lru_cache(maxsize=1)
def load_rules() -> str:
    text = config.RULES_FILE.read_text(encoding="utf-8")
    return re.sub(r"[ \t]*<!--.*?-->", "", text, flags=re.DOTALL).strip()


@lru_cache(maxsize=1)
def prompt_version() -> str:
    digest = hashlib.sha1(load_rules().encode("utf-8")).hexdigest()[:8]
    return f"rules-{digest}.layout-{PROMPT_LAYOUT_VERSION}"


def build_system_instruction(codebook: Codebook) -> str:
    return f"{load_rules()}\n\n{codebook.render()}"


def build_user_message(slideshow: str, transcript: str) -> str:
    return (
        f"Score this participant's free-recall response for the {slideshow} slideshow.\n\n"
        f"<transcript>\n{transcript}\n</transcript>"
    )
