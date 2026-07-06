# Prompt asset change log

A record of every change EpiTranslator makes to its **prompt assets**
(`prompt_assets/system_prompt.md` and `prompt_assets/target_schema.py`) relative
to the originals published in the Pandemic Simulator repo's documentation. It
exists so it is clear where these prompts differ from those originals, and why.
Each entry gives the exact before/after, the reason, and the evidence that
motivated it.

The prompt assets are the editable files that build the Claude system prompt:
`system_prompt.md` (instructions) + `target_schema.py` (the schema reference the
translated `model.py` must conform to) + the worked examples. See
[../backend/prompt.py](../backend/prompt.py) for how they are assembled.

---

## 2026-07-01

### Fix: infection edges wrongly mapped to `frequency_dependent=False`

#### Summary

Testing across a range of published disease models surfaced one genuine
**correctness bug** (as opposed to a documented simplification): a plain SIR
model whose infection term is `β·S·I` was translated with the S→I transmission
edge set to `frequency_dependent=False`. In the target schema that flag means
the flow is `rate * source` = `β·S` — **with no dependence on the number of
infectives**. The result is not an SIR model at all: susceptibles convert to
infected spontaneously, the "epidemic" runs even when there are zero infectives,
and the attack rate goes to 100%.

The output was syntactically valid, ran, and produced a plausible-looking
epidemic curve, so a modeler would not catch it without knowing the schema's
flag semantics in detail. This is why it was worth a prompt fix.

**Root cause: a terminology collision, reinforced by the prompt itself.**
In epidemiology, `β·S·I` (no `/N`) is classic **"mass-action" / density-dependent**
transmission. But the schema uses the label "mass action" for its
`frequency_dependent=False` form, which is `β·S` (a per-capita flow, no `I`).
The original prompt's mapping guidance explicitly told the model to distinguish
*"frequency-dependent (`β S I / N`) vs mass-action (`β S I`); set
`frequency_dependent` accordingly"* — which directly maps `β·S·I` → `False`.
The schema has **no** `β·S·I` density-dependent edge form; the correct target is
`frequency_dependent=True` (`β·S·I/N`), which equals `β·S·I` when the population
is normalized to N=1 (as it is in most textbook/example code).

Evidence that this is a systematic, not one-off, error: in the same test the
near-identical **sir-julia** SIR — which wrote the force of infection *with* an
explicit `/N` (`β·c·I/N·S`) — was correctly set to `frequency_dependent=True`.
Two nearly identical trivial models got opposite (one wrong) treatment, decided
only by whether the source happened to write `/N`. Any source written in
proportions (`β·S·I`, populations summing to 1) is at risk — a very common style.

Numerical impact (β=0.1, γ=0.05, I₀=0.01):

| Version | Peak infectious | Peak time | Final attack rate |
|---|---|---|---|
| Correct (`β·S·I/N`) | 0.158 | t≈88 | 0.777 |
| Buggy (`β·S`)       | 0.500 | t≈14 | 1.000 |
| Correct, **I₀=0**   | 0.000 | —    | 0.000 (no epidemic — correct) |
| Buggy, **I₀=0**     | 0.500 | t≈14 | 1.000 (epidemic with zero infectives — impossible) |

#### Changes to `prompt_assets/system_prompt.md`

**1. Mapping guidance (the direct cause).**

Before:
```
- Preserve whether transmission is frequency-dependent (`β S I / N`) vs
  mass-action (`β S I`); set `frequency_dependent` accordingly.
```
After:
```
- Infection edges must couple to infectives. The schema offers only two
  edge forms: frequency_dependent=False gives `rate * source` (NO dependence
  on infectives), and frequency_dependent=True gives
  `source * rate * sum(infective) / N`. There is no plain `β S I`
  (density-dependent) edge form. So any susceptible→exposed/infected infection
  edge must use frequency_dependent=True — including when the source writes
  `β S I` without a `/N` (normalized population, N=1). Use
  frequency_dependent=False only for progression/recovery flows (E→I, I→R). If
  transmission is truly density-dependent (`β S I` with N not held constant),
  compute the force of infection manually via `skip_edges` + `_apply_flow`.
```

**2. Authoring recipe, step 3** — removed the misleading "(mass action)" label
for the `rate * source` form and stated that infection edges must set
`frequency_dependent=True`.

**3. Critical rules and pitfalls** — added a dedicated bullet warning that a
`False` infection edge silently drops the `I` term (ranking it alongside the
existing rate-vs-period `value_type` inversion warning as an easy silent error).

#### Change to `prompt_assets/target_schema.py`

