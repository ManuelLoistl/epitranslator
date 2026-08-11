You are documenting a disease model that was just translated into the WHO
Collaboratory compartmental pandemic simulator framework.

Write the contents of `model.md` — the documentation file that sits next to
`model.py` in the model's folder. The framework reads it verbatim into the model
artifact, so output **only** the markdown document: no preamble, no explanation
of what you are doing, no surrounding code fence.

Structure it as:

# <Model name>

One short paragraph: what the model represents and where it came from.

## Compartments

A markdown table — id, meaning — one row per compartment in the translated
`model.py`.

## Parameters

A markdown table — name, meaning, default, unit — one row per transmission edge
and disease parameter in the translated `model.py`.

## Dynamics

Two to four sentences on how infection, progression, and any interventions or
strata work, in the model's own terms.

## Assumptions and limitations

Bullets, only for assumptions the source model actually makes or that the
translation had to impose (for example a mechanism the schema cannot express).

**Describe only what is in the translated `model.py` and its source.** Do not
invent parameters, mechanisms, citations, or validation claims. Where the
translation departed from the source, say so plainly in one bullet.
