# Design — Translation report (honest-parameter / dynamics-free handling)

**Date:** 2026-07-01. **Status:** approved design, pending implementation plan.

## Problem

The translator emits a bare `model.py`. When a source lacks numeric parameters
(they live in separate config/binary files) or lacks dynamics entirely (a
user pastes a run-wrapper, not the model), the tool silently fills plausible
values and produces confident-looking output with no signal to the user about
what was invented, converted, or dropped. The 14-model test
([../../translation-test-results.md](../../translation-test-results.md)) showed
this is common and, in the wrong-file case, produced a fully fabricated model.

## Goal

Surface, after each translation, **(1)** anything that needs the user's
attention (invented parameters, dropped structure, dynamics-free/wrong-file,
ambiguities) and **(2)** an expandable audit of **every** parameter translation
with its provenance — without changing the copyable `model.py` deliverable.

Non-goals: validation/execution of the model, faithfulness scoring, or any
second model call. This is a surfacing layer over the existing single call.

## UX — two tiers

Both live in the right (output) pane; the `<pre>` still holds only the code.

- **Tier 1 — attention banner** (between the pane header and the code). Renders
  `attention[]`, severity-colored (`high` = accent, `info` = muted); each item
  shows a `title` with expandable `detail`. Hidden when empty. A `no_dynamics`
  item gets top placement and distinct "inferred, not translated" treatment.
- **Tier 2 — translation audit** (collapsible bar at the bottom of the pane,
  *"Translation audit (N)"*). Expands into a table covering **every declared
  element** — compartments, parameters/edge rates, and interventions — grouped
  by kind. Each row shows its `source → schema` mapping, the relevant fields
  (value/unit for parameters; `target_rates` for interventions), an **origin
  badge** (`guessed` highlighted; `converted`/`derived` subtle; `source` plain),
  and a `note`.

The banner is the "you should look at this" filter; the panel is the complete
audit trail across compartments, parameters, and interventions. Invented/dropped
items appear in both.

## Data model — the translation report

After the bare `model.py`, the model emits a sentinel line and one JSON object:

```
# ---TRANSLATION-REPORT---
{ "attention": [...], "compartments": [...], "parameters": [...], "interventions": [...] }
```

The audit covers three element kinds. They share the same `origin` vocabulary
(each uses the applicable subset):
**source** = taken directly from the source; **converted** = same quantity,
unit-transformed (rate↔period, %↔fraction); **derived** = computed/restructured
from the source (e.g. β from R₀, or a compartment split for competing risks);
**guessed** = not in the source, invented as a plausible default.
`source_name` is `null` when the element has no counterpart in the source.

**`compartments[]`** — one row per compartment:

```json
{
  "schema_id": "H_crit",
  "source_name": "critical",
  "origin": "source | derived | guessed",
  "note": "split from 'severe' for the competing-risk recovery/critical branch"
}
```

**`parameters[]`** — one row per declared parameter/edge rate:

```json
{
  "schema_name": "beta",
  "source_name": "b",
  "value": 0.1,
  "unit": "per day",
  "origin": "source | converted | derived | guessed",
  "note": "inverted from a 10-day infectious period"
}
```

**`interventions[]`** — one row per declared intervention:

```json
{
  "schema_id": "social_distancing",
  "source_name": null,
  "target_rates": ["beta"],
  "origin": "source | guessed",
  "note": "not in source; added as a typical control measure"
}
```

**`attention[]`** — banner items, model-authored, severity-ranked:

```json
{
  "severity": "high | info",
  "category": "no_dynamics | invented | dropped_structure | model_mismatch | ambiguity",
  "title": "3 parameters were guessed (not in the source)",
  "detail": "beta, sigma, mu use typical values; verify before use."
}
```

`high` = could be wrong / needs a human decision. `info` = a faithful
simplification worth knowing. `no_dynamics` is the wrong-file/entry-point case
and is always `high`. `invented` covers any guessed element — parameter,
compartment, or intervention (generalized from the earlier `guessed_param`, now
that the audit spans all three kinds).

