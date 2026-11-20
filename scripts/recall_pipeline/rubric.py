"""Load the event-level codebooks that serve as the scoring rubric."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config

SCOREABLE_FIELDS = [
    "GistLabel",
    "Object",
    "Action",
    "Person_Character",
    "Location",
    "Goal",
    "OtherRelevantDetails",
]
CODEBOOK_COLUMNS = [
    "Slideshow", "EventID", "EventTitle", "EventStartImageID", "EventEndImageID",
    *SCOREABLE_FIELDS, "AllowedSynonyms",
]


@dataclass(frozen=True)
class Codebook:
    slideshow: str
    events: pd.DataFrame  # one row per EventID, CODEBOOK_COLUMNS

    @property
    def event_ids(self) -> list[int]:
        return [int(e) for e in self.events["EventID"]]

    def validate(self) -> None:
        ids = self.event_ids
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.slideshow}: duplicate EventIDs {ids}")
        expected = config.EXPECTED_EVENT_COUNTS[self.slideshow]
        if len(ids) != expected:
            raise ValueError(f"{self.slideshow}: expected {expected} events, found {len(ids)}")
        if ids != sorted(ids):
            raise ValueError(f"{self.slideshow}: EventIDs out of order {ids}")

    def render(self) -> str:
        """Plain-text rendering used inside the system instruction / cache."""
        lines = [f"EVENT CODEBOOK FOR SLIDESHOW: {self.slideshow}",
                 f"Total events: {len(self.events)}", ""]
        for _, row in self.events.iterrows():
            lines.append(f"=== EventID {int(row['EventID'])}: {row['EventTitle']} ===")
            for field in SCOREABLE_FIELDS + ["AllowedSynonyms"]:
                val = row[field]
                if pd.isna(val) or not str(val).strip():
                    continue
                lines.append(f"{field}: {str(val).strip()}")
            lines.append("")
        return "\n".join(lines)


def load_codebook(slideshow: str) -> Codebook:
    path = config.RUBRIC_FILES[slideshow]
    df = pd.read_excel(path, sheet_name=f"{slideshow}_Event_Codebook")
    missing = [c for c in CODEBOOK_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: codebook missing columns {missing}")
    df = df[CODEBOOK_COLUMNS].dropna(subset=["EventID"]).copy()
    df["EventID"] = df["EventID"].astype(int)
    cb = Codebook(slideshow, df.reset_index(drop=True))
    cb.validate()
    return cb


def load_all_codebooks() -> dict[str, Codebook]:
    return {s: load_codebook(s) for s in config.SLIDESHOWS}


if __name__ == "__main__":
    for s, cb in load_all_codebooks().items():
        text = cb.render()
        print(f"{s}: {len(cb.events)} events, ~{len(text.split())} words rendered")
