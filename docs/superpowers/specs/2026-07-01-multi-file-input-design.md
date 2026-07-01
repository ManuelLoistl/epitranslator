# Multi-file input — design

**Date:** 2026-07-01
**Roadmap item:** #2 (Multiple input files → single consolidated output).
**Status:** design, pending review.

## Problem

A disease model is frequently split across several files: the dynamics in one
file, parameter values / initial conditions in another (`params.R`, a config,
a `.csv`), sometimes a contact-structure file. Today the tool accepts a single
paste, so the numbers that live in other files are missing — and the translator
fills plausible defaults instead. Our 14-model test
([translation-test-results.md](../../translation-test-results.md)) made this the
**#1 real-world bottleneck**: several Tier-A models scored only *Medium* purely
because "params weren't in the paste", and the cross-cutting risk #3 is exactly
this silent parameter invention.

## Goal

Let the modeler submit the model as a **set of files** so the translator sees
dynamics + parameters + config together. Output stays a single consolidated
`model.py`. Improve fidelity by supplying real numbers; reduce invention.

## Scope decisions (settled during brainstorming)

- **File kinds — code *and* data/param files (option B).** CSV/JSON parameter
  files and contact matrices go in as text alongside code. This is the option
  that most directly improves fidelity, and it is no more engineering than
  code-only because Claude reads CSV/JSON as text. The differentiator is
  **guidance** (below), not mechanism.
- **Input UX — both upload and paste**, unified onto one representation: an
  ordered list of file blocks `{filename, content}`. "Upload" creates one
  prefilled block per selected file; "+ Add file" creates an empty block.
- **Cap — `MAX_FILES = 10`.** Enough for any real model; prevents dumping a
  whole repo. Enforced in the backend (authoritative) and mirrored in the UI.
- **No hard per-file/total size cap** — matches today's uncapped textarea; the
  roadmap notes multi-file is well within context limits.
- **Contact matrices — expectation-managed, not transcribed.** The target
  schema derives contact from declared age groups + built-in Prem 2021 matrices
  (`add_demographic_group(age_range=…)`), with `set_contact_override` for
  individual cells. A pasted matrix therefore mainly conveys *age structure*,
  not exact cell values. This is stated in the guidance, not enforced in code.

## Architecture

The frontend sends `files: [{filename, content}, …]`. The backend
**concatenates them into one source string with headers**, then feeds that into
the *existing, unchanged* translation + report pipeline.

```
files[] ──▶ render_source_files() ──▶ one source string ──▶ stream_translation()  (unchanged)
                                                        └──▶ generate_report()    (unchanged)
```

`translator.py` and the report call do not change — the headers become part of
the source string they already receive.

### `render_source_files(files)` — new, in `backend/prompt.py`

```
files: list[{"filename": str, "content": str}]

1. Drop blocks whose content is blank (after strip).
2. If nothing remains -> "".
3. If exactly one block AND it has no filename -> return its content verbatim
   (byte-identical to today's single paste; preserves prompt cache + example
   framing).
4. Otherwise, for each block emit:
       === file: <name> (<Lang>) ===
       <content>
   joined by a blank line. <name> defaults to "untitled" when empty. <Lang> is
   inferred from the filename extension via the existing language_for_extension();
   omitted when there is no recognizable extension.
```

The one-unnamed-file special case is what keeps existing single-paste behavior
and the prompt cache intact.

### Backend wiring — `backend/app.py`

- New module constant `MAX_FILES = 10`.
- `translate()` reads `files` from the payload:
  - If `files` is a non-empty list: enforce `len(files) <= MAX_FILES` (else emit
    `{"error": "Too many files (max 10)."}` and stop), then
    `source_code = prompt_assets.render_source_files(files)`.
  - Else fall back to the existing `source_code` string (backward compatible;
    keeps direct API callers and tests working).
- The empty-source guard and the rest of `event_stream()` are unchanged.
- `/api/health` exposes the cap so the UI reads it rather than hardcoding:
  add `"max_files": MAX_FILES` to the `config` (or a top-level `limits`) block.

### Model-facing guidance — new appended prompt-asset file

Per the project prompt-stability rule (CLAUDE.md), we do **not** edit the
existing prompt files. Add `prompt_assets/multi_file_guidance.md`, appended by
`build_system_prompt()` after the examples. Phrased conditionally so it is a
harmless no-op for single-file pastes and keeps the system prompt stable/cached:

