# EpiTranslator

**Live at [epitranslator.com](https://epitranslator.com).**

EpiTranslator helps disease modelers bring an existing model into the **WHO
Collaboratory pandemic simulator**. Paste or upload your model — written in
**any language** (R, Python, Julia, C++, Stan, …) — and it's rewritten into the
simulator's compartmental Python schema (`model.py`), streamed back for you to
review alongside a **translation report** that flags anything needing your eye.

It's a translation *aid*: it does the tedious first pass, but you review, adjust,
and own the result. There is no automated validation by design — the code is
shown raw for a modeler to check.

## Using it

At **[epitranslator.com](https://epitranslator.com)**:

1. **Paste or upload** your model on the left. If it spans several files, add
   them all (up to 10) — upload, drag-and-drop, or paste into named blocks; they
   are concatenated into one source. *Include* the model definition and the files
   holding parameter values / initial conditions; *skip* run scripts, plots, and
   tests; export binary data (`.rds`/`.mat`/`.npy`) to text first. (A contact
   matrix mainly conveys age structure — the schema uses built-in Prem 2021
   matrices, not pasted cell values.)
2. Optionally pick a **disease category** — a disambiguation hint only; it never
   overrides the source.
3. Press **Translate**. The `model.py` streams into the right pane with syntax
   highlighting.
4. Review the **translation report**: an attention banner (guessed parameters,
   dropped structure, a dynamics-free source) and an audit of every compartment,
   parameter, and intervention, each tagged with its provenance —
   `source` / `converted` / `derived` / `guessed`.
5. **Copy or download** the `model.py` and take it into the simulator.

The **Schema reference** button (top right) shows the exact target schema.

## The target framework

EpiTranslator translates *into* the WHO Collaboratory compartmental pandemic
simulator. Its documentation is authoritative for how a `model.py` must be
structured and what the schema can (and can't) express:

- **Repository** — [WHO-Collaboratory/pandemic-simulator-compartment](https://github.com/WHO-Collaboratory/pandemic-simulator-compartment)
- **Writing a model** — [docs/DEVELOPING_MODELS.md](https://github.com/WHO-Collaboratory/pandemic-simulator-compartment/blob/main/docs/DEVELOPING_MODELS.md)
- **Interventions** — [docs/INTERVENTIONS.md](https://github.com/WHO-Collaboratory/pandemic-simulator-compartment/blob/main/docs/INTERVENTIONS.md)
- **Contact matrices / age structure** — [docs/CONTACT_MATRICES.md](https://github.com/WHO-Collaboratory/pandemic-simulator-compartment/blob/main/docs/CONTACT_MATRICES.md)
- **The framework code** — the real `Model` base class and parameter schema live in
  [`compartment/model.py`](https://github.com/WHO-Collaboratory/pandemic-simulator-compartment/blob/main/compartment/model.py)
  and [`compartment/parameters.py`](https://github.com/WHO-Collaboratory/pandemic-simulator-compartment/blob/main/compartment/parameters.py).

A translation is only as good as the fit between your source and this schema.
When a model carries machinery the compartmental schema can't express (e.g. an
economic layer, agent-based rules, or bespoke intervention scheduling), the
report flags what was approximated or dropped — that is your cue to review
closely.

## Behind the curtain

The translation is driven by a prompt assembled from three shared,
externally-owned ingredients, kept close to what the simulator's authors
maintain (in `prompt_assets/`):

| Ingredient | File | What it is |
|---|---|---|
| Instructions | [`prompt_assets/system_prompt.md`](prompt_assets/system_prompt.md) | The translation instructions. |
| Target schema | [`prompt_assets/target_schema.py`](prompt_assets/target_schema.py) | An annotated reference of the framework's `Model`, `ParameterSchemaBuilder`, and `ValueType` — the same schema the app's **Schema reference** shows. |
| Worked examples | [`prompt_assets/examples/`](prompt_assets/examples) | Before/after pairs (`source.<ext>` + `target.py`) — the highest-leverage ingredient. |

Any change to those three shared ingredients is recorded in
[`docs/prompt-change-log.md`](docs/prompt-change-log.md) so it can be shared with
the prompt's authors and stay aligned with the upstream schema.

On top of that shared core, EpiTranslator adds a few pieces of its own so the
app works end-to-end:

| Addition | Where | What it does |
|---|---|---|
| Multi-file guidance | [`prompt_assets/multi_file_guidance.md`](prompt_assets/multi_file_guidance.md) | Appended to the instructions when you submit more than one file, telling the model how to reconcile several sources into a single `model.py`. |
| File headers | assembly code | When you submit several files, each is wrapped in a `=== file: <name> ===` header so the model can tell them apart. A single pasted source is passed through unchanged. |
| Disease-category hint | assembly code | If you pick a category, one line (`Disease category hint: …`) is added to the message — used only to disambiguate, never to override what the source says. |
| Report instructions | [`prompt_assets/output_report.md`](prompt_assets/output_report.md) | Drives a **separate, structured** model call that produces the translation report (origin / severity / category and the fidelity notes). |

So the app makes **two** model calls: one streams the bare `model.py`, and a
second, structured call — driven by `output_report.md` — produces the
translation report, so the report can never leak into the code. The shared
instructions + schema + examples are cached, so repeat translations only pay
for the source you paste.

---

*Self-hosting: the repo ships a `Dockerfile` bound to `$PORT` (runs on any
container host); the only required variable is `ANTHROPIC_API_KEY`.*