**4. `add_transmission_edge` docstring** — the reference comment previously read
*"`rate * source` (mass action) or, with frequency_dependent=True, …"*. The
"(mass action)" label was the collision at its source. Rewrote it to describe
`False` as "a plain per-capita flow with NO dependence on infectives (use for
progression/recovery)" and `True` as "the infection form", and added an explicit
note that a normalized `β·S·I` with N=1 is the `frequency_dependent=True` case.

#### Verification

Re-ran the failing case (epicookbook SIR) plus two regression cases after the
edits:

- **epicookbook SIR** — the S→I edge now emits `frequency_dependent=True` on
  both of two independent re-runs (was `False`). The output also now carries a
  correct explanatory comment it generated on its own: *"Source writes b·S·I
  with a normalized population (N=1), so b·S·I == b·S·I/N — the
  frequency-dependent form."* The `derivative()` applies the edge once via
  `_compute_derivatives` (no double-application). **Bug fixed, consistent.**
- **sir-julia** (regression) — still correct: `frequency_dependent=True` with
  the contact rate `c` split out via `skip_edges` + `_apply_flow`. No regression.
- **SIWR cholera** (regression) — still correct: infection computed manually via
  `_apply_flow` for both the direct and waterborne routes. No regression.

All four re-runs compile. Verified 2026-07-01.

#### Notes

- The bug was purely in the *guidance*, not the framework — the schema itself is
  fine; it just lacked a density-dependent edge and its docstring mislabeled the
  linear form as "mass action."
- Consider whether the framework should offer a true density-dependent
  (`β·S·I`) edge form, or emit a warning when an edge's source looks like a
  susceptible compartment and its target is infective-flagged but
  `frequency_dependent=False` — that would catch this class at the framework
  level rather than relying on prompt wording.
- All other models in the test either translated faithfully or were simplified
  with visible `# NOTE:` comments; this was the only silently-wrong output among
  genuinely compartmental sources.

### Output-report addendum (translation-report feature)

**Implementation note:** `backend/prompt.py`'s `build_user_message()` was also 
softened to remove the "Output **only** the bare translated Python code" 
constraint (changed to "Output the bare translated Python code, then the 
translation-report addendum described in the instructions") to avoid suppressing 
the report addendum when the model considers both the system prompt and the user 
message. Part of the "honest-parameter /
dynamics-free handling" feature: a two-tier UI (an attention banner + an
expandable panel auditing every parameter translation).

#### Change to `prompt_assets/system_prompt.md` ("What you output" section)

Before:
```
Output **only** the complete contents of `model.py` — bare Python source,
ready to save. No prose, no explanation, no markdown code fences. (The
```

After:
```
Output the complete contents of `model.py` — bare Python source, ready to
save — then the translation-report addendum described at the end of this
prompt (after a sentinel line). No prose or explanation around the code, and
no markdown code fences around it. (The
```

New file `prompt_assets/output_report.md` added and appended by `build_system_prompt()`.

Two prompt-asset changes, following the project's prompt-stability rule of
**preferring a new appended file over editing the existing prompt**:

1. **New file `prompt_assets/output_report.md`** — appended to the system prompt
   as its final section by `build_system_prompt()`. Instructs the model to emit,
   after the bare `model.py`, a sentinel line `# ---TRANSLATION-REPORT---`
   followed by a single JSON object reporting: (a) **every** declared element —
   compartments, parameters/edge rates, and interventions — each with its
   provenance `origin` ∈ {`source`, `converted`, `derived`, `guessed`} (each kind
   uses the applicable subset) — and (b) `attention` items with `severity` ∈
   {`high`, `info`} and `category` ∈ {`no_dynamics`, `invented`,
   `dropped_structure`, `model_mismatch`, `ambiguity`}. Additive; does not touch
   the existing prompt files.

2. **One-line edit to `system_prompt.md`** ("What you output" section) — soften
   *"Output **only** the complete contents of `model.py`…"* to acknowledge the
   output addendum, so the new report instruction does not contradict it. This is
   the minimal edit needed to resolve the contradiction; rationale is the report
   feature. (Chosen over leaving it untouched because a direct contradiction
   risks the model dropping the report.)

#### Verification (2026-07-01)

Live end-to-end confirmed the model emits a valid report and the code stays clean
(no sentinel leak, code compiles) on three sources:
- **epicookbook SIR** — 3 compartments + 2 parameters, all `origin: source`.
- **`mpox_run.R` (dynamics-free wrapper)** — a `high`/`no_dynamics` attention item
  ("Source contained no model dynamics") with all compartments/most parameters
  flagged `guessed` — the intended honest handling of a wrong-file paste.
- **`wuhan_seir.R`** — parameter provenance `derived` (β from R₀) and `converted`
  (unit transforms), plus dropped-age-structure attention items.
