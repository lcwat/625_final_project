"""Structured output the model must return for one (participant, slideshow).

Counts, totals, and summary rows are deliberately NOT part of the schema:
they are derived in Python from the lists below so they are always
internally consistent (see export.py).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CategoryMatch(BaseModel):
    recalled: list[str] = Field(
        default_factory=list,
        description="Distinct rubric details from this category the participant "
                    "recalled, as short standardized labels taken from the codebook. "
                    "Empty if nothing in this category was recalled.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Exact participant wording supporting each recalled detail, "
                    "quoted verbatim from the transcript (shortest phrase that "
                    "clearly supports the match). Same length and order as `recalled`.",
    )


class EventScore(BaseModel):
    event_id: int = Field(description="EventID from the codebook.")
    gist: CategoryMatch = Field(default_factory=CategoryMatch, description="Matches against GistLabel.")
    objects: CategoryMatch = Field(default_factory=CategoryMatch, description="Matches against Object.")
    actions: CategoryMatch = Field(default_factory=CategoryMatch, description="Matches against Action.")
    persons: CategoryMatch = Field(default_factory=CategoryMatch, description="Matches against Person_Character.")
    locations: CategoryMatch = Field(default_factory=CategoryMatch, description="Matches against Location.")
    goals: CategoryMatch = Field(default_factory=CategoryMatch, description="Matches against Goal.")
    other_details: CategoryMatch = Field(default_factory=CategoryMatch, description="Matches against OtherRelevantDetails.")
    unique_details: list[str] = Field(
        default_factory=list,
        description="Every distinct semantic detail recalled for this event, listed "
                    "ONCE after removing repetition, synonym/paraphrase duplicates, "
                    "and cross-category duplicates. Empty if the event was not recalled.",
    )
    event_remembered: bool = Field(
        description="True if at least one valid, reliably assignable detail was "
                    "recalled for this event (i.e. unique_details is non-empty).",
    )
    coder_notes: str = Field(
        default="",
        description="Ambiguity, hedged recall, self-corrections, or unmatched "
                    "material relevant to this event. Empty string if none.",
    )


class SlideshowScore(BaseModel):
    slideshow: str = Field(description="Slideshow name exactly as given.")
    participant_id: int = Field(description="Participant ID exactly as given.")
    events: list[EventScore] = Field(
        description="Exactly one entry per EventID in the codebook, in EventID order, "
                    "including events with nothing recalled.",
    )
    unmatched_recall: list[str] = Field(
        default_factory=list,
        description="Substantive participant statements that could not be matched to "
                    "any event: not in the rubric, too vague, contradictory, or "
                    "ambiguous across events. Each entry: the participant wording "
                    "plus a short reason.",
    )
    coder_notes: str = Field(default="", description="Slideshow-level notes, if any.")


# Mapping from schema attribute -> rubric field name / output column prefix.
CATEGORY_FIELDS = {
    "gist": ("GistLabel", "GistLabel"),
    "objects": ("Object", "Object"),
    "actions": ("Action", "Action"),
    "persons": ("Person_Character", "PersonCharacter"),
    "locations": ("Location", "Location"),
    "goals": ("Goal", "Goal"),
    "other_details": ("OtherRelevantDetails", "OtherRelevantDetails"),
}
