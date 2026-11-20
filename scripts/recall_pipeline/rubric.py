"""Load the event-level codebooks that serve as the scoring rubric."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config

# Column names exactly as the scoring rules refer to them, in codebook order.
CODEBOOK_FIELDS = (
    "Slideshow",
    "EventID",
    "EventTitle",
    "EventStartImageID",
    "EventEndImageID",
    "GistLabel",
    "Object",
    "Action",
    "Person_Character",
    "Location",
    "Goal",
    "OtherRelevantDetails",
    "AllowedSynonyms",
)


def _cell_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).replace("\xa0", " ").strip()


@dataclass(frozen=True)
class Codebook:
    slideshow: str
    events: list[dict[str, str]]  # one dict per EventID, keys = CODEBOOK_FIELDS

    @property
    def event_ids(self) -> list[str]:
        return [e["EventID"] for e in self.events]

    def validate(self) -> None:
        ids = self.event_ids
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.slideshow}: duplicate EventIDs {ids}")
        expected = config.EXPECTED_EVENT_COUNTS[self.slideshow]
        if len(ids) != expected:
            raise ValueError(f"{self.slideshow}: expected {expected} events, found {len(ids)}")

    def render(self) -> str:
        """One <event> block per EventID with the column names the rules use."""
        blocks = []
        for event in self.events:
            lines = [f'<event id="{event["EventID"]}">']
            lines += [f"{col}: {event.get(col) or '(blank)'}" for col in CODEBOOK_FIELDS]
            lines.append("</event>")
            blocks.append("\n".join(lines))
        return f"# {self.slideshow}_Event_Codebook ({len(self.events)} events)\n\n" + "\n\n".join(blocks)


def load_codebook(slideshow: str) -> Codebook:
    path = config.RUBRIC_FILES[slideshow]
    df = pd.read_excel(path, sheet_name=f"{slideshow}_Event_Codebook")
    missing = [c for c in CODEBOOK_FIELDS if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: codebook missing columns {missing}")
    events = []
    for _, row in df.iterrows():
        event = {col: _cell_text(row[col]) for col in CODEBOOK_FIELDS}
        if event["EventID"]:
            events.append(event)
    cb = Codebook(slideshow, events)
    cb.validate()
    return cb


def load_all_codebooks() -> dict[str, Codebook]:
    return {s: load_codebook(s) for s in config.SLIDESHOWS}


if __name__ == "__main__":
    for s, cb in load_all_codebooks().items():
        text = cb.render()
        print(f"{s}: {len(cb.events)} events, ~{len(text) // 4:,} tokens rendered")
