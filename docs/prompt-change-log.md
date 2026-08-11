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

---

## 2026-07-11

### Add: two worked examples — age structure, and stochastic + Erlang + vaccination strata

#### Summary

Added two new before/after pairs to `prompt_assets/examples/`:

- `age_structured_seir_from_r/` — an age-stratified deterministic SEIR whose force
  of infection is contact-matrix mediated, translated with
  `add_demographic_group(age_range=...)` (opting into the built-in Prem 2021
  matrices) and a manually-applied age-structured FOI (`skip_edges` + `_apply_flow`
  + `self.contact_matrix`).
- `stochastic_erlang_vaccine_from_python/` — a fixed-step stochastic SEIR with a
  2-stage Erlang latent period and a leaky-vaccine stratum, translated with
  `STOCHASTIC = True` (per-step Poisson event counts), explicit `E1`/`E2`
  sub-compartments, and an `S`/`Sv` stratum split with a reduced `beta_v` edge.

No existing example, instruction, or schema file was modified — this is purely
additive. (The examples are used together with a companion **app-owned** guidance
file, `prompt_assets/structure_guidance.md`, and its wiring in
[../backend/prompt.py](../backend/prompt.py); per this log's scope that app-owned
file is not recorded here.)

#### Why

The prior prompt reliably produced a faithful *flat* compartmental core but
**dropped structure the source actually had**: on models with age stratification
(kieshaprem, cmmid-covid-uk) or vaccination strata (mpox) the baseline translation
collapsed them to a single unstratified population. That is a faithfulness loss —
the schema *can* represent these (demographic groups, parallel strata, explicit
sub-compartments, `STOCHASTIC`), but the prompt gave no worked pattern for them, so
the model defaulted to the flat core it had examples for.

These two examples supply the missing patterns. An evaluation on a 4-model subset
(flat-SIR canary, age SEIR, stochastic-Erlang ebola, age+strata mpox), scored via
the framework-built schema and sealed clean-context faithfulness judges, found:

- With the examples present, age structure and vaccination strata are recovered
  and judged **faithful** (correct strata, dose flows, per-stratum susceptibility;
  age wired into a real contact-matrix FOI, not cosmetic groups).
- The flat-SIR **canary stayed minimal** (S/I/R, no groups, no strata) — the
  examples did **not** cause over-enrichment or invented structure.
- The gain **generalized to a held-out model** never used to build the examples
  (cmmid-covid-uk: age groups recovered where the baseline had dropped them).

