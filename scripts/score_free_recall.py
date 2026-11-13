"""Score real free-recall transcripts against the event codebooks with Gemini.

One API call scores one (session, participant, slideshow) transcript against
that slideshow's full event codebook. The model only makes the judgment calls
(which rubric details were recalled, for which event, with a verbatim quote).
Counts, the remembered flag, totals, and output formatting are done here.

Calls run one at a time. `score_unit` is self-contained so a parallel runner
can call it for many units at once later.

Examples (run from the repo root):
    python scripts/score_free_recall.py --dry-run
    python scripts/score_free_recall.py --session 1 --participants 101 --slideshows Summer
    python scripts/score_free_recall.py --session 1
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from pydantic import BaseModel, Field, ValidationError

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "mohsen_files"
MASTER_FILE = DATA_DIR / "Ao25_MasterFile_FreeRecall_MD.xlsx"
RULES_FILE = ROOT / "prompts" / "scoring_rules.md"
OUTPUT_DIR = ROOT / "model_output"

DEFAULT_MODEL = "gemini-3.8-flash"
SLIDESHOWS = ("Bean", "Oscar", "Shaun", "Summer")
EXPECTED_EVENTS = {"Bean": 18, "Oscar": 17, "Shaun": 17, "Summer": 9}

# The cleaned free-recall sheets (41 participants), not the raw "Transcriptions"
# sheets, which cover only about a dozen participants.
SESSION_SHEETS = {1: "S1 FreeRecall", 2: "S2 Free Recall", 3: "S3 FreeRecall"}

# Cells shorter than this are placeholders ("x", "N/A", "MISSING"), not recall.
MIN_TRANSCRIPT_CHARS = 25

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

OUTPUT_COLUMNS = (
    ["Session", "CoderID", "ParticipantID", "Slideshow", "EventID", "RecallText"]
    + [f"{prefix}_{suffix}" for _, _, prefix in CATEGORIES for suffix in ("Recalled", "Count", "Evidence")]
    + [
        "UniqueDetailsRecalled",
        "DetailsRecalled_Count",
        "EventRemembered_0_1",
        "EventsRemembered_Total",
        "CoderNotes",
        "UnscoredRecall",
        "ValidationFlags",
    ]
)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# What the model returns
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Loading the rubric and the transcripts
# ---------------------------------------------------------------------------


@dataclass
class Unit:
    session: int
    participant_id: str
    slideshow: str
    transcript: str

    @property
    def key(self) -> str:
        return f"S{self.session}_{self.participant_id}_{self.slideshow}"


@dataclass
class Scored:
    unit: Unit
    result: ScoringResult
    flags: list[str] = field(default_factory=list)


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def load_codebook(slideshow: str) -> list[dict[str, str]]:
    """Return the event rows of one slideshow's codebook, in event order."""
    path = DATA_DIR / f"{slideshow}_Rubric_Workbook.xlsx"
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = workbook[f"{slideshow}_Event_Codebook"].iter_rows(values_only=True)
    header = [_cell_text(name) for name in next(rows)]
    events = []
    for row in rows:
        event = {name: _cell_text(value) for name, value in zip(header, row) if name}
        if event.get("EventID"):
            events.append(event)
    workbook.close()

    ids = [event["EventID"] for event in events]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{slideshow} codebook has duplicate EventIDs: {ids}")
    if len(ids) != EXPECTED_EVENTS[slideshow]:
        raise ValueError(f"{slideshow} codebook has {len(ids)} events, expected {EXPECTED_EVENTS[slideshow]}")
    return events


