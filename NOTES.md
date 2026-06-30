# Project notes & deferred decisions

Running log of intended direction and things parked for later. This is a
personal test/experiment project — it may be abandoned at any point, so the bias
is: don't over-build, don't paint into a corner.

## Intended direction (not yet built, may change)

A translation flow closer to the epidemic-simulator importer's "checks and runs",
adapted to the fact that source code is **pasted, not cloned**:

1. Translate pasted model code into the target Python schema (built — current app).
2. Show the translated code, let the user **edit** it and resubmit. On resubmit,
   the model code only **runs** (no re-translation).
3. Cheap validation on the translated run: smoke test (imports/instantiates/runs)
   + invariants (no NaN/Inf, non-negative compartments, mass balance, R0 sane).
   NOTE: running the output model is **best-effort / optional** — only do it when
   we actually can; otherwise skip running entirely, no need to force it.
4. Equivalence check, tiered by source language:
   - **Python source** → run original + translated with the same inputs and
     compare numerically (per-compartment R²/RMSE/max-rel-error). Feasible because
     no foreign runtime is needed.
   - **Non-Python** → either install that runtime later (R/Julia easy, MATLAB
     painful/licensed), or fall back to: user pastes the original's reference
     outputs and we compare against those.
5. Optional: basic epi-chart visualization of the run output (timeseries).
6. Session persisted **in the browser only** (localStorage/IndexedDB) — no auth.
7. Output via copy/paste or **download**; user commits it to GitHub themselves.

### Linchpin to decide early
Standardize the **run-output contract** (timeseries + summary shape) — run,
validation, and viz all depend on it. The target schema likely already dictates
this; confirm it does.

### Explicitly skipped (overkill for this scope)
- Running the *original* model in arbitrary native languages (multi-runtime ops).
- Automated GitHub push (re-adds the auth we're avoiding; download is enough).
- A parameter/config wizard for runs (default/example inputs are fine).

## DEFERRED — revisit later, after the core flow works

**Running generated/pasted Python code — failures, deps, error surfacing.**
Best-effort feature. When we build it, handle: missing dependencies, runtime
errors/tracebacks surfaced to the UI so the user can edit and re-run, and the
case where the model simply can't be run (skip gracefully). Parked for now.

**Error surfacing in general (translation + run).** Show clean errors/tracebacks
in the UI. Deferred — basic error events exist in the API already; polish later.

## DEFERRED — revisit LAST, after everything else

**External / untrusted code execution security.**
The moment we run pasted-or-generated model code (translated Python first, other
languages later), we are executing untrusted code. Parked until the rest works.

When we revisit, the plan we already worked out:
- **Biggest risk = API-key theft.** The translator container holds
  `ANTHROPIC_API_KEY`; code running in the same container with network access can
  read and exfiltrate it. Keep code execution in a **separate process/context
  that never shares an environment with the key.**
- Cheap, high-value controls (do these when deployed even if still solo):
  1. Run model code in a **subprocess with a scrubbed env** (no API key present).
  2. **Block network egress** for the executed code.
  3. **Hard CPU / memory / wall-clock limits**, kill on exceed.
  4. **Non-root**, ephemeral temp dir, read-only app files.
- Strong isolation (per-run isolated container / gVisor / Firecracker microVM,
  no network) only needed **if/when it becomes public / multi-user**.
- Solo + local: running in-process with a timeout is fine; the above matters once
  it's deployed and especially once others can use it.

## Housekeeping
- The local `.env` holds a real Anthropic key for testing (gitignored). Rotate or
  delete it in the Anthropic Console when done testing.
