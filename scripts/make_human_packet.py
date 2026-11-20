"""Build a human-scoring packet: verbatim transcripts plus the event codebook,
with none of the model instructions. For comparing a human coder against the
model's scores.

    python scripts/make_human_packet.py --session 1 --slideshow Summer --participants 101 102 103

Writes to model_output/human_scoring/:
    S<session>_<slideshow>_<ids>.md    readable: transcripts, then the codebook
    S<session>_<slideshow>_<ids>.xlsx  fillable: Codebook sheet + one blank
                                       scoring sheet per participant in the
                                       same column layout the model output uses
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recall_pipeline import config  # noqa: E402
from recall_pipeline.data import load_transcripts  # noqa: E402
from recall_pipeline.export import SCORING_LONG_COLUMNS  # noqa: E402
from recall_pipeline.rubric import load_codebook  # noqa: E402
from recall_pipeline.schema import CATEGORIES  # noqa: E402

RUBRIC_FIELDS = [col for _, col, _ in CATEGORIES] + ["AllowedSynonyms"]


def codebook_markdown(cb) -> str:
    out = [f"## {cb.slideshow} event codebook ({len(cb.events)} events)", "",
           "Score against the seven fields below. EventTitle is for orientation only. "
           "AllowedSynonyms is equivalence guidance, not its own category.", ""]
    for e in cb.events:
        out.append(f"### Event {e['EventID']}: {e['EventTitle']}")
        out.append("")
        for f in RUBRIC_FIELDS:
            out.append(f"- **{f}:** {e[f] or '(blank)'}")
        out.append("")
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--session", type=int, default=1)
    p.add_argument("--slideshow", required=True, choices=config.SLIDESHOWS)
    p.add_argument("--participants", type=int, nargs="+", required=True)
    p.add_argument("--out-dir", default=str(config.OUTPUT_DIR / "human_scoring"))
    args = p.parse_args()

    cb = load_codebook(args.slideshow)
    ts = {t.participant_id: t for t in load_transcripts([args.session], [args.slideshow], args.participants)}
    missing = [pid for pid in args.participants if pid not in ts]
    if missing:
        sys.exit(f"no transcript for participants {missing} in session {args.session} {args.slideshow}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = "-".join(str(i) for i in args.participants)
    stem = f"S{args.session}_{args.slideshow}_{ids}"

    # ---- markdown -----------------------------------------------------
    md = [f"# Human scoring packet: Session {args.session}, {args.slideshow}", "",
          f"Participants: {', '.join(map(str, args.participants))}. Transcripts are verbatim from the master file. "
          f"Score each at the event level against the codebook at the end.", ""]
    for pid in args.participants:
        t = ts[pid]
        md += [f"## Participant {pid} ({t.cohort} adult), Session {t.session}, {t.slideshow} "
               f"({len(t.text.split())} words)", "", t.text, ""]
    md.append(codebook_markdown(cb))
    md_path = out_dir / f"{stem}.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    # ---- excel --------------------------------------------------------
    xlsx_path = out_dir / f"{stem}.xlsx"
    cb_df = pd.DataFrame(cb.events)[["EventID", "EventTitle"] + RUBRIC_FIELDS]
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        cb_df.to_excel(xw, sheet_name=f"{args.slideshow}_Codebook", index=False)
        for pid in args.participants:
            t = ts[pid]
            base = {"Session": t.session, "CoderID": "", "ParticipantID": pid, "Slideshow": t.slideshow}
            rows = [{**base, "EventID": "", "RecallText": t.text, "CoderNotes": "Participant response"}]
            rows += [{**base, "EventID": e["EventID"]} for e in cb.events]
            rows.append({**base, "EventID": "TOTAL", "CoderNotes": "Participant totals"})
            pd.DataFrame(rows).reindex(columns=SCORING_LONG_COLUMNS).astype(object).fillna("").to_excel(
                xw, sheet_name=f"P{pid}_Scoring", index=False)
        for ws in xw.book.worksheets:  # readable column widths, wrapped text
            from openpyxl.styles import Alignment
            for col in ws.columns:
                letter = col[0].column_letter
                ws.column_dimensions[letter].width = 60 if letter in ("B", "F") or ws.title.endswith("Codebook") else 22
                for cell in col:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
            ws.freeze_panes = "A2"

    print("wrote", md_path)
    print("wrote", xlsx_path)


if __name__ == "__main__":
    main()
