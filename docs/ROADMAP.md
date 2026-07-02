# Roadmap — EpiTranslator

A reviewable plan to walk through **after v1 is running**. This is a personal
test/experiment project: it may be abandoned at any point, so the guiding bias is
**don't over-build, don't paint into a corner**. Nothing here is committed work —
it's the agreed direction plus the trade-offs we worked out.

Effort labels: **S** = small (hours), **M** = moderate (a day-ish), **L** = large
(a real project). Status: ☐ todo · ◐ partial · ✅ done.

---

## v1 — current state (built)

- ✅ Paste model source → one streaming Claude call → bare translated Python out.
- ✅ FastAPI backend (`/` UI, `/api/translate` SSE stream) + minimal two-pane UI.
- ✅ Prompt assembled from editable files in `prompt_assets/` (instructions +
  target schema + worked examples), cached in the system prompt.
- ✅ Model/effort/thinking configurable via env vars (swap `TRANSLATOR_MODEL`).
- ✅ Local `.env` support for the API key (gitignored); Railway vars in prod.
- ✅ Dockerfile for Railway.
- ◐ **Real prompt / schema / examples** still placeholders — the one thing
  blocking genuine output. **This is the immediate next step, not part of the
  post-v1 backlog below.**

---

## Post-v1 backlog (go through these together)

> **Shipped 2026-07-01 — translation report.** The output now surfaces an
> attention banner (guessed params, dropped structure, dynamics-free source) and
> an expandable audit of every compartment/parameter/intervention translation
> with provenance. This delivers part of the "surface what needs attention"
> intent behind items #4 (validation) and #10 (in-app docs). Spec:
> `docs/superpowers/specs/2026-07-01-translation-report-design.md`.

### 1. Category picker on submit — **S** — ✅ shipped 2026-07-01
> **Shipped.** The list lives in `backend/categories.py` (the schema defines no
> category taxonomy, so open-question #3 is resolved — there is nothing to sync
> with). Optional, default "Unspecified"; the selection feeds a *disambiguation
> hint* into the user message (source stays authoritative). "Stored with the
> output" deferred to item #7. Spec:
> `docs/superpowers/specs/2026-07-01-category-picker-design.md`.

On submit, user chooses from a fixed list (respiratory, vector-borne,
waterborne, …). Feeds into the translation prompt so the translation is
category-aware; stored with the output.
- Work: a dropdown in the UI + one field in the request + one line in the prompt
  builder. Optionally drive the list from the same place the schema defines
  disease types so it stays in sync.

### 2. Multiple input files → single consolidated output — **S** — ✅ shipped 2026-07-01
> **Shipped.** Files are submitted as a set (upload or paste into named blocks),
> concatenated with `=== file: <name> (<Lang>) ===` headers into one source, and
> run through the existing translation + report pipeline (single `model.py` out).
> A single unnamed paste stays byte-identical to before. `MAX_FILES = 10`,
> enforced in the backend and mirrored to the UI via `/api/health`. Include/skip
> guidance lives in a new appended prompt-asset file (`multi_file_guidance.md`)
> plus a UI hint. Multi-file *output* remains deferred. Spec:
> `docs/superpowers/specs/2026-07-01-multi-file-input-design.md`.

Let a model that spans several files be submitted as a set.
- Work: UI to add several named files (add-file boxes or multi-select upload);
  backend takes a list of `{filename, content}`; prompt builder concatenates them
  with `=== file: <name> ===` headers so the model sees the whole project.
- Output stays a single file (the natural shape when translating *into one
  schema*). **Multi-file output is deferred** — it needs a file-boundary protocol
  + multi-file UI/download and is **M**, only if a real need appears.
- Caveat: bigger prompt, but well within context limits.

### 3. Edit translated code → resubmit → run-only — **M**
Make the output pane editable; a "Run" button executes the (possibly edited)
code without re-translating.
- Clean seam: `/api/translate` (Claude) vs `/api/run` (execute Python).
- Needs run inputs (params / initial conditions / duration): cheapest is
  baked-in example/default inputs — **no parameter wizard** (overkill).
- Depends on the run-output contract (see Linchpin).

### 4. Cheap validation on the translated run — **S–M**
Best-effort. Runs only when we actually can; otherwise skip gracefully.
- Smoke test: imports / instantiates / runs without error.
- Invariants: no NaN/Inf, non-negative compartments, mass balance / population
  conservation, attack rate in [0,1], R0 sane.
- Optional: a second Claude call as a faithfulness reviewer of the translation.

### 5. Equivalence check (translated vs. original) — tiered
The importer's gold-standard check, adapted to pasted (not cloned) code.
- **Python source → run both, compare numerically — M.** Feasible because no
  foreign runtime is needed. Compare per-compartment R²/RMSE/max-rel-error.
  The one genuinely new bit: a shared **invocation interface** so original and
  translated run with the *same* inputs (apples-to-apples).