> When several files are provided, treat them as one model. The file that
> defines the dynamics is authoritative for structure; parameter/data files
> supply the numeric values — use them instead of guessing. Do not invent
> compartments or mechanisms from a run wrapper or config that has no dynamics.
> A contact matrix conveys the age/group structure (declare it with
> `add_demographic_group`); its exact cell values are not transcribed.

`assets_status()` gains a `multi_file_guidance_present` flag (surfaced in
health, consistent with the other asset flags).

## Frontend UX — `static/index.html`

The source pane becomes a stackable list of file blocks; today's `#source`
textarea is the first block.

- **File block:** an optional **filename** input (reuses the existing
  `.pane-head input[type=text]` styling) + the content **textarea** + a **×**
  remove button. Blocks stack vertically; the pane scrolls.
- **Toolbar** (thin row under the pane-head): **"+ Add file"**, **"Upload
  files"** (`<input type=file multiple>` read client-side via `FileReader`), and
  a short muted **guidance hint**.
- **Cap enforcement:** disable "+ Add file" when block count reaches
  `max_files` (read from `/api/health`); on upload, accept only up to the
  remaining slots and set a brief status like "skipped 2 (max 10)".
- **Remove:** the × removes a block; never allow zero blocks (keep one empty).
- **`translate()`** posts `files: [{filename, content}, …]` built from the
  blocks (skipping blank content), plus the existing `source_language` (the
  global `lang` field, unchanged) and `category`. The empty-input guard becomes
  "at least one non-empty block".
- **Guidance hint text** (UI): *Include the model definition and the files with
  parameter values / initial conditions. Skip run scripts, plots, and tests.
  Export binary data (.rds/.mat/.npy) to text first. A contact matrix mainly
  conveys age structure.*

The category picker, report drawer, output pane, copy, stop, and Cmd/Ctrl-Enter
behaviors are unchanged.

## Wiring summary (every new symbol has a reader)

| New symbol | Defined in | Wired / read in |
|---|---|---|
| `render_source_files(files)` | `backend/prompt.py` | `backend/app.py` `translate()` |
| `MAX_FILES` | `backend/app.py` | `translate()` guard + `/api/health` config |
| `max_files` (health field) | `backend/app.py` health | `static/index.html` `loadConfig()` |
| `prompt_assets/multi_file_guidance.md` | new file | `build_system_prompt()` append + `assets_status()` flag |
| `files[]` request field | `static/index.html` `translate()` | `backend/app.py` `translate()` |
| file-block list + toolbar | `static/index.html` | frontend only |

## Testing

- **`render_source_files()`** (`tests/test_prompt.py` additions):
  - single unnamed block → content verbatim (regression guard on today's behavior).
  - single named block → one `=== file: name (Lang) ===` header.
  - multiple blocks → headers in order, per-file language inferred, blank blocks dropped.
  - all-blank / empty list → `""`.
- **`build_system_prompt()`** includes the guidance file when present; health
  reports `multi_file_guidance_present`.
- **`app.py`** (new `tests/test_app_multifile.py` or additions):
  - payload with `files[]` drives translation (mock the translator) and the
    rendered source reaches it with headers.
  - `len(files) > MAX_FILES` yields the `"Too many files"` error event.
  - `source_code` fallback path still works when `files` is absent.
  - `/api/health` includes `max_files`.
- Existing suite stays green.

## Docs

- `docs/prompt-change-log.md`: log the new appended `multi_file_guidance.md`
  (purpose + rationale), per the prompt-stability rule.
- `docs/ROADMAP.md`: mark #2 shipped, note single-file output kept, multi-file
  output still deferred.
- `README.md`: short note that several files can be submitted (upload or paste),
  concatenated with headers, single `model.py` out; the include/skip guidance.
- Update this repo's project docs / CLAUDE.md only if the new asset file changes
  the documented prompt-assembly story (it adds one appended file).

## Explicitly out of scope

- Multi-file **output** (single consolidated `model.py` is the natural target).
- Binary file parsing (`.rds`, `.mat`, `.npy`) — user exports to text first.
- Faithful transcription of contact-matrix cell values (schema uses Prem 2021).
- Per-file language override UI (language is inferred from the filename).
```