def load_units(session: int) -> tuple[list[Unit], list[str]]:
    """Return the scoreable transcripts for a session and a note for each cell skipped."""
    workbook = openpyxl.load_workbook(MASTER_FILE, read_only=True, data_only=True)
    rows = list(workbook[SESSION_SHEETS[session]].iter_rows(values_only=True))
    workbook.close()

    header = [_cell_text(name).upper() for name in rows[0]]
    columns = {name: header.index(name.upper()) for name in SLIDESHOWS}

    units, skipped, seen = [], [], set()
    for row in rows[1:]:
        participant_id = _cell_text(row[0])
        if not participant_id.isdigit():  # blank separator rows and the repeated header row
            continue
        for slideshow, column in columns.items():
            text = _cell_text(row[column]) if column < len(row) else ""
            key = (participant_id, slideshow)
            if key in seen:
                skipped.append(f"S{session} {participant_id} {slideshow}: duplicate participant row")
            elif len(text) < MIN_TRANSCRIPT_CHARS:
                skipped.append(f"S{session} {participant_id} {slideshow}: no transcript ({text!r})")
            else:
                seen.add(key)
                units.append(Unit(session, participant_id, slideshow, text))
    return units, skipped


# ---------------------------------------------------------------------------
# Building the prompt
# ---------------------------------------------------------------------------

# Column names exactly as the scoring rules refer to them.
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


def build_system_instruction(slideshow: str, codebook: list[dict[str, str]]) -> str:
    """Rules plus codebook. Identical for every transcript of a slideshow, so it can be cached."""
    blocks = []
    for event in codebook:
        lines = [f'<event id="{event["EventID"]}">']
        lines += [f"{column}: {event.get(column) or '(blank)'}" for column in CODEBOOK_FIELDS]
        lines.append("</event>")
        blocks.append("\n".join(lines))
    # The rules file carries review notes as HTML comments; they are not part of the prompt.
    rules = re.sub(r"[ \t]*<!--.*?-->", "", RULES_FILE.read_text(encoding="utf-8"), flags=re.DOTALL)
    return (
        rules.strip()
        + f"\n\n# {slideshow}_Event_Codebook ({len(codebook)} events)\n\n"
        + "\n\n".join(blocks)
    )


def build_user_message(unit: Unit) -> str:
    return (
        f"Score this participant's free-recall response for the {unit.slideshow} slideshow.\n\n"
        f"<transcript>\n{unit.transcript}\n</transcript>"
    )


# ---------------------------------------------------------------------------
# Checking what the model returned
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Make quote matching forgiving of spacing, case, and typographic quotes only."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'}))
    return re.sub(r"\s+", " ", text).strip().lower()


def structural_problems(result: ScoringResult, codebook_ids: list[str]) -> list[str]:
    """Problems that make the response unusable: the set of events is wrong."""
    returned = [event.event_id.strip() for event in result.events]
    problems = []
    missing = [event_id for event_id in codebook_ids if event_id not in returned]
    unknown = [event_id for event_id in returned if event_id not in codebook_ids]
    duplicated = sorted({event_id for event_id in returned if returned.count(event_id) > 1})
    if missing:
        problems.append(f"missing events {missing}")
    if unknown:
        problems.append(f"unknown events {unknown}")
    if duplicated:
        problems.append(f"duplicated events {duplicated}")
    return problems


def content_flags(result: ScoringResult, transcript: str) -> list[str]:
    """Problems worth a human look that do not stop the response being used."""
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
                elif any(quote not in haystack for quote in quotes):
                    flags.append(f"event {event.event_id} {prefix} '{item.detail}': evidence not in transcript")
        unique = len(event.unique_details)
        if credited and not unique:
            flags.append(f"event {event.event_id}: details credited but unique_details is empty")
        elif unique and not credited:
            flags.append(f"event {event.event_id}: unique_details listed with no category details")
        elif unique > credited:
            flags.append(f"event {event.event_id}: more unique details ({unique}) than credited details ({credited})")
    return flags


# ---------------------------------------------------------------------------
# Calling the model
# ---------------------------------------------------------------------------