- **Non-Python source → L (or skip).** Either install that runtime later (R /
  Julia easy; MATLAB painful/licensed; image bloat + per-language deps), or the
  cheap substitute: **user pastes the original's reference outputs** and we
  compare against those — zero foreign runtime.
- Recommended: Python auto-compare first; reference-output paste as the general
  fallback; add runtimes only on real demand.

### 6. Basic epi-chart visualization (optional) — **S**
Plot the run's timeseries (S/E/I/R, …) with a small JS chart.
- Low effort *if* the run output has a predictable shape (see Linchpin).
- Do last; nice-to-have.

### 7. Browser-only session persistence — **S** — ✅ shipped 2026-07-01
> **Shipped.** A `localStorage` snapshot (`mt.session.v1`) of the file blocks,
> language, category, and last output — saved on edit (debounced) and on
> translate, restored on load. No auth, no DB, no backend state.

Save last source / category / translation / edits in `localStorage` /
IndexedDB. No auth, no DB, no backend state. Correct scope for a test tool.

### 8. Output handoff — **S** — ✅ shipped 2026-07-01
> **Shipped.** A Download button beside Copy saves the output pane as
> `model.py` (client-side Blob). Automated GitHub push stays skipped.

- Download button (in addition to copy) — trivial.
- User commits the file to GitHub themselves. **Automated GitHub push is
  skipped** (re-adds the auth we're avoiding; download is enough).

### 9. Make interventions easy to add — **S (lightweight) / M (builder)**
After a user pastes their disease model, make it easy to add interventions.
- **Lightweight first pass (preferred):** in the UI, surface that interventions
  *can* be added and link/show the documentation on how to express them in the
  target schema — i.e. guidance + a pointer, not a form. Likely just a hint +
  doc link near submission/output.
- Fuller version (later, if needed): an actual intervention builder/picker that
  injects intervention definitions into the translation — **M**, only on demand.

### 10. In-app documentation (view + download) — **S** — ◐ partial (2026-07-01)
> **Partial.** A "Schema reference" button opens the target schema
> (`GET /api/docs`, served from `prompt_assets/target_schema.py` — one source of
> truth) in a modal, with its own Download. This is the highest-value doc and the
> basis for item 9. Remaining: broader project docs / how-to content if wanted.

Make the project/schema documentation available inside the app — viewable in the
UI and downloadable. Powers item 9 (the intervention guidance) and general
onboarding. Source the docs from the repo so there's one source of truth.

---

## Linchpin decision (settle early)

**Standardize the run-output contract** — the timeseries + summary shape a run
returns. Items 3, 4, 5, and 6 all depend on it. The target schema very likely
already dictates this; confirm it does and treat it as the contract.

---

## Deferred — revisit after the core flow works

- **Running generated/pasted Python: failures, deps, error surfacing.**
  Handle missing dependencies, surface runtime tracebacks to the UI so the user
  can edit and re-run, and skip gracefully when a model can't be run.
- **Error surfacing in general** (translation + run) — clean errors/tracebacks in
  the UI. Basic error events already exist server-side; polish later.

## Deferred — revisit LAST (after everything else)

**Untrusted code-execution security.** Running pasted/generated code is arbitrary
code execution. Parked until the rest works. Agreed approach when we get to it:
- **Biggest risk = API-key theft.** Code in the same container as
  `ANTHROPIC_API_KEY`, with network, can exfiltrate it. Keep execution in a
  **separate process/context that never shares an environment with the key.**
- Cheap, high-value controls (do these once deployed, even if still solo):
  1. Subprocess with a **scrubbed env** (no API key present).
  2. **No network egress** for executed code.
  3. **Hard CPU / memory / wall-clock limits**, kill on exceed.
  4. **Non-root**, ephemeral temp dir, read-only app files.
- **Strong isolation** (per-run isolated container / gVisor / Firecracker microVM)
  only **if/when public / multi-user** — that's an **L**, not a flag.
- Solo + local: in-process with a timeout is fine; the above matters once
  deployed, and especially once others can use it.

---

## Explicitly skipped (overkill for this scope)

- Running the *original* model in arbitrary native languages by default.
- Automated GitHub push (download + manual commit is enough).
- A parameter/config wizard for runs (default/example inputs suffice).
- Multi-file *output* (single consolidated output is the natural target).
- Heavy code-execution sandboxing while it's solo/local.

---

## Open questions to resolve at review time

1. Does the target schema already define the **run-output contract** (timeseries
   + summary)? If yes, item-5/6 unlock cheaply.
2. In practice, are source models **mostly Python** or a real mix? Decides
   whether auto-compare is the main path or a Python-only bonus.
3. Where should the **category list** live so the UI and schema stay in sync?

---

## Housekeeping

- The local `.env` holds a real Anthropic key for testing (gitignored). **Rotate
  or delete it** in the Anthropic Console when done testing.
