# Translation test — 14 published disease models

**Date:** 2026-06-30 / 2026-07-01. **Setup:** Opus 4.8, effort `high`, adaptive
thinking (the shipped `TRANSLATOR_*` defaults). Each model's core source was
extracted from its public repo and run through `backend.translator` unchanged.

## Purpose

The question this test answers is **not** "can the tool translate anything into
the compartmental schema" — a disease modeler already knows whether their model
fits the compartmental paradigm. The real question is:

> **When the source genuinely is a compartmental model that can live in this
> schema, does the translation come out faithful?**

So the results are split into **Tier A** (genuinely in-paradigm compartmental
models — the fair test) and **Tier B** (fundamentally different model classes —
ABM, Bayesian inference, state-space; a modeler wouldn't expect a faithful map,
but we still try and the tool should surface the limitations).

Every one of the 14 produced **syntactically valid, schema-conformant Python**
(a `define_parameters()` + `derivative()` model.py). Fidelity is the differentiator.

## Headline result

- **Tier A (in-paradigm): fidelity is High across the board, with exactly one
  systematic correctness bug** — the `frequency_dependent` flag on infection
  edges. That bug is now fixed in the prompt assets (see
  [prompt-change-log.md](prompt-change-log.md)) and verified.
- **Tier B (out-of-paradigm): the "still-try" behavior is sound** — the tool
  reduces each model to its generative/compartmental core and mostly documents
  the reinterpretation honestly. The one gap is **over-confident parameter
  invention** (it fills plausible numbers, and in the extreme "wrong file" case
  fabricated a whole model), which should be flagged rather than presented as
  translated.

## Tier A — genuinely in-paradigm (the fair test)

| Model | Source | Fidelity | Notes |
|---|---|---|---|
| SIR (sir-julia) | Julia ODE | 🟢 High | Exact; `β·c·S·I/N` preserved. |
| SIWR cholera | R/deSolve | 🟢 High | Both transmission routes + water reservoir correct; cosmetic `infective=True` on W. |
| PTTI (SEIR-CT) | Python + reaction-DSL | 🟢 High | 11 compartments, 19 couplings incl. bilinear contact-tracing terms — standout. |
| Wuhan SEIR (Prem) | R | 🟢 High | Age + contact matrix + subclinical 0.25× + R0→β eigenvalue calibration all preserved. |
| pomp SIR | R + C | 🟢 High | Deterministic skeleton faithful (seasonality, births/deaths, import); stochasticity dropped by design. |
| WHO simex | R/deSolve | 🟡 Medium | Structurally faithful, age preserved; Medium only because params weren't in the paste + a `/N` normalization choice. |
| CMMID COVID-UK | C++/Rcpp | 🟡 Medium | SEI3HR core + weighted FOI correct; age/stochastic/Erlang/travel dropped (documented). |
| MRC-IDE Mpox SEIR | odin DSL | 🟡 Medium | 2-stage latent + Ir/Id branch + 4 routes + stochastic preserved; **seeding dropped → inert**; CFR unit hazard. |
| DAEDALUS | C++/dust2 | 🟡 Medium | 8-compartment epi core + Is/Ia + Hr/Hd branch correct; age/sector/vax/NPI/behaviour/overflow-mortality dropped. |
| SIR (epicookbook) | Python notebook | 🔴 Low → **fixed** | The `frequency_dependent` bug; now `True` after the prompt fix. |

**Reading Tier A:** the Medium grades are largely **not translator weakness** —
they come from (a) numeric parameters living in separate config/binary files not
in the paste, or (b) the source carrying machinery beyond a plain compartmental
model (economics, NPIs, Erlang delays) that a modeler knows isn't schema-native.
Strip those away and the compartmental skeleton translates cleanly. The schema's
manual-flow escape hatch (`skip_edges` + `_apply_flow`) is why even elaborate
compartmental structure (contact-tracing, age-mixing, competing-risk branches)
survives intact.

