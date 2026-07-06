# Prompt asset change log

A record of every change EpiTranslator makes to the **upstream-owned prompt
files** — `prompt_assets/system_prompt.md`, `prompt_assets/target_schema.py`, and
the worked `prompt_assets/examples/` — relative to the originals published in the
Pandemic Simulator repo's documentation. It exists so it is clear where these
prompts differ from those originals, and why. Each entry gives the exact
before/after, the reason, and the evidence that motivated it.

**Scope: only changes to those upstream originals are recorded here.**
EpiTranslator's own prompt assets — the report-call instructions
(`output_report.md`), the multi-file guidance (`multi_file_guidance.md`), and any
other app-specific files — are not shared with the upstream project and do not
diverge from it, so their changes are deliberately kept out of this log.

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
