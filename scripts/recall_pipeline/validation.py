"""Checks on what the model returned.

structural_problems: the response is unusable (wrong set of events) -> retry.
content_flags: worth a human look but the response is still used -> stored
with the result and exported in the ValidationFlags column.
"""
from __future__ import annotations

import re
import unicodedata

from .schema import CATEGORIES, ScoringResult


def _normalize(text: str) -> str:
    """Make quote matching forgiving of spacing, case, and typographic quotes only."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'}))
    return re.sub(r"\s+", " ", text).strip().lower()


def structural_problems(result: ScoringResult, codebook_ids: list[str]) -> list[str]:
    returned = [event.event_id.strip() for event in result.events]
    problems = []
    missing = [i for i in codebook_ids if i not in returned]
    unknown = [i for i in returned if i not in codebook_ids]
    duplicated = sorted({i for i in returned if returned.count(i) > 1})
    if missing:
        problems.append(f"missing events {missing}")
    if unknown:
        problems.append(f"unknown events {unknown}")
    if duplicated:
        problems.append(f"duplicated events {duplicated}")
    return problems


def content_flags(result: ScoringResult, transcript: str) -> list[str]:
    haystack = _normalize(transcript)
    flags = []
    if result.scoring_problem.strip():
        flags.append(f"model reported a scoring problem: {result.scoring_problem.strip()}")
    for event in result.events:
        credited = 0
        for field_name, _, prefix in CATEGORIES:
            for item in getattr(event, field_name):
                credited += 1
                # The rules allow several supporting phrases joined with "|"; check each one.
                quotes = [_normalize(part) for part in item.evidence.split("|") if part.strip()]
                if not quotes:
                    flags.append(f"event {event.event_id} {prefix} '{item.detail}': no evidence")
                elif any(q not in haystack for q in quotes):
                    flags.append(f"event {event.event_id} {prefix} '{item.detail}': evidence not in transcript")
        unique = len(event.unique_details)
        if credited and not unique:
            flags.append(f"event {event.event_id}: details credited but unique_details is empty")
        elif unique and not credited:
            flags.append(f"event {event.event_id}: unique_details listed with no category details")
        elif unique > credited:
            flags.append(f"event {event.event_id}: more unique details ({unique}) than credited details ({credited})")
    return flags
