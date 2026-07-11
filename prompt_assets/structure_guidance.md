## Expressing structure the source already has

The schema can represent more than a flat compartmental core. When — and ONLY
when — the source model contains one of the following, express it. When the
source does not contain it, do not add it: adding structure the source lacks is a
translation error, not an improvement. Faithfulness runs in both directions —
express what is there, invent nothing that isn't.

- **Age / demographic structure.** If the source stratifies by age or drives
  transmission through a contact matrix, declare the age bands with
  `schema.add_demographic_group(id, label, default_weight=..., age_range=(lo, hi))`.
  `age_range` opts into the built-in Prem 2021 contact matrices — do NOT transcribe
  the source's contact cell values. Compute the age-structured force of infection
  manually: `_compute_derivatives(..., skip_edges={"beta"})`, then `_apply_flow`
  using `self.contact_matrix`.

- **Non-exponential (Erlang / boxcar) delays.** If the source splits a stage
  (commonly the latent E or infectious I) into k sequential sub-stages for a
  gamma/Erlang dwell time, declare k explicit sub-compartments (e.g. `E1`, `E2`)
  chained by edges, each advancing at rate k / mean-duration. Do NOT collapse them
  into a single exponential stage.

- **Vaccination / other strata.** If the source runs parallel strata (e.g.
  vaccinated vs unvaccinated), duplicate the affected compartments per stratum
  (e.g. `S`, `Sv`), add the flow between strata (e.g. `S -> Sv` at the vaccination
  rate), and give each stratum its own parameters (e.g. a reduced transmission
  edge from the vaccinated stratum). Do NOT collapse strata into a single
  population or a scalar rate reduction.

- **Stochastic dynamics.** If the source advances with random draws (tau-leaping,
  Binomial / Poisson / multinomial event counts, fixed-step stochastic updates),
  set `STOCHASTIC = True` and have `derivative()` return the per-step change (event
  counts), not instantaneous rates. Do NOT silently convert a stochastic model to
  a deterministic ODE.

- **Spatial / metapopulation structure.** If the source has multiple patches or a
  travel/mobility model, declare it with `set_travel_volume(...)` and build the
  travel matrix accordingly. When the source is a single well-mixed population,
  keep `self.travel_matrix = np.eye(R)` and do NOT invent patches.

When a source feature genuinely cannot be represented (an economic layer, a
fitting/likelihood step, arbitrary continuous time-dependent parameter functions),
leave a short `# NOTE:` and omit it rather than approximate it.
