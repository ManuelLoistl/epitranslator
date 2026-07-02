# EpiTranslator

A lightweight tool: paste a disease model's source code in, and Claude translates
it into a well-defined Python target schema. The bare translated code is streamed
back for you to review.

Link to a disease model in → schema-adjusted model out.

## How it works

```
┌──────────────────────────────────────────────────────┐
│  FastAPI (backend/app.py)                             │
│   GET  /              → serves the single-page UI     │
│   POST /api/translate → streams the translation (SSE) │
│                                                        │
│  prompt (backend/prompt.py) assembles:                │
│     instructions + TARGET SCHEMA + WORKED EXAMPLES    │
│     (cached) ── then your pasted source as the user   │
│     turn ── one streaming Claude call.                │
└──────────────────────────────────────────────────────┘
```

There is no automated validation by design — the translated code is shown raw
for a modeler to review.

A model that spans several files can be submitted as a **set** — upload files or
paste into named blocks (up to 10). They're concatenated with
`=== file: <name> (<Lang>) ===` headers into one source and translated into a
single `model.py`. A single unnamed paste behaves exactly as before. Include the
model definition and the files holding parameter values / initial conditions;
skip run scripts, plots, and tests; export binary data (`.rds`/`.mat`/`.npy`) to
text first. (A contact matrix mainly conveys age structure — the schema uses
built-in Prem 2021 matrices, not pasted cell values.)

The source pane has an optional **disease-category** picker (by transmission
route — respiratory, vector-borne, waterborne, …). The choice feeds a
disambiguation hint into the translation; it never overrides the source, and
"Unspecified" adds no hint.

Alongside the code, the output pane shows a **translation report**: an attention
banner (things to review — guessed parameters, dropped structure, or a
dynamics-free source) and an expandable audit of every compartment, parameter,
and intervention with its provenance (`source` / `converted` / `derived` /
`guessed`). The model appends this report after the code; if it is absent the
pane simply shows the code, unchanged.

The output can be **copied or downloaded** as `model.py`. A **Schema reference**
button (top right) opens the target schema in a viewer (also downloadable),
served from the same file that feeds the prompt. Your last source, category,
language, and translation are **kept in the browser** (`localStorage`) and
restored on reload — no account, no server state.

## Your materials live in `prompt_assets/`

Drop your real prompt, schema, and examples into these files — no Python edits
needed:

| File | What goes here |
|------|----------------|
| `prompt_assets/system_prompt.md` | The translation instructions (your prompt). |
| `prompt_assets/target_schema.py` | The Python target schema the output must conform to. |
| `prompt_assets/examples/<name>/` | Before/after pairs: `source.<ext>` + `target.py`. |

The worked examples are the highest-leverage ingredient — one complete, correct
before/after pair teaches the model more than paragraphs of instructions.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn backend.app:app --reload --port 8000
```

Open http://localhost:8000. `GET /api/health` shows the active model and which
prompt assets were loaded.

## Configuration

All optional except the API key (see `.env.example`):

| Env var | Default | Purpose |
|---------|---------|---------|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic key. |
| `TRANSLATOR_MODEL` | `claude-opus-4-8` | The model — change this to try others. |
| `TRANSLATOR_EFFORT` | `high` | Reasoning effort: low/medium/high/xhigh/max. |
| `TRANSLATOR_THINKING` | `adaptive` | Set to `off` to disable adaptive thinking. |
| `TRANSLATOR_MAX_TOKENS` | `32000` | Max output tokens for the translated file. |

## Deploy to Railway

The repo ships a `Dockerfile`; Railway builds it directly.

1. Create a new Railway project from this repo.
2. Add a variable `ANTHROPIC_API_KEY` (and optionally `TRANSLATOR_MODEL`, etc.).
3. Deploy. Railway injects `$PORT`; the container binds to it automatically.

To try a different model in production, change the `TRANSLATOR_MODEL` variable
and redeploy — no code change.