## Tier B — out-of-paradigm (still-try + flag limitations)

| Model | Source | What it is | Behavior |
|---|---|---|---|
| EpiNow2 | Stan | Bayesian Rt inference (renewal + GP) | Reduced to a forward renewal *simulator*; reinterpretation documented. No longer does Rt estimation. |
| Covasim | Python ABM | Stochastic agent-based COVID | Excellent competing-risks reduction of the branching tree; age-stratified prognoses collapsed to one average. |
| laser-measles | Python (LASER) | Spatial stochastic metapopulation | SEIR + seasonality + stochastic kept; **vital dynamics, MCV1-newborns→R, and spatial mixing dropped**. |
| MRC-IDE mpox `run.R` | R entry-point | **Not a model** — a run wrapper with no dynamics | Flagged the missing model structure, but **fabricated a full SEIRD with authoritative-looking numbers**. |

**Reading Tier B:** reducing to the generative core is reasonable, and the tool
recognized each mismatch. The `run.R` case is the cautionary tale for the
"still-try" path: given a dynamics-free wrapper it invented compartments and
rates. For Tier B especially, invented parameters should be marked as guesses,
and a dynamics-free paste should yield a flagged skeleton, not a confident model.

## Cross-cutting observations

1. **Structural translation is genuinely strong** — compartment sets and flow
   topology come through even for brutal sources (multi-file C++/Stan/odin,
   reaction-string DSLs, ABM branching trees). The tool reliably knows when to
   bypass the declarative edge system and hand-write flows.
2. **One hard correctness bug, now fixed** — every model that computed its force
   of infection *manually* got the infective-coupling right; the only failure
   was the one model that relied on the declarative `add_transmission_edge`. Root
   cause and fix in [prompt-change-log.md](prompt-change-log.md).
3. **Silent parameter invention is the subtlest risk** — many real models keep
   numeric parameters in separate config/binary files, so the paste has
   structure but no numbers, and the tool fills plausible defaults. Worth marking
   invented values distinctly from source-derived ones.
4. **Big models lose their distinctive features — mostly documented.** Age
   structure was *preserved* when the source foregrounded it (Wuhan, simex used
   `add_demographic_group`) but dropped when it was buried (Covasim, DAEDALUS) —
   so the schema can do it; the tool just doesn't always reach for it.
5. **Extraction ("fork-or-paste") is the real-world bottleneck** — notebooks need
   cell extraction; C++/Stan/odin are multi-file with `#include`/`$new()`
   indirection; contact matrices and populations live in binary files; and
   pasting the wrong file (`run.R`) yields confident but invented output. This
   validates roadmap item #2 (multi-file input) and argues for input guidance
   ("paste the model *definition*, not the run script").

## Follow-ups this test suggests

- **Done:** fix the `frequency_dependent` guidance (prompt assets). See the
  change log.
- **Done (via the translation report):** invented parameters/compartments/
  interventions are marked (`guessed` origin), and a dynamics-free source raises a
  `high` / `no_dynamics` attention item.
- **Won't do — flagged skeleton for dynamics-free pastes.** Considered emitting
  an incomplete/stubbed `model.py` (instead of a fabricated one) when the source
  has no dynamics. Decided against it: the target user is a disease modeler who
  knows a run-wrapper/entry-point can't be faithfully translated without the AI
  assuming values, and the report's `no_dynamics` + `guessed` flags already signal
  that clearly. The advisory flag is sufficient; no need to also gate the code.
- **Consider:** nudge the tool to use `add_demographic_group` so age structure
  isn't dropped when the source doesn't foreground it.
- **Latent issues to watch** (noted during review): SIWR `W` marked
  `infective=True` (inert now, would corrupt FOI if any edge went
  frequency-dependent); mpox_seir dropped Poisson seeding; laser-measles mutates
  the RNG key inside `derivative()` under Euler.

Sources and generated `model.py` outputs from this run were kept in a scratch
directory (not committed).