The conditional framing ("express this ONLY when the source contains it; adding
structure the source lacks is a translation error") lives in the companion
guidance file and is reinforced by each example's docstring.

#### Verification

Both `target.py` files build their schema and run through the framework (instantiate
+ integrate) with a valid config: population is conserved, no negative compartments,
and an epidemic occurs. Verified 2026-07-11.

#### Notes

- These examples were **authored by EpiTranslator** (the age one is based on the
  framework's own `covid_jax_model`); they are candidates to adopt upstream so the
  canonical example set carries the same patterns rather than forking here.
- Erlang recovery remained the weakest area in evaluation even with the stochastic
  example present — a known hard case, flagged for future attention, not a blocker.
---

## 2026-08-11

### Resync: realign with upstream framework API drift (2026-07-01 snapshot → `3e28faa`)

#### Summary

Our copies of `system_prompt.md`, `target_schema.py`, and the four worked
`examples/` were snapshotted from upstream on 2026-07-01 and had not been
touched since. In that window upstream renamed the model's hand-written
methods, changed what `prepare_initial_state()` returns, replaced the
travel-volume schema builder with a model-owned `build_travel_matrix()`
override, scoped its automatic unit conversion to transmission edges only,
and added an editorial-metadata builder. None of this is new
EpiTranslator-specific behavior — it is **entirely a resync**: bringing our
copies back into line with upstream's current API so translated `model.py`
files still match what the framework actually expects. Net effect: strictly
reduced divergence from upstream.

Each change below is paired with the upstream commit that introduced the API
change it tracks (upstream repository, not this one).

#### 1. `derivative()` → `equation()`, `_compute_derivatives()` → `_compute_equations()`

Upstream `3c34115` (2026-07-24) renamed both the abstract method every model
implements and the helper that applies the schema's transmission edges; the
old names and the `evaluate()` alias no longer exist in the framework.
Applied throughout `system_prompt.md` (the contract bullets, the
`equation()` patterns section, the pitfalls list), `target_schema.py` (the
`Model` docstring, the `equation()`/`_compute_equations()` stubs), and all
four `examples/*/target.py` files.

Before (`system_prompt.md`):
```
4. **`derivative(self, y, t, p)`** — the right-hand side, using `jax.numpy`.
   ...
## `derivative()` patterns
...
def derivative(self, y, t, p):
    ...
    derivs = self._compute_derivatives(states, rates)
    ...
```
After:
```
4. **`equation(self, y, t, p)`** — the right-hand side, using `jax.numpy`.
   ...
## `equation()` patterns
...
def equation(self, y, t, p):
    ...
    derivs = self._compute_equations(states, rates)
    ...
```

Before (`target_schema.py`):
```
        def derivative(self, y, t, p)            # ODE / per-step delta
...
    def _compute_derivatives(self, states: dict, rates: dict,
                             skip_edges: set[str] | None = None) -> dict:
```
After:
```
        def equation(self, y, t, p)              # ODE / per-step delta
...
    def _compute_equations(self, states: dict, rates: dict,
                             skip_edges: set[str] | None = None) -> dict:
```

Same mechanical rename applied to each example's method definition and call
site (e.g. `sir_basic_from_r/target.py`: `def derivative(self, y, t, p):` →
`def equation(self, y, t, p):`, `self._compute_derivatives(...)` →
`self._compute_equations(...)`).

Commit: `acc4959`.

#### 2. `prepare_initial_state()` returns a bare state array, not a tuple

Upstream `d00c4b0` changed `prepare_initial_state()` to return just the state
array (the framework already knows `compartment_list` from
`define_parameters()`); the old `(state_array, compartment_list)` tuple
return is no longer accepted. The framework also now builds
`self.travel_matrix` **before** `prepare_initial_state()` runs, so a model
must not set it there either.

Before (`system_prompt.md`):
```
3. **`prepare_initial_state(self)`** — set `self.travel_matrix`
   (`np.eye(R)` when there is no travel model) and return
   `(state_array, list(self.compartment_list))`.
```
After:
```
3. **`prepare_initial_state(self)`** — return the state array (normally
   `self.population_matrix`, after any demographic expansion). Return the array
   itself, not a tuple. Do **not** set `self.travel_matrix` here: the framework
   builds it before this method runs.
```

Before (`target_schema.py`):
```
        def prepare_initial_state(self)          # set self.travel_matrix; return (state, compartment_list)
```
After:
```
        def prepare_initial_state(self)          # return the state array (NOT a tuple)
```

Applied to all four examples, e.g. `sir_basic_from_r/target.py`:
```
    def prepare_initial_state(self):
        R = self.population_matrix.shape[1]
        # No inter-region travel: identity keeps each region self-contained.
        self.travel_matrix = np.eye(R)
        return self.population_matrix, list(self.compartment_list)
```
→
```
    def prepare_initial_state(self):
        # No inter-region travel — the framework supplies the identity matrix.
        return self.population_matrix
```
(the now-unused `import numpy as np` was also dropped from that file; the
other three examples' `self.travel_matrix = np.eye(...)` assignments and
tuple returns were removed the same way.)

Commit: `3d7081a` (examples, guidance); `aa0af09` (follow-up: the `__init__`
contract bullet still said *"add anything model-specific (e.g. a travel
matrix)"*, contradicting the new framework-owns-the-matrix rule two bullets
later — reworded to *"add anything model-specific (e.g. demographics,
temperature, a PRNG key for a stochastic model)"*).

#### 3. Mobility: `set_travel_volume()` removed; declare `travel_sigma` + override `build_travel_matrix()`

Upstream `06bb351` removed the `ParameterSchemaBuilder.set_travel_volume()`
builder entirely. Mobility is now expressed as an ordinary
`add_disease_parameter` (convention: `travel_sigma`,
`ValueType.PERCENTAGE`) plus a `Model.build_travel_matrix(admin_zones)`
override that returns the `(R, R)` matrix; the framework calls it and owns
`self.travel_matrix`. `_apply_interventions()` still returns the (possibly
intervention-modified) matrix, but a model must take that into a local
variable, not assign it back to `self.travel_matrix`.

Before (`system_prompt.md`, pitfalls):
```
- **Set `self.travel_matrix`** (use `np.eye(R)` when no travel) before the
  first `equation()` call — `_apply_interventions()` reads it.
```
After:
```
- **Mobility is model-owned, the travel matrix is framework-owned.** The
  framework calls `build_travel_matrix()` and stores the result on
  `self.travel_matrix` *before* `prepare_initial_state()` — identity when the
  model declares no travel. Never assign `self.travel_matrix` yourself. If the
  source has a travel/mobility model, declare its parameters with
  `add_disease_parameter` (convention: `travel_sigma`, `ValueType.PERCENTAGE`)
  and override `build_travel_matrix(self, admin_zones)` to return the `(R, R)`
  matrix — rows summing to 1, diagonal = the stay-home fraction `1 - sigma`,
  row/column order matching `admin_zones`. Never name a mobility parameter
  plain `sigma`: non-edge names route to the disease config, and a collision
  with an edge `variable_name` misroutes during uncertainty runs.
```
The recipe-step bullet `5. schema.set_travel_volume(...), demographics /
contact matrix, ...` was reworded to `5. mobility parameters (declared as
ordinary add_disease_parameter fields — see the mobility rule below),
demographics / contact matrix, ...`.

Before (`target_schema.py`):
```
    def set_travel_volume(self, leaving_default: float = 0.2,
                          leaving_min: float = 0.0, leaving_max: float = 1.0,
                          returning_default: float | None = None,
                          returning_required: bool = False, **kwargs: Any) -> None: ...
```
After:
```
    # There is no travel-specific builder method. A model that travels declares
    # its mobility parameters as ordinary disease parameters (convention:
    # `travel_sigma`, ValueType.PERCENTAGE) and overrides
    # Model.build_travel_matrix() — see the Model class below.
```
`_apply_interventions()`'s docstring gained a note that it also stores the
matrix on `self.travel_matrix`, and a new `build_travel_matrix()` stub was
documented on `Model`.

The age-structured example's `__init__` lost its reads of
`config["travel_matrix"]` and `config["travel_volume"]["leaving"]` (both
config keys no longer exist upstream):
```
        self.travel_matrix = np.fill_diagonal(
            np.array(config["travel_matrix"]), 1.0, inplace=False
        )
        self.sigma = config["travel_volume"]["leaving"]
```
removed outright (the example has no travel model — the fields were unused
scaffolding). The `equation()` bodies across the flat/age examples switched
from `rates, self.travel_matrix = self._apply_interventions(...)` to
`rates, travel_matrix = self._apply_interventions(...)` (or `rates, _ = ...`
where the matrix isn't used), since assigning to `self.travel_matrix` is now
wrong.

Commit: `3d7081a`.

#### 4. `DAYS`/`PERCENTAGE` auto-conversion scoped to transmission edges; `enable_variance` and `_to_rate` documented; "mass action" → "standard"

Upstream `06bb351` also narrowed automatic unit conversion: it applies only
to transmission-edge rates (`_load_transmission_params`), not to values
declared via `add_disease_parameter` / `add_admin_zone_field`, which arrive
in native units and must be converted at point of use with the new
`Model._to_rate(value, value_type)` helper. `add_disease_parameter` also
gained an `enable_variance: bool = True` keyword.

Before (`target_schema.py`, `ValueType` docstring):
```
    Conversions applied automatically at model load time:
      DAYS       -> per-day rate as 1/value  (default=10.0 ⇒ rate 0.1) — DO NOT pre-invert
      PERCENTAGE -> fraction as value/100    (default=80.0 ⇒ 0.8)
      RATE       -> used as-is (per-day rate)
```
After:
```
    Conversions applied automatically at model load time — for TRANSMISSION
    EDGES ONLY (_load_transmission_params reads schema.transmission_edges):
      DAYS       -> per-day rate as 1/value  (default=10.0 ⇒ rate 0.1) — DO NOT pre-invert
      PERCENTAGE -> fraction as value/100    (default=80.0 ⇒ 0.8)
      RATE       -> used as-is (per-day rate)

    Values from add_disease_parameter() / add_admin_zone_field() are NOT
    converted — they arrive in native units (a PERCENTAGE parameter is 20.0,
    not 0.2). Convert at the point of use with
    self._to_rate(value, ValueType.PERCENTAGE).
```
A `_to_rate()` static-method stub was added to the `Model` reference, and
`system_prompt.md`'s units bullet gained a matching paragraph
("Auto-conversion covers transmission edges only. ...").

Separately, this same commit fixed a terminology collision left over from
the 2026-07-01 fix in this log: the schema's own docstring and one worked
example still called the plain `rate * source` edge form "mass action" — the
exact label that, per the 2026-07-01 entry, had previously caused a
`frequency_dependent` mapping bug. Both surviving occurrences were replaced
with upstream's own term, "standard": the `_compute_equations()` docstring
(*"Apply all transmission edges (mass-action / frequency-dependent)"* →
*"(standard `rate * source` / frequency-dependent FOI)"*) and a comment in
`sir_basic_from_r/target.py` (*"mass-action I->R"* → *"standard rate *
source I->R"*).

Commit: `6b55ec6`.

#### 5. `set_model_metadata()` stub added to the schema reference

Upstream `036148b` added `ParameterSchemaBuilder.set_model_metadata()` — an
optional, artifact-only editorial-metadata builder (authors, license,
citations, model type, diseases, transmission routes, key assumptions,
etc.) with no effect on the simulation. Documented the stub in
`target_schema.py` immediately after `set_model_info()`, matching upstream's
signature:
```
    def set_model_metadata(self, authors: list[dict] | None = None,
                           license: str | None = None,
                           citations: list[str] | None = None,
                           model_type: str | None = None,
                           diseases: list[str] | None = None,
                           transmission_routes: list[str] | None = None,
                           questions_answered: list[str] | None = None,
                           key_assumptions: list[str] | None = None,
                           applicability: str | None = None,
                           not_for: str | None = None,
                           constraints: str | None = None,
                           biases: str | None = None,
                           validation: str | None = None) -> None: ...
```
(The no-invention instruction telling the model when/how to call it lives in
EpiTranslator's own `metadata_guidance.md`, which is out of this log's
scope — only the schema stub above is an upstream-owned-file change.)

Commit: `976ae8b`.

### Example fix: `sir_stochastic_from_python` disease_type collision with upstream's shipped model

Independent of the resync above: `sir_stochastic_from_python/target.py`
declared `disease_type="COVID_SIR_STOCHASTIC"`, which collides with
upstream's own shipped `compartment/models/test_covid_sir_stochastic` model
(same disease type). Renamed the identifier to `EXAMPLE_SIR_STOCHASTIC`, and,
to match the `EXAMPLE_*` disease type + neutral class name convention the
other three worked examples already use, renamed the class
`CovidSirStochasticModel` → `ExampleSirStochasticModel` and the label
`"COVID-19 Stochastic SIR"` → `"Example Stochastic SIR"`. No dynamics were
touched. Commits: `eabc80c` (disease_type only), `f2f2b01` (class/label,
completing the rename).

**A fix that was tried and reverted.** A first attempt (`eabc80c`) also added
`if self.beta is None: self.beta = <default>` fallback blocks to three
examples' `__init__` methods, on the theory that the framework was leaving
transmission-edge attributes unset. That diagnosis was wrong and the blocks
were reverted in `f2f2b01` — see the upstream-bug note below for the real
cause. No entry for that reverted attempt survives in this log.

#### Verification

All four worked examples (`sir_basic_from_r`, `age_structured_seir_from_r`,
`sir_stochastic_from_python`, `stochastic_erlang_vaccine_from_python`) were
copied byte-for-byte into a real checkout of the framework at upstream
commit `3e28faa` and run against it:

- `uv run pytest tests/test_smoke.py -q -m integration -k epitrans` — **48
  passed** (108 deselected), 0 failed.
- Each model was also constructed directly from a `ProcessedSimulation`
  built via the framework's own `load_simulation_config()` entry point, with
  a config in the framework's canonical shape, confirming every declared
  transmission parameter reached the model non-`None` (e.g.
  `sir_basic_from_r`: `self.beta = 0.3`, `self.gamma = 0.1`, matching the
  config's `{'beta': 0.3, 'gamma': 10.0}` with the `DAYS → 1/value`
  conversion correctly applied).
- The flat SIR example was run end-to-end through
  `compartment.run_simulation.run_simulation` and produced a real epidemic
  curve: I first / peak / last = `10000.0 / 303627.9375 / 3831.313720703125`.
  The other three examples were also run end-to-end and each produced a
  genuine epidemic (population conserved, `I` rising then falling).

This was independently reproduced by a reviewer before being treated as
verified.

**Caveat.** The epidemic check above (`max(I series) > I[0]`) only proves
the S→I edge is not fully dead (rate not silently zero/`None`). It does
**not** prove the coupling is semantically correct: a `frequency_dependent=
False` S→I edge (the exact class of bug fixed in this log's 2026-07-01
entry) was verified to also pass this check, since a bare `rate * source`
edge still produces a rising-then-falling `I` curve. Anyone relying on this
check as proof of correct `frequency_dependent` wiring should not — it is a
liveness check, not a correctness check.

#### Note: upstream framework bug hit during verification (not a prompt divergence, not fixed here)

While producing configs to verify the examples above, we found a mismatch
inside the framework itself, unrelated to anything in our prompt assets:
`SimulationSchema.to_example_config()` (`compartment/parameters.py:910-922`
— the function behind `generate_artifact --example-config`) writes
transmission rates under the `Disease.transmission_edges` key, but
`ValidationPostProcessor._process_default()`
(`compartment/validation/post_processor.py:104-109, 145-148`) only ever
reads them from the top-level `TransmissionEdges.items` key. Nothing in the
framework consumes the format the generator emits, so any config produced by
`--example-config` silently drops every transmission parameter before a
model is constructed. Upstream is aware the two shapes diverge — its own
scaffolder comments on it at `compartment/new_model.py:245-246` — but
`to_example_config()` itself hasn't been updated to match. This is worth
reporting to the framework's authors so `--example-config` either emits the
`TransmissionEdges.items` shape or the post-processor also reads
`Disease.transmission_edges`. It is **not** logged as a change here because
nothing in `prompt_assets/` diverges from upstream on this point — it is a
bug in two parts of the framework disagreeing with each other, discovered
while verifying, not something this log tracks.

#### Notes

- This entry is a **pure resync**: every change above brings our copies back
  into line with upstream's current API surface (commits `3c34115`,
  `d00c4b0`, `06bb351`, `036148b`) rather than adding EpiTranslator-specific
  behavior. Net divergence from upstream went down, not up.
- `metadata_guidance.md`, `model_doc.md`, and `structure_guidance.md` are
  EpiTranslator-owned prompt assets and are out of this log's scope per the
  header above; changes to them (including the `model.md`-generation feature
  shipped alongside this resync) are not recorded here.
