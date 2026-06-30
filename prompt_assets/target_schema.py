# =============================================================================
# TARGET SCHEMA  (placeholder — replace with your real schema)
# =============================================================================
# Drop your actual Python target schema here. The entire contents of this file
# are injected into the system prompt verbatim, under a "TARGET SCHEMA" heading,
# so the model knows exactly what shape the translated code must conform to.
#
# The richer and more concrete this is, the better the output. A real interface
# (base class / dataclass / function signatures) plus inline docstrings beats a
# prose description. Pair it with at least one filled-in example in
# prompt_assets/examples/ — a worked before/after is worth more than any amount
# of instruction text.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelParameters:
    """Replace with the real parameter definition for your schema."""
    ...


class DiseaseModel:
    """Replace with the real target interface a translated model must implement.

    For example, your schema might require a ``run(...)`` method returning a
    timeseries dict, a ``compute_r0(...)`` method, declared compartments, etc.
    Define that contract here so the model translates against a concrete target.
    """

    def run(self, *args, **kwargs):
        ...