def call_model(client, model: str, system_instruction: str, user_message: str, max_retries: int = 6) -> str:
    """Send one request and return the JSON text. Retries rate limits and server errors."""
    from google.genai import errors, types

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=ScoringResult,
        temperature=0.0,
    )
    delay = 2.0
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(model=model, contents=user_message, config=config)
            return response.text or ""
        except errors.APIError as error:
            if error.code not in RETRYABLE_STATUS or attempt == max_retries:
                raise
            wait = delay + random.uniform(0, 1)
            print(f"    HTTP {error.code}, retry {attempt}/{max_retries - 1} in {wait:.0f}s")
            time.sleep(wait)
            delay = min(delay * 2, 60)
    raise RuntimeError("unreachable")


def score_unit(client, model: str, unit: Unit, codebook: list[dict[str, str]], system_instruction: str,
               attempts: int = 2) -> Scored:
    """Score one transcript. Asks again if the response is malformed or has the wrong events."""
    codebook_ids = [event["EventID"] for event in codebook]
    problems: list[str] = []
    for _ in range(attempts):
        raw = call_model(client, model, system_instruction, build_user_message(unit))
        try:
            result = ScoringResult.model_validate_json(raw)
        except ValidationError as error:
            problems = [f"response did not match the schema ({error.error_count()} errors)"]
            continue
        problems = structural_problems(result, codebook_ids)
        if not problems:
            order = {event_id: position for position, event_id in enumerate(codebook_ids)}
            result.events.sort(key=lambda event: order[event.event_id.strip()])
            return Scored(unit, result, content_flags(result, unit.transcript))
    raise RuntimeError(f"{unit.key}: unusable response after {attempts} attempts: {'; '.join(problems)}")


# ---------------------------------------------------------------------------
# Turning results into the scoring table
# ---------------------------------------------------------------------------


def _label(text: str) -> str:
    """Semicolons separate details in the output, so keep them out of the labels."""
    return re.sub(r"\s+", " ", text.replace(";", ",")).strip()


def to_rows(scored: Scored, coder_id: str) -> list[dict]:
    """One participant-response row, one row per event, then one TOTAL row."""
    unit, result = scored.unit, scored.result
    base = {"Session": unit.session, "CoderID": coder_id, "ParticipantID": unit.participant_id,
            "Slideshow": unit.slideshow}
    count_columns = [f"{prefix}_Count" for _, _, prefix in CATEGORIES] + ["DetailsRecalled_Count"]

    rows = [{
        **base,
        "RecallText": unit.transcript,
        "CoderNotes": "Participant response",
        "UnscoredRecall": " | ".join(f"[{item.reason}] {item.text} ({item.note})" for item in result.unscored),
        "ValidationFlags": " | ".join(scored.flags),
    }]

    totals = dict.fromkeys(count_columns, 0)
    events_remembered = 0
    for event in result.events:
        row = {**base, "EventID": event.event_id.strip(), "CoderNotes": event.coder_notes.strip()}
        for field_name, _, prefix in CATEGORIES:
            items = getattr(event, field_name)
            row[f"{prefix}_Recalled"] = "; ".join(_label(item.detail) for item in items)
            row[f"{prefix}_Count"] = len(items)
            row[f"{prefix}_Evidence"] = " | ".join(item.evidence.strip() for item in items)
        unique = [_label(detail) for detail in event.unique_details if detail.strip()]
        row["UniqueDetailsRecalled"] = "; ".join(unique)
        row["DetailsRecalled_Count"] = len(unique)
        row["EventRemembered_0_1"] = int(len(unique) >= 1)
        events_remembered += row["EventRemembered_0_1"]
        for column in count_columns:
            totals[column] += row[column]
        rows.append(row)

    rows.append({**base, "EventID": "TOTAL", **totals, "EventsRemembered_Total": events_remembered,
                 "CoderNotes": "Participant totals"})
    return rows


