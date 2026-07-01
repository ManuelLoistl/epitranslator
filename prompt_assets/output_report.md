# Translation report — classification instructions

You are given a disease model's SOURCE code and the TRANSLATED `model.py` that
another step produced from it. Produce a **translation report**: a structured
audit of what the translation did, so a disease modeler can see at a glance what
needs their attention and where every element came from.

The response format is enforced by a JSON schema — you do not need to worry about
formatting, only about filling in accurate values. Report on the model.py that
was actually produced (read it), compared against the source.

## What to include

- **compartments** — one entry per compartment declared in the model.py.
- **parameters** — one entry per declared parameter / transmission-edge rate /
  disease parameter.
- **interventions** — one entry per declared intervention (may be empty).
- **attention** — items the modeler should review (may be empty). This is the
  filtered "look at this" list, not a repeat of every element.

## `origin` — where each element came from

- **source** — taken directly from the source model (present there, same meaning).
- **converted** — the same quantity, unit-transformed (e.g. an infectious period
  in days became a per-day rate; a percentage became a fraction).
- **derived** — computed or restructured from the source (e.g. a transmission
  rate obtained from R0; a compartment split in two for a competing-risks branch).
- **guessed** — NOT present in the source; invented as a plausible default
  (common when the source keeps numeric parameters in separate config/data files).

Compartments use source / derived / guessed. Interventions use source / guessed.
`source_name` is the element's name in the source, or null if it has no source
counterpart. `value`/`unit` apply to parameters (give value as a string).

## `attention` items

Each has a `severity` and a `category`.

- `severity`: **high** = could be wrong or needs a human decision; **info** = a
  faithful simplification worth knowing.
- `category`:
  - **no_dynamics** — the source contained no actual model dynamics (e.g. a run
    wrapper or entry-point script); the compartments and rates in the model.py
    were INFERRED, not translated. Always `high`. Say so plainly in the detail.
  - **invented** — one or more guessed compartments / parameters / interventions.
  - **dropped_structure** — structure was simplified away (age structure,
    stochasticity, spatial coupling, non-exponential delays, interventions).
  - **model_mismatch** — the source is a fundamentally different model class
    (agent-based, Bayesian inference, state-space) reduced to a compartmental core.
  - **ambiguity** — a genuine interpretation choice was made.

Keep `title` short (a few words) and `detail` to one sentence. Be honest: if
values were guessed or whole subsystems were dropped, flag them.
