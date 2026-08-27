<!--
EpiTranslator-owned prompt asset (NOT part of the upstream prompt).
Teaches the initial-population seeding contract that the upstream-owned
schema reference does not cover: the framework's default seeder assumes
compartments literally named "S" and "I". Appended to the system prompt by
backend/prompt.py -> build_system_prompt().
-->
## Initial-population seeding

The framework builds each zone's initial state with
`Model.get_initial_population(cls, admin_zones, compartment_list, **kwargs)`.
The **default implementation seeds compartments literally named `"S"` and
`"I"`**: it puts the zone's `infected_population` percentage into `I` and the
rest into `S`. If the translated model has no compartment with id `I` (or
none named `S`), the default raises `KeyError` at config validation and the
model cannot run.

Therefore: **if and only if the translated model's compartment ids are not
exactly `S`/`I`, override `get_initial_population()`**. Distribute the seed
across the model's entry infectious compartment(s), faithful to the model's
own structure — evenly across Erlang/boxcar sub-stages, or by the model's
branching fractions where infectious tracks split. Do not seed exposed-only
compartments unless the source itself seeds there.

Pattern (adapt compartment ids and split to the model):

```python
@classmethod
def get_initial_population(cls, admin_zones, compartment_list, **kwargs):
    """Seed each zone's infected percentage into this model's compartments."""
    import numpy as onp

    col = {v: i for i, v in enumerate(compartment_list)}
    pop = onp.zeros((len(admin_zones), len(compartment_list)))
    for z, zone in enumerate(admin_zones):
        N = float(zone["population"])
        pct = max(float(zone.get("infected_population", 0.0) or 0.0), 0.0)
        infected = N * pct / 100.0
        pop[z, col["S"]] = max(N - infected, 0.0)
        pop[z, col["I1"]] = infected * 0.5   # e.g. Erlang(2): split evenly
        pop[z, col["I2"]] = infected * 0.5
    return pop
```

Rules:

- Return a numpy array of shape `(n_zones, n_compartments)` in
  `compartment_list` order; leave `_total` columns at zero.
- `infected_population` is a **percentage** of the zone's population, not a
  count.
- Models whose compartments are exactly `S`, `I` (plus others the default
  does not seed, like `R`) need NO override — the default is correct.
