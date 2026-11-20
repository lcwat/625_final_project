"""Turn stored results into the deliverables.

- `<run>_scoring_long.csv`  one row per (participant, session, slideshow, event),
  in the 31-column layout from Mohsen's prompt, plus a participant-response row
  and a TOTAL row per block.
- `<run>_summary.csv`       one row per (participant, session, slideshow) plus a
  per-session total row, mirroring Session1_Summary.
- `<run>_run_stats.csv`     tokens / latency / attempts per job (for the
  parallelism write-up).
- `<run>_session{N}.xlsx`   optional Excel workbook with README / Summary /
  Scoring_Long sheets per session, written as plain ranges (no table XML).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import config
from .db import Store
from .schema import CATEGORY_FIELDS

CODER_ID_DEFAULT = "LLM"

SCORING_LONG_COLUMNS = ["CoderID", "ParticipantID", "Session", "Slideshow", "EventID", "RecallText"]
for _, prefix in CATEGORY_FIELDS.values():
    SCORING_LONG_COLUMNS += [f"{prefix}_Recalled", f"{prefix}_Count", f"{prefix}_Evidence"]
SCORING_LONG_COLUMNS += ["UniqueDetailsRecalled", "DetailsRecalled_Count", "EventRemembered_0_1",
                         "EventsRemembered_Total", "CoderNotes"]

SUMMARY_COLUMNS = ["ParticipantID", "Session", "Cohort", "Slideshow", "TotalEvents", "EventsRemembered",
                   "EventsNotRemembered"] + [f"{p}_Total" for _, p in CATEGORY_FIELDS.values()] + \
                  ["UniqueDetails_Total", "UnmatchedRecall_Count", "WordCount"]


def _join(items: list[str], sep: str) -> str:
    return sep.join(s.strip() for s in items if s and s.strip())


def _event_row(base: dict, ev: dict) -> dict:
    row = dict(base, EventID=int(ev["event_id"]), RecallText="")
    for attr, (_, prefix) in CATEGORY_FIELDS.items():
        cm = ev.get(attr) or {}
        recalled = cm.get("recalled") or []
        evidence = cm.get("evidence") or []
        row[f"{prefix}_Recalled"] = _join(recalled, "; ")
        row[f"{prefix}_Count"] = len(recalled)
        row[f"{prefix}_Evidence"] = _join(evidence, " | ")
    uniq = ev.get("unique_details") or []
    row["UniqueDetailsRecalled"] = _join(uniq, "; ")
    row["DetailsRecalled_Count"] = len(uniq)
    row["EventRemembered_0_1"] = int(bool(ev.get("event_remembered")))
    row["EventsRemembered_Total"] = ""
    row["CoderNotes"] = ev.get("coder_notes") or ""
    return row


def build_frames(store: Store, run_tag: str = config.RUN_TAG, coder_id: str = CODER_ID_DEFAULT):
    """Return (scoring_long, summary, run_stats) DataFrames."""
    long_rows, summary_rows, stat_rows = [], [], []
    for r in store.fetch_results(run_tag):
        parsed = json.loads(r["raw_json"])
        base = dict(CoderID=coder_id, ParticipantID=r["participant_id"], Session=r["session"],
                    Slideshow=r["slideshow"])
        # 1. participant-response row
        long_rows.append(dict(base, EventID="", RecallText=r["transcript"], CoderNotes="Participant response"))
        # 2. event rows
        ev_rows = [_event_row(base, ev) for ev in parsed["events"]]
        long_rows += ev_rows
        # 3. TOTAL row
        ev_df = pd.DataFrame(ev_rows)
        total = dict(base, EventID="TOTAL", RecallText="", CoderNotes="Participant totals")
        for _, prefix in CATEGORY_FIELDS.values():
            total[f"{prefix}_Count"] = int(ev_df[f"{prefix}_Count"].sum())
        total["DetailsRecalled_Count"] = int(ev_df["DetailsRecalled_Count"].sum())
        total["EventsRemembered_Total"] = int(ev_df["EventRemembered_0_1"].sum())
        notes = parsed.get("unmatched_recall") or []
        if notes or parsed.get("coder_notes"):
            total["CoderNotes"] = "Participant totals. " + (parsed.get("coder_notes") or "") + \
                                  (" Unmatched: " + " | ".join(notes) if notes else "")
        long_rows.append(total)

        n_events = len(ev_rows)
        remembered = total["EventsRemembered_Total"]
        srow = dict(ParticipantID=r["participant_id"], Session=r["session"], Cohort=r["cohort"],
                    Slideshow=r["slideshow"], TotalEvents=n_events, EventsRemembered=remembered,
                    EventsNotRemembered=n_events - remembered)
        for _, prefix in CATEGORY_FIELDS.values():
            srow[f"{prefix}_Total"] = total[f"{prefix}_Count"]
        srow["UniqueDetails_Total"] = total["DetailsRecalled_Count"]
        srow["UnmatchedRecall_Count"] = len(notes)
        srow["WordCount"] = r["word_count"]
        summary_rows.append(srow)

        stat_rows.append(dict(job_id=r["job_id"], participant_id=r["participant_id"], session=r["session"],
                              slideshow=r["slideshow"], cohort=r["cohort"], word_count=r["word_count"],
                              model=r["model"], prompt_version=r["prompt_version"], used_cache=r["used_cache"],
                              prompt_tokens=r["prompt_tokens"], cached_tokens=r["cached_tokens"],
                              output_tokens=r["output_tokens"], thinking_tokens=r["thinking_tokens"],
                              latency_s=r["latency_s"], attempts=r["attempts"], scored_at=r["scored_at"]))

    long_df = pd.DataFrame(long_rows).reindex(columns=SCORING_LONG_COLUMNS).fillna("")
    summary_df = pd.DataFrame(summary_rows).reindex(columns=SUMMARY_COLUMNS)
    if not summary_df.empty:
        # per-participant-session total rows, mirroring SESSION1_TOTAL
        num_cols = [c for c in SUMMARY_COLUMNS if c not in ("ParticipantID", "Session", "Cohort", "Slideshow")]
        totals = summary_df.groupby(["ParticipantID", "Session", "Cohort"], as_index=False)[num_cols].sum()
        totals["Slideshow"] = totals["Session"].map(lambda s: f"SESSION{s}_TOTAL")
        summary_df = pd.concat([summary_df, totals], ignore_index=True)
        order = {s: i for i, s in enumerate(config.SLIDESHOWS)}
        summary_df["_ord"] = summary_df["Slideshow"].map(lambda s: order.get(s, len(order)))  # totals last
        summary_df = summary_df.sort_values(["Session", "ParticipantID", "_ord"]).reset_index(drop=True)
        summary_df = summary_df.reindex(columns=SUMMARY_COLUMNS)
    stats_df = pd.DataFrame(stat_rows)
    return long_df, summary_df, stats_df


def export(store: Store, run_tag: str = config.RUN_TAG, out_dir: Path = config.OUTPUT_DIR,
           excel: bool = False, coder_id: str = CODER_ID_DEFAULT) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    long_df, summary_df, stats_df = build_frames(store, run_tag, coder_id)
    written = []
    for name, df in (("scoring_long", long_df), ("summary", summary_df), ("run_stats", stats_df)):
        p = out_dir / f"{run_tag}_{name}.csv"
        df.to_csv(p, index=False)
        written.append(p)
    if excel and not long_df.empty:
        for session, block in long_df.groupby("Session"):
            p = out_dir / f"{run_tag}_session{session}.xlsx"
            readme = pd.DataFrame({
                "Key": ["Run tag", "Session", "CoderID", "Model(s)", "Prompt version(s)", "Slideshows",
                        "Expected events", "Sheets"],
                "Value": [run_tag, session, coder_id,
                          ", ".join(sorted(stats_df["model"].unique())),
                          ", ".join(sorted(stats_df["prompt_version"].unique())),
                          ", ".join(config.SLIDESHOWS),
                          ", ".join(f"{k}={v}" for k, v in config.EXPECTED_EVENT_COUNTS.items()),
                          "Summary = one row per participant x slideshow plus SESSION_TOTAL; "
                          "Scoring_Long = participant-response row, event rows, TOTAL row per block"],
            })
            with pd.ExcelWriter(p, engine="openpyxl") as xw:
                readme.to_excel(xw, sheet_name=f"Session{session}_README", index=False)
                summary_df[summary_df["Session"] == session].to_excel(
                    xw, sheet_name=f"Session{session}_Summary", index=False)
                block.to_excel(xw, sheet_name=f"Session{session}_Scoring_Long", index=False)
            written.append(p)
    return written
