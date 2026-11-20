"""Load participant free-recall transcripts from the master workbook.

Each free-recall sheet has the layout:

    ID | SHAUN | SUMMER | BEAN | OSCAR | (marker column)

with a second `ID` header row partway down separating the two age cohorts
(100s = young adults, 200s = older adults) and blank spacer rows between.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from . import config

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transcript:
    participant_id: int
    session: int
    slideshow: str
    text: str

    @property
    def job_id(self) -> str:
        return f"{self.participant_id}-S{self.session}-{self.slideshow}"

    @property
    def cohort(self) -> str:
        return "young" if self.participant_id < 200 else "older"


def _clean_id(value) -> int | None:
    """Return an int participant id, or None for header/spacer rows."""
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value.isdigit():
            return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def load_transcripts(
    sessions: Iterable[int] | None = None,
    slideshows: Iterable[str] | None = None,
    participants: Iterable[int] | None = None,
    master_file=config.MASTER_FILE,
) -> list[Transcript]:
    """Read every scoreable (participant, session, slideshow) cell.
    Placeholder cells (shorter than MIN_TRANSCRIPT_CHARS) and duplicate
    participant rows are skipped and logged."""
    sessions = set(sessions) if sessions else set(config.FREE_RECALL_SHEETS)
    slideshows = set(slideshows) if slideshows else set(config.SLIDESHOWS)
    participants = set(participants) if participants else None

    out: list[Transcript] = []
    for session in sorted(sessions):
        sheet = config.FREE_RECALL_SHEETS[session]
        df = pd.read_excel(master_file, sheet_name=sheet, header=None)
        header = [str(h).strip().upper() if not pd.isna(h) else "" for h in df.iloc[0]]
        col_for = {name: header.index(name.upper()) for name in slideshows if name.upper() in header}
        seen: set[tuple[int, str]] = set()
        for _, row in df.iloc[1:].iterrows():
            pid = _clean_id(row.iloc[0])
            if pid is None or (participants and pid not in participants):
                continue
            for name, col in col_for.items():
                cell = row.iloc[col]
                text = "" if pd.isna(cell) else str(cell).replace("\xa0", " ").strip()
                if (pid, name) in seen:
                    log.warning("S%d %s %s: duplicate participant row skipped", session, pid, name)
                elif len(text) < config.MIN_TRANSCRIPT_CHARS:
                    log.debug("S%d %s %s: no transcript (%r)", session, pid, name, text)
                else:
                    seen.add((pid, name))
                    out.append(Transcript(pid, session, name, text))
    return out


if __name__ == "__main__":  # quick inspection
    ts = load_transcripts()
    print(f"{len(ts)} transcripts")
    by = pd.DataFrame([(t.session, t.slideshow, len(t.text.split())) for t in ts],
                      columns=["session", "slideshow", "words"])
    print(by.groupby(["session", "slideshow"])["words"].agg(["count", "mean", "max"]).round(0))