def write_table(scored_units: list[Scored], coder_id: str, path: Path) -> None:
    ordered = sorted(scored_units, key=lambda scored: (int(scored.unit.participant_id),
                                                       SLIDESHOWS.index(scored.unit.slideshow)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:  # BOM so Excel reads it as UTF-8
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, restval="")
        writer.writeheader()
        for scored in ordered:
            writer.writerows(to_rows(scored, coder_id))


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score free-recall transcripts against the event codebooks.")
    parser.add_argument("--session", type=int, choices=sorted(SESSION_SHEETS), default=1)
    parser.add_argument("--slideshows", nargs="+", choices=SLIDESHOWS, default=list(SLIDESHOWS))
    parser.add_argument("--participants", nargs="+", help="Participant IDs to score. Default: all.")
    parser.add_argument("--limit", type=int, help="Score at most this many transcripts.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--coder-id", help="Value for the CoderID column. Default: the model name.")
    parser.add_argument("--force", action="store_true", help="Score again even if a saved response exists.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be sent without calling the API.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    units, skipped = load_units(args.session)
    units = [unit for unit in units if unit.slideshow in args.slideshows]
    if args.participants:
        units = [unit for unit in units if unit.participant_id in args.participants]
    # Group by slideshow so consecutive requests share the same long system instruction.
    units.sort(key=lambda unit: (SLIDESHOWS.index(unit.slideshow), int(unit.participant_id)))
    if args.limit:
        units = units[: args.limit]

    codebooks = {name: load_codebook(name) for name in args.slideshows}
    instructions = {name: build_system_instruction(name, codebooks[name]) for name in args.slideshows}

    if args.dry_run:
        print(f"Session {args.session}: {len(units)} transcripts to score, {len(skipped)} cells skipped")
        for name in args.slideshows:
            count = sum(unit.slideshow == name for unit in units)
            print(f"  {name}: {count} transcripts, {len(codebooks[name])} events, "
                  f"system instruction about {len(instructions[name]) // 4:,} tokens")
        for note in skipped:
            print(f"  skipped {note}")
        return 0

    if not units:
        print("No transcripts match those filters.")
        return 1

    from dotenv import load_dotenv
    from google import genai

    load_dotenv(ROOT / ".env")
    client = genai.Client()

    raw_dir = OUTPUT_DIR / "raw" / args.model
    raw_dir.mkdir(parents=True, exist_ok=True)
    scored_units, failures = [], []
    started = time.perf_counter()

    for position, unit in enumerate(units, start=1):
        raw_path = raw_dir / f"{unit.key}.json"
        codebook = codebooks[unit.slideshow]
        try:
            if raw_path.exists() and not args.force:
                result = ScoringResult.model_validate_json(raw_path.read_text(encoding="utf-8"))
                scored = Scored(unit, result, content_flags(result, unit.transcript))
                source = "saved"
            else:
                scored = score_unit(client, args.model, unit, codebook, instructions[unit.slideshow])
                raw_path.write_text(scored.result.model_dump_json(indent=2), encoding="utf-8")
                source = "scored"
        except Exception as error:  # keep going so one bad transcript does not lose the rest
            failures.append(f"{unit.key}: {error}")
            print(f"[{position}/{len(units)}] {unit.key} FAILED: {error}")
            continue
        scored_units.append(scored)
        remembered = sum(bool(event.unique_details) for event in scored.result.events)
        print(f"[{position}/{len(units)}] {unit.key} {source}: {remembered}/{len(codebook)} events remembered, "
              f"{len(scored.flags)} flags")

    table_path = OUTPUT_DIR / f"{args.model}_S{args.session}_scoring_long.csv"
    write_table(scored_units, args.coder_id or args.model, table_path)

    elapsed = time.perf_counter() - started
    flagged = sum(bool(scored.flags) for scored in scored_units)
    print(f"\n{len(scored_units)} scored, {len(failures)} failed, {flagged} with validation flags, {elapsed:.0f}s")
    print(f"Table: {table_path.relative_to(ROOT)}")
    for failure in failures:
        print(f"  failed {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