Graceful degradation confirmed: with `output_report.md` removed, no report event is
emitted and the app shows code only, without error.

#### Follow-up hardening (2026-07-01)

Live browser testing showed the model sometimes ignored the exact format and wrote
the report as a **paraphrased comment block** (`# ===TRANSLATION REPORT===` with
`# -` bullet prose) instead of the sentinel + raw JSON — which then leaked into the
code pane. Hardening, so the report can never appear as code:

- **`prompt_assets/output_report.md` strengthened** (prompt change): emphasizes the
  sentinel must be copied verbatim (not paraphrased, no `=`), that everything after
  it is **raw JSON only** (starts `{`, ends `}`), and an explicit "do NOT write the
  report as Python comments / do NOT prefix lines with `#` / do NOT use code fences"
  list, including a "if you catch yourself writing `# - …` bullets, STOP" note.
- **`backend/report.py` (code, not prompt):** the sentinel matcher is now a tolerant
  regex (accepts paraphrased dividers) so a non-canonical divider is still stripped
  out of the code; and `parse_report` falls back to the outermost `{…}` span so a
  stray prefix/fence around valid JSON still parses.
- **UI:** the report moved to a full-width drawer below both panes (code pane holds
  only code).

### Re-architecture: translation report via a separate structured call

Replaces the in-stream "sentinel + JSON after
the code" approach (the two entries above) — that proved unreliable: the model
would sometimes paraphrase the sentinel and write the report as `#` comment prose,
which then leaked into the code pane (observed twice in the browser). Prompt
wording could not make single-call emission reliable.

**New design — two calls:**

1. **Code call** — unchanged from the original: produces **only** the bare
   `model.py`. The report instructions were removed from this call entirely, so
   the code output can never contain a report by construction. Reverts:
   - `prompt_assets/system_prompt.md` "What you output" restored to the original
     *"Output **only** the complete contents of `model.py`…"* (undoes the earlier
     softening).
   - `backend/prompt.py` `build_system_prompt()` no longer appends the report
     file; `build_user_message()` restored to *"Output only the bare translated
     Python code."*
2. **Report call** (new, `backend/translator.py::generate_report`) — a second
   call that reads the source + generated `model.py` and returns the report as a
   JSON object via **structured outputs** (`output_config.format` with a
   `json_schema`). The schema guarantees a valid object matching the report shape
   (attention / compartments / parameters / interventions with `origin`
   provenance); the model cannot emit prose or leak into code. Runs at low effort
   on a configurable model (`TRANSLATOR_REPORT_MODEL`, default = translation model).

**Prompt-asset change:** `prompt_assets/output_report.md` was rewritten from
"emit a sentinel + JSON after the code" formatting rules into **classification
instructions** for the report call (what `origin`/`severity`/`category` mean, what
to include). It is no longer part of the system prompt; it is the report call's
system prompt (`build_report_system_prompt()`).

**Removed:** `backend/report.py` (sentinel splitter + tolerant regex) and its
tests — obsolete now that code and report come from separate calls.

**Verified 2026-07-01 (live):** epicookbook SIR and `mpox_run.R` (wrong-file) both
produce a valid report with **zero report text in the code pane** (structurally
impossible), code compiles; `mpox_run` correctly flags `high`/`no_dynamics`.

### New appended file: multi-file input guidance

Part of the multi-file input feature.

**No edits to existing prompt files.** Following the project's prompt-stability
rule, this is a **new appended prompt-asset file only**.

#### New file `prompt_assets/multi_file_guidance.md`

Appended to the system prompt as its final section by `build_system_prompt()`
(after the worked examples). It tells the model, **when the source is supplied
as several files** (each under a `=== file: ... ===` header), to:

- treat the files as one model, with the dynamics file authoritative for
  structure;
- take numeric values from parameter/data files instead of guessing defaults;
- not invent structure from a dynamics-free run wrapper / entry-point / config;
- read a contact matrix as *age/group structure* (→ `add_demographic_group`),
  not transcribe its cell values (the schema uses built-in Prem 2021 matrices,
  with `set_contact_override` for specific deviations).

**Purpose / rationale:** testing across different disease models found that
parameters often live in separate files, so a single paste has structure but no
numbers and the tool fills plausible defaults. Multi-file input lets the
modeler supply those files; this guidance steers the model to use the supplied
numbers and to keep the contact-matrix expectation honest. Phrased conditionally
("when several files are provided…") so it is a harmless no-op for single-file
pastes and the cached system prompt stays stable.

**Wiring (assembly code, not prompt content):** `_MULTI_FILE_FILE` appended in
`build_system_prompt()`; `assets_status()` gains `multi_file_guidance_present`.
