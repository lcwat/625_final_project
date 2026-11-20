"""Structured output the model must return for one (participant, slideshow).

The model only makes the judgment calls: which rubric details were recalled,
for which event, with a verbatim quote. Counts, the remembered flag, totals
and output formatting are computed in Python (export.py) so they are always
internally consistent. Field names match how prompts/scoring_rules.md
explains the JSON to the model, so change them together.

No field has a default: Azure OpenAI strict structured output requires every
property to be present, and Gemini's response_schema behaves the same way.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Detail(BaseModel):
    detail: str = Field(description="Short standard label for the recalled detail, following the codebook wording.")
    evidence: str = Field(description="Exact continuous wording copied from the transcript that supports the detail.")


class EventScore(BaseModel):
    event_id: str = Field(description="EventID exactly as it appears in the codebook.")
    gist: list[Detail] = Field(description="Recalled details matching GistLabel.")
    objects: list[Detail] = Field(description="Recalled details matching Object.")
    actions: list[Detail] = Field(description="Recalled details matching Action.")
    persons_characters: list[Detail] = Field(description="Recalled details matching Person_Character.")
    locations: list[Detail] = Field(description="Recalled details matching Location.")
    goals: list[Detail] = Field(description="Recalled details matching Goal.")
    other_details: list[Detail] = Field(description="Recalled details matching OtherRelevantDetails.")
    unique_details: list[str] = Field(
        description="Every distinct detail recalled for this event, listed once, after removing cross-category duplicates."
    )
    coder_notes: str = Field(description="Judgment calls for this event. Empty when there is nothing to note.")


class UnscoredUnit(BaseModel):
    text: str = Field(description="The participant's wording that earned no credit.")
    reason: str = Field(description="One of: unmatched, ambiguous, contradictory, vague, withdrawn.")
    note: str = Field(description="Brief explanation, naming candidate events when ambiguous.")


class ScoringResult(BaseModel):
    events: list[EventScore] = Field(description="One entry per EventID in the codebook, in codebook order.")
    unscored: list[UnscoredUnit] = Field(description="Substantive recall that was not credited to any event.")
    scoring_problem: str = Field(
        description="The exact problem if reliable scoring is impossible. Empty when scoring went ahead normally."
    )


# (field on EventScore, codebook column, output column prefix)
CATEGORIES = (
    ("gist", "GistLabel", "GistLabel"),
    ("objects", "Object", "Object"),
    ("actions", "Action", "Action"),
    ("persons_characters", "Person_Character", "PersonCharacter"),
    ("locations", "Location", "Location"),
    ("goals", "Goal", "Goal"),
    ("other_details", "OtherRelevantDetails", "OtherRelevantDetails"),
)
