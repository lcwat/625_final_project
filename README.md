# EEG Recall AI API analysis pipeline
This where the storage for all of the files related to our 625 final project will reside. In this project, we apply parallelism to speed up a qualitative analysis pipeline where participant free memory recall responses are scored by an LLM. Right now, we have a minimal working example where we insert rows of participant free recall responses into a preset prompt and have an LLM score the response on recall accuracy via a standardized rubric. 

## Prerequisites
In order to get the minimal working example running on your machine, you must have a **Google AI Studio** account (free) and the unique **Gemini API key** they provide you after setting up that account. We use Gemini for our initial analysis working example because it is the only LLM API that provides a free tier for developers. 
1. Once you have your API key, you should paste the following in a **```.env```** file you create in the root of your cloned directory (this allows python to recognize your unique key as a local environmental variable):
- ```GEMINI_API_KEY=[Insert-your-API-key-here]```

3. You should also create your own virtual environment to run this python project. You can initialize a virtual environment from the command line with the following:
- ```python -m venv .venv```

4. Then, you should activate the virtual environment (varies by terminal, machine, etc.), I'll show how I do it through bash/Linux (also works for Unix/Mac terminal):
- ```source .venv/bin/activate```

5. Last, you can easily download all of the module dependencies by loading in the requirements.txt file:
- ```python -m pip install -r requirements.txt```

## Directories

- **```/scripts```** This is where the jupyter notebooks and python files will reside to run the bulk of the analysis that connects to and prompts the AI.
- **```/model_output```** This is where the final ```.csv``` output files will reside.

## Scoring pipeline (`scripts/recall_pipeline`)

The notebook above is the minimal example. The real pipeline lives in `scripts/recall_pipeline/` and is driven by `scripts/run_pipeline.py`. It scores every (participant, session, slideshow) free-recall transcript in `mohsen_files/Ao25_MasterFile_FreeRecall_MD.xlsx` against the matching event codebook in the `*_Rubric_Workbook.xlsx` files.

How it works:

- **One API call per transcript.** The model returns JSON that must match a Pydantic schema (`schema.py`): per event, the recalled details and verbatim evidence for each of the seven rubric categories, the de-duplicated unique details, and a remembered flag. Counts, TOTAL rows and summaries are computed in Python from those lists so they are always consistent.
- **The rubric is cached, not re-sent.** At the start of a run the scoring rules plus one slideshow's codebook are uploaded once as a Gemini context cache (`caching.py`), and every call references the cache handle. If a cache cannot be created the same text is sent inline, so results are identical either way.
- **A SQLite job queue** (`model_output/recall_scoring.sqlite`) tracks every job, so a run can be stopped and resumed, failed jobs can be retried, and several model/prompt configurations can live side by side under different `--run-tag`s.
- **Parallel workers** share a requests-per-minute limiter and exponential backoff on 429/5xx (`scorer.py`, `runner.py`).

Typical use (after the setup steps above):

```
python scripts/run_pipeline.py preview --participant 101 --session 1 --slideshow Summer   # see the exact prompt, no API call
python scripts/run_pipeline.py init                                                       # load all transcripts as jobs
python scripts/run_pipeline.py run --limit 5                                              # smoke test
python scripts/run_pipeline.py run --workers 8 --rpm 60                                   # full run (resumable)
python scripts/run_pipeline.py status
python scripts/run_pipeline.py export --excel                                             # CSVs + per-session .xlsx in model_output/
```

Useful environment variables (put them in `.env`): `GEMINI_MODEL`, `GEMINI_TEMPERATURE`, `GEMINI_THINKING_BUDGET`, `RECALL_WORKERS`, `RECALL_RPM`, `RECALL_RUN_TAG`.

Outputs in `model_output/`: `<run>_scoring_long.csv` (participant-response row, one row per event, TOTAL row per block, in the column layout from the scoring prompt), `<run>_summary.csv` (per participant x slideshow totals plus a session total), `<run>_run_stats.csv` (tokens, cached tokens, latency, attempts per job, for the parallelism write-up), and optionally `<run>_session{N}.xlsx`.