The block is always emitted (compartments/parameters are never empty for a real
model); `attention` may be `[]`.

## Components and changes

### 1. Prompt — new appended file (per the CLAUDE.md prompt-stability rule)

- **New `prompt_assets/output_report.md`** — the full report instruction: emit
  the bare `model.py`, then the sentinel, then the JSON object; defines the
  `origin`/`attention` vocabulary; requires **every** declared element
  (compartment, parameter/edge rate, intervention) be listed; includes one short
  worked example of the JSON. This is additive and does not modify the existing
  prompt files.
- **One-line edit to `prompt_assets/system_prompt.md`** ("What you output") —
  soften *"Output **only** the complete contents of `model.py`…"* to acknowledge
  the addendum, resolving the contradiction. Logged in
  [../../prompt-change-log.md](../../prompt-change-log.md).

### 2. Prompt assembly — `backend/prompt.py`

- `build_system_prompt()` reads `output_report.md` and appends it as the **final**
  section (after instructions + schema + examples), so it is the last word on
  output format. One read + one append; mirrors how the schema section is added.

### 3. Server / streaming — `backend/app.py`

- In `event_stream`, split the streamed text on the sentinel line
  `# ---TRANSLATION-REPORT---`: text **before** streams to the client as `{text}`
  events exactly as today; text **after** is buffered, parsed as JSON at end of
  stream, and emitted as a single new `{report: {...}}` event immediately before
  `{done}`.
- **Graceful degradation:** if no sentinel appears, or the trailing text is not
  valid JSON, stream everything as `{text}` and emit no report event. The UI is
  then identical to today's. The feature can never break a translation.
- The sentinel-split composes with the existing `_strip_code_fences` in
  `translator.py`; the model is instructed to emit no code fences, and the
  trailing content is JSON (not a closing fence), so fence-stripping is
  unaffected.

### 4. UI — `static/index.html`

- Consume the new `{report}` SSE event; render the Tier 1 banner and Tier 2
  panel from it. Reset both on each new translation. Hide both when no report /
  empty.
- **Copy** continues to copy only `<pre>` (code). The report lives in separate
  DOM, so the deliverable is unchanged.

## Wiring checklist (every new symbol has a reader)

| Introduced | Wired in |
|---|---|
| `prompt_assets/output_report.md` | read + appended by `build_system_prompt()` in `backend/prompt.py` |
| `system_prompt.md` "output" line edit | logged in `docs/prompt-change-log.md` |
| Sentinel-split + `{report}` event | produced in `backend/app.py` `event_stream`; consumed in `static/index.html` |
| Banner + panel DOM | rendered in `static/index.html` from the `{report}` event |
| (optional) `assets_status()` includes `output_report_present` | shown by `/api/health`; surfaced in the header meta if useful |

## Testing

- **Prompt/report emission:** re-run a handful of the saved test sources
  (epicookbook SIR → expect `guessed`/`info` items and a full audit of
  compartments + parameters + interventions;
  `mpox_run.R` → expect a `no_dynamics` high-severity item; Wuhan → expect
  `derived` β from R₀). Assert the sentinel appears and the JSON parses.
- **Graceful degradation:** feed a stubbed stream with no sentinel and with
  malformed JSON; assert the code still renders and no report event is emitted.
- **Server split:** unit-test the sentinel-split generator on chunk boundaries
  (sentinel split across two chunks; sentinel absent; JSON after sentinel).
- **UI:** manual check that the banner and panel render, expand/collapse, and
  that Copy still yields only the code.

## Rollout

Feature is self-contained and backward-compatible: if `output_report.md` is
absent or the model omits the report, behavior is exactly today's. No config
flag needed.

## Docs to update at the end

- Finalize the "Planned" entry in `docs/prompt-change-log.md` with the actual
  before/after and verification.
- Note the feature in `docs/ROADMAP.md` (it delivers part of item #4/#10's
  intent — surfacing what needs attention) and in `README.md` (the output pane
  now includes an attention banner + parameter audit).
