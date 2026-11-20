"""Turn stored results into the deliverables.

- `<run>_scoring_long.csv`  per (participant, session, slideshow): one
  participant-response row, one row per event (in the column layout from
  Mohsen's prompt, plus UnscoredRecall and ValidationFlags), one TOTAL row.
- `<run>_summary.csv`       one row per (participant, session, slideshow) plus
  a per-session total row, mirroring Session1_Summary.
- `<run>_run_stats.csv`     provider / tokens / cached tokens / latency /
  attempts / flags per job (for the parallelism write-up).
- `<run>_session{N}.xlsx`   optional workbook with README / Summary /
  Scoring_Long sheets per session, written as plain ranges (no table XML).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import config
from .db import Store
from .schema import CATEGORIES, ScoringResult

SCORING_LONG_COLUMNS = (
    ["Session", "CoderID", "ParticipantID", "Slideshow", "EventID", "RecallText"]
    + [f"{p}_{sfx}" for _, _, p in CATEGORIES for sfx in ("Recalled", "Count", "Evidence")]
    + ["UniqueDetailsRecalled", "DetailsRecalled_Count", "EventRemembered_0_1", "EventsRemembered_Total",
       "CoderNotes", "UnscoredRecall", "ValidationFlags"]
)
SUMMARY_COLUMNS = (
    ["ParticipantID", "Session", "Cohort", "Slideshow", "TotalEvents", "EventsRemembered", "EventsNotRemembered"]
    + [f"{p}_Total" for _, _, p in CATEGORIES]
    + ["UniqueDetails_Total", "UnscoredRecall_Count", "ValidationFlag_Count", "WordCount"]
)


def _label(text: str) -> str:
    """Semicolons separate details in the output, so keep them out of the labels."""
    return re.sub(r"\s+", " ", text.replace(";", ",")).strip()


def block_rows(r, result: ScoringResult, coder_id: str) -> tuple[list[dict], dict]:
    """Participant-response row, event rows, TOTAL row; plus the summary row."""
    base = {"Session": r["session"], "CoderID": coder_id, "ParticipantID": r["participant_id"],
            "Slideshow": r["slideshow"]}
    count_cols = [f"{p}_Count" for _, _, p in CATEGORIES] + ["DetailsRecalled_Count"]
    rows = [{**base, "RecallText": r["transcript"], "CoderNotes": "Participant response",
             "UnscoredRecall": " | ".join(f"[{u.reason}] {u.text} ({u.note})" for u in result.unscored),
             "ValidationFlags": r["flags"] or ""}]
    totals = dict.fromkeys(count_cols, 0)
    remembered = 0
    for ev in result.events:
        row = {**base, "EventID": ev.event_id.strip(), "CoderNotes": ev.coder_notes.strip()}
        for field_name, _, p in CATEGORIES:
            items = getattr(ev, field_name)
            row[f"{p}_Recalled"] = "; ".join(_label(i.detail) for i in items)
            row[f"{p}_Count"] = len(items)
            row[f"{p}_Evidence"] = " | ".join(i.evidence.strip() for i in items)
        unique = [_label(d) for d in ev.unique_details if d.strip()]
        row["UniqueDetailsRecalled"] = "; ".join(unique)
        row["DetailsRecalled_Count"] = len(unique)
        row["EventRemembered_0_1"] = int(bool(unique))
        remembered += row["EventRemembered_0_1"]
        for col in count_cols:
            totals[col] += row[col]
        rows.append(row)
    rows.append({**base, "EventID": "TOTAL", **totals, "EventsRemembered_Total": remembered,
                 "CoderNotes": "Participant totals"})

    n = len(result.events)
    summary = {"ParticipantID": r["participant_id"], "Session": r["session"], "Cohort": r["cohort"],
               "Slideshow": r["slideshow"], "TotalEvents": n, "EventsRemembered": remembered,
               "EventsNotRemembered": n - remembered,
               **{f"{p}_Total": totals[f"{p}_Count"] for _, _, p in CATEGORIES},
               "UniqueDetails_Total": totals["DetailsRecalled_Count"],
               "UnscoredRecall_Count": len(result.unscored),
               "ValidationFlag_Count": len([f for f in (r["flags"] or "").split(" | ") if f]),
               "WordCount": r["word_count"]}
    return rows, summary


def build_frames(store: Store, run_tag: str = config.RUN_TAG, coder_id: str | None = None):
    """Return (scoring_long, summary, run_stats) DataFrames."""
    long_rows, summary_rows, stat_rows = [], [], []
    for r in store.fetch_results(run_tag):
        result = ScoringResult.model_validate_json(r["raw_json"])
        rows, summary = block_rows(r, result, coder_id or r["model"])
        long_rows += rows
        summary_rows.append(summary)
        stat_rows.append({k: r[k] for k in ("job_id", "participant_id", "session", "slideshow", "cohort",
                                            "word_count", "provider", "model", "prompt_version", "used_cache",
                                            "prompt_tokens", "cached_tokens", "output_tokens", "thinking_tokens",
                                            "latency_s", "attempts", "scored_at")}
                         | {"flag_count": summary["ValidationFlag_Count"]})

    long_df = pd.DataFrame(long_rows).reindex(columns=SCORING_LONG_COLUMNS).fillna("")
    summary_df = pd.DataFrame(summary_rows).reindex(columns=SUMMARY_COLUMNS)
    if not summary_df.empty:
        num_cols = [c for c in SUMMARY_COLUMNS if c not in ("ParticipantID", "Session", "Cohort", "Slideshow")]
        totals = summary_df.groupby(["ParticipantID", "Session", "Cohort"], as_index=False)[num_cols].sum()
        totals["Slideshow"] = totals["Session"].map(lambda s: f"SESSION{s}_TOTAL")
        summary_df = pd.concat([summary_df, totals], ignore_index=True)
        order = {s: i for i, s in enumerate(config.SLIDESHOWS)}
        summary_df["_ord"] = summary_df["Slideshow"].map(lambda s: order.get(s, len(order)))  # totals last
        summary_df = summary_df.sort_values(["Session", "ParticipantID", "_ord"]).reset_index(drop=True)
        summary_df = summary_df.reindex(columns=SUMMARY_COLUMNS)
    return long_df, summary_df, pd.DataFrame(stat_rows)


def export(store: Store, run_tag: str = config.RUN_TAG, out_dir: Path = config.OUTPUT_DIR,
           excel: bool = False, coder_id: str | None = None) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    long_df, summary_df, stats_df = build_frames(store, run_tag, coder_id)
    written = []
    for name, df in (("scoring_long", long_df), ("summary", summary_df), ("run_stats", stats_df)):
        p = out_dir / f"{run_tag}_{name}.csv"
        df.to_csv(p, index=False, encoding="utf-8-sig")  # BOM so Excel opens it as UTF-8
        written.append(p)
    if excel and not long_df.empty:
        for session, block in long_df.groupby("Session"):
            p = out_dir / f"{run_tag}_session{session}.xlsx"
            readme = pd.DataFrame({
                "Key": ["Run tag", "Session", "Provider(s) / model(s)", "Prompt version(s)", "Slideshows",
                        "Expected events", "Sheets"],
                "Value": [run_tag, session,
                          ", ".join(sorted({f"{a}:{b}" for a, b in zip(stats_df["provider"], stats_df["model"])})),
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
