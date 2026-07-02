# EpiTranslator

**Live at [epitranslator.com](https://epitranslator.com)** — paste a disease model in, get a pandemic-simulator `model.py` out.

EpiTranslator rewrites a disease model — written in **any language** (R, Python,
Julia, C++, Stan, …) — into the WHO pandemic-simulator's compartmental Python
schema. The translated `model.py` streams back for you to review, alongside a
**translation report** that flags anything needing a modeler's eye.

> Try it now at **[epitranslator.com](https://epitranslator.com)**.

## How to use

1. **Paste or upload** your model source on the left. If the model spans several
   files, add them all (up to 10) — **upload, drag-and-drop, or paste** into
   named blocks; they're concatenated into one source with `=== file: … ===`
   headers. *Include* the model definition and the files holding parameter
   values / initial conditions; *skip* run scripts, plots, and tests; export
   binary data (`.rds`/`.mat`/`.npy`) to text first. (A contact matrix mainly
   conveys age structure — the schema uses built-in Prem 2021 matrices, not
   pasted cell values.)
2. Optionally pick a **disease category** — a disambiguation hint only; it never
   overrides the source, and "Unspecified" adds no hint.
3. Press **Translate** (or ⌘/Ctrl + ↵). The `model.py` streams into the right
   pane with syntax highlighting and line numbers.
4. Review the **translation report** below the code: an attention banner
   (guessed parameters, dropped structure, or a dynamics-free source) and an
   expandable audit of every compartment, parameter, and intervention — each
   tagged with its provenance: `source`, `converted`, `derived`, or `guessed`.
   Collapse it to give the code more room.
5. **Copy or download** the `model.py`.

Your last source, category, and translation are kept in your browser
(`localStorage`) and restored on reload — no account, no server-side state. A
**Schema reference** button (top right) shows the exact target schema and lets
you download it.

There is no automated validation by design: the translated code is shown raw for
a modeler to review.

## How it works

```
┌────────────────────────────────────────────────────────────┐
│  FastAPI (backend/app.py)                                   │
│   GET  /              → serves the single-page UI           │
│   POST /api/translate → streams the translation (SSE), then │
│                         a second, structured call for the   │
│                         translation report                  │
│                                                              │
│  prompt (backend/prompt.py) assembles + caches:             │
│     instructions + TARGET SCHEMA + WORKED EXAMPLES          │
│     + multi-file guidance ── then your pasted source(s)     │
│     as the user turn.                                        │
└────────────────────────────────────────────────────────────┘
```

The report is a separate structured call, so it can never leak into the code
pane. The system prompt (instructions + schema + examples) is cached, so repeat
translations only pay for the source you paste.

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
prompt assets were loaded. Run the tests with `python -m pytest`.

## Configuration

All optional except the API key (see `.env.example`):

| Env var | Default | Purpose |
|---------|---------|---------|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic key. |
| `TRANSLATOR_MODEL` | `claude-opus-4-8` | The model — change this to try others. |
| `TRANSLATOR_EFFORT` | `high` | Reasoning effort: low/medium/high/xhigh/max. |
| `TRANSLATOR_THINKING` | `adaptive` | Set to `off` to disable adaptive thinking. |
| `TRANSLATOR_MAX_TOKENS` | `32000` | Max output tokens for the translated file. |
| `MAX_FILES` | `10` | Max files accepted per translation request. |
| `MAX_SOURCE_CHARS` | `600000` | Max total source characters per request. |
| `RATE_LIMIT_MAX` | `20` | Max requests per IP within the window. |
| `RATE_LIMIT_WINDOW` | `60` | Rate-limit window, in seconds. |

## Deploy to Railway

The repo ships a `Dockerfile`; Railway builds it directly.

1. Create a new Railway project from this repo.
2. Add a variable `ANTHROPIC_API_KEY` (and optionally `TRANSLATOR_MODEL`, etc.).
3. Deploy. Railway injects `$PORT`; the container binds to it automatically.

To try a different model in production, change the `TRANSLATOR_MODEL` variable
and redeploy — no code change.
