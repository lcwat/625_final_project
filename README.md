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
- On Windows PowerShell instead: ```Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned; .\.venv\Scripts\Activate.ps1```

5. Last, you can easily download all of the module dependencies by loading in the requirements.txt file:
- ```python -m pip install -r requirements.txt```

## Directories

- **```/scripts```** This is where the jupyter notebooks and python files will reside to run the bulk of the analysis that connects to and prompts the AI.
- **```/prompts```** This is where the scoring rules sent to the model as its instructions reside.
- **```/model_output```** This is where the final ```.csv``` output files will reside.

## Scoring the real transcripts (`scripts/recall_pipeline`)

`scripts/run_pipeline.py` scores the transcripts in `mohsen_files` against the event codebooks, one participant and slideshow per model call, serially or in parallel. Run it from the root of the repository.

How it works:

- **The model only makes the judgment calls.** Its instructions are Mohsen's scoring rules (`prompts/scoring_rules.md`, copied from the PDF) followed by one slideshow's event codebook. It returns JSON matching a strict schema (`schema.py`): per event, the recalled details with a verbatim quote for each of the seven rubric categories, the de-duplicated unique details, and notes. Counts, the remembered flag, TOTAL rows and summaries are computed in Python so they are always consistent.
- **Every quote is checked against the transcript.** Responses with the wrong set of events are retried; quotes that are not in the transcript and other oddities are kept but flagged in a `ValidationFlags` column for a human look.
- **The rubric is sent once, not every call.** The rules + codebook are identical for every transcript of a slideshow. On Azure OpenAI that prefix is cached automatically (usage shows `cached_tokens`); on Gemini it is uploaded once as a context cache and referenced by handle.
- **Three providers, one scorer.** `--provider azure` (Azure OpenAI), `--provider openai` (a plain platform.openai.com key) or `--provider gemini` (Google AI Studio). The provider is auto-detected from which key is in `.env`, in that order.
- **A SQLite job queue** (`model_output/recall_scoring.sqlite`, gitignored) tracks every job, so a run can be stopped and resumed, failed jobs retried, and several provider/model/prompt configurations kept side by side under different `--run-tag`s.
- **Parallel workers** share a requests-per-minute limiter and exponential backoff that honours `Retry-After`. `--workers 1` is the serial baseline for the write-up.

`.env` for Azure OpenAI:

```
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://<resource>.services.ai.azure.com/openai/v1/responses   # as shown on the deployment's Details tab
AZURE_OPENAI_DEPLOYMENT=gpt-5            # deployment name
AZURE_OPENAI_API_VERSION=2025-04-01-preview   # only used with the classic https://<resource>.openai.azure.com endpoint form
AZURE_OPENAI_REASONING_EFFORT=medium     # gpt-5 / o-series only; leave temperature unset for those
```

`.env` for a plain OpenAI key (e.g. a lab account on platform.openai.com):

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5                       # any model that supports structured outputs
OPENAI_REASONING_EFFORT=medium           # gpt-5 / o-series only; leave temperature unset for those
```

`.env` for Gemini: `GEMINI_API_KEY=...` and optionally `GEMINI_MODEL`, `GEMINI_TEMPERATURE`, `GEMINI_THINKING_BUDGET`.

Typical use:

```
python scripts/run_pipeline.py preview --participant 101 --session 1 --slideshow Summer   # see the exact prompt, no API call
python scripts/run_pipeline.py init                                                       # load all transcripts as jobs (or --sessions 1)
python scripts/run_pipeline.py run --limit 3                                              # smoke test
python scripts/run_pipeline.py run --workers 1  --run-tag serial                          # serial baseline
python scripts/run_pipeline.py run --workers 8  --run-tag parallel --rpm 60               # parallel run (resumable)
python scripts/run_pipeline.py status
python scripts/run_pipeline.py export --excel                                             # CSVs + per-session .xlsx in model_output/
```

Other knobs via `.env`: `RECALL_WORKERS`, `RECALL_RPM`, `RECALL_RUN_TAG`, `RECALL_MAX_OUTPUT_TOKENS`.

Outputs in `model_output/`: `<run>_scoring_long.csv` (per participant x slideshow: a participant-response row, one row per event in the column layout from the scoring prompt, a TOTAL row), `<run>_summary.csv` (totals per participant x slideshow plus a session total), `<run>_run_stats.csv` (provider, tokens, cached tokens, latency, attempts, flags per job, for the parallelism write-up), and optionally `<run>_session{N}.xlsx`.
