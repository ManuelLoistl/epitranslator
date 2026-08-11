# =============================================================================
# TARGET SCHEMA — the contract a translated model.py must conform to.
#
# This is a REFERENCE (annotated stubs), not runnable code. It documents the
# `Model` base class your translation subclasses, the `ParameterSchemaBuilder`
# API you call inside define_parameters(), and the ValueType enum. The real
# implementations live in the framework (compartment/model.py and
# compartment/parameters.py); you only write define_parameters() + equation().
# =============================================================================
from __future__ import annotations

from enum import Enum
from typing import Any


class ValueType(str, Enum):
    """Type of a parameter value — drives unit conversion and config rendering.

    Conversions applied automatically at model load time:
      DAYS       -> per-day rate as 1/value  (default=10.0 ⇒ rate 0.1) — DO NOT pre-invert
      PERCENTAGE -> fraction as value/100    (default=80.0 ⇒ 0.8)
      RATE       -> used as-is (per-day rate)
    """
    RATE = "rate"
    DAYS = "days"
    PERCENTAGE = "percentage"
    COUNT = "count"
    DATE = "date"
    BOOLEAN = "boolean"
    TEXT = "text"
    SELECT = "select"
    FLOAT = "float"
    INTEGER = "integer"
    COORDINATE = "coordinate"


class ParameterSchemaBuilder:
    """The `schema` object passed to define_parameters(cls, schema).

    Call these methods to declare the model. Everything else (compartment list,
    config class, example config, registry entry, cumulative _total compartments,
    self.<variable_name> rate attributes) is derived from these declarations.
    """

    # --- Identity (required, exactly once) ---
    def set_model_info(self, disease_type: str, label: str, description: str) -> None: ...

    # --- Compartments ---
    # `id` is the short key used in the state array (e.g. "S"). Set infective=True
    # on every compartment that contributes to the force of infection.
    def add_compartment(self, id: str, label: str, description: str,
                        infective: bool = False) -> None: ...
    def remove_compartment(self, id: str) -> None: ...  # also drops referencing edges

    # --- Transmission edges ---
    # One per compartment-to-compartment flow. With frequency_dependent=False
    # (default) the flow is `rate * source` — a plain per-capita flow with NO
    # dependence on infectives (use for progression/recovery, e.g. E->I, I->R).
    # With frequency_dependent=True the flow is `source * rate * sum(infective)/N`
    # — the infection form; use this for every S->E / S->I infection edge.
    # (There is no plain `rate * source * infective` density-dependent form; a
    # normalized `beta*S*I` with N=1 is the frequency_dependent=True case.)
    # `variable_name` becomes self.<variable_name>. Numeric bounds are in NATIVE
    # units per `value_type`. default_min/default_max are the default uncertainty
    # band; min_value/max_value are hard limits.
    def add_transmission_edge(
        self,
        source: str,                 # compartment id or label
        target: str,                 # compartment id or label
        variable_name: str,          # e.g. "beta", "gamma"
        label: str,
        description: str,
        default: float,
        min_value: float | None = None,
        max_value: float | None = None,
        default_min: float | None = None,
        default_max: float | None = None,
        unit: str = "per day",
        frequency_dependent: bool = False,
        value_type: "ValueType" = ValueType.RATE,
    ) -> None: ...
    def remove_transmission_edge(self, variable_name: str) -> None: ...

    # --- Interventions (optional) ---
    # target_rates lists the edge variable_names this intervention reduces:
    #   new_rate = rate * (1 - adherence * transmission_reduction)
    # modifies_travel=True replaces the travel matrix with identity while active
    # (lockdown). adherence / transmission_reduction are default percentages 0–100.
    def add_intervention(
        self,
        id: str,
        label: str,
        description: str,
        target_rates: list[str] | None = None,
        modifies_travel: bool = False,
        adherence: float | None = None,
        transmission_reduction: float | None = None,
    ) -> None: ...

    # --- Spatial travel (optional) ---
    # There is no travel-specific builder method. A model that travels declares
    # its mobility parameters as ordinary disease parameters (convention:
    # `travel_sigma`, ValueType.PERCENTAGE) and overrides
    # Model.build_travel_matrix() — see the Model class below.

    # --- Demographics / contact matrix (optional) ---
    # Declare an inclusive age_range on every group to opt into country-aware
    # Prem 2021 contact matrices. Age ranges must not overlap.
    def add_demographic_group(self, id: str, label: str, default_weight: float,
                              age_range: tuple[int, int] | None = None) -> None: ...
    def set_contact_override(self, from_group: str, to_group: str, value: float) -> None: ...

    # --- Bespoke fields (optional) ---
    # add_admin_zone_field: per-zone inputs (e.g. seroprevalence, temperature).
    # add_disease_parameter: top-level disease constants that aren't a single edge
    # rate (e.g. immunity_period, or the constants behind a manual flow).
    def add_admin_zone_field(self, name: str, label: str, description: str,
                             value_type: "ValueType", default: Any,
                             min_value: float | None = None, max_value: float | None = None,
                             unit: str | None = None, required: bool = False,
                             options: list[str] | None = None, **kwargs: Any) -> None: ...
    def add_disease_parameter(self, name: str, label: str, description: str,
                              value_type: "ValueType", default: Any,
                              min_value: float | None = None, max_value: float | None = None,
                              unit: str | None = None, required: bool = True,
                              options: list[str] | None = None, **kwargs: Any) -> None: ...

    def build(self) -> Any: ...  # finalize; raises if no model info / no compartments


class Model:
    """Base class for every compartmental model. Your translation subclasses this.

    MUST implement:
        @classmethod
        def define_parameters(cls, schema: ParameterSchemaBuilder) -> None
        def equation(self, y, t, p)              # ODE / per-step delta

    USUALLY implement:
        def __init__(self, config)               # call super().__init__(config) first
        def prepare_initial_state(self)          # return the state array (NOT a tuple)

    Optional class attributes:
        STOCHASTIC = True                        # use fixed-step Euler; equation() returns per-step delta
        SOLVER = "euler" | "odeint"              # explicit solver override (else odeint)
        COMPARTMENT_DELTA_GROUPING = {...}        # group raw compartments for output (e.g. dengue serotypes)

    Auto-derived after define_parameters() (do not set by hand):
        cls.DISEASE_TYPE, cls.COMPARTMENT_LIST, cls.COMPARTMENTS (attribute-style
        registry: self.COMPARTMENTS.S -> "S"; has .infective_ids), self.<variable_name>
        rate attributes, get_params().
    """

    # --- Set for you by super().__init__(config) on a typical model ---
    # self.population_matrix     (K, R) array — compartments × regions
    # self.compartment_list      list[str] of compartment ids (canonical order)
    # self.beta, self.gamma, ... transmission rates (converted to per-day by value_type)
    # self.interventions         list of runtime Intervention objects
    # self.intervention_statuses {intervention_id: False}
    # self.contact_matrix        (A, A) demographic contact matrix or None
    # self.start_date, self.start_date_ordinal, self.n_timesteps, self.admin_units

    # --- Helpers available inside equation() ---
    def _unpack_params(self, p) -> dict:
        """Tuple of params (schema edge order) -> {variable_name: value}."""
        ...

    def _compute_equations(self, states: dict, rates: dict,
                             skip_edges: set[str] | None = None) -> dict:
        """Apply all transmission edges (mass-action / frequency-dependent),
        auto-accumulate into <target>_total, skip inactive/skipped edges.
        Returns {compartment_id: deriv_array}."""
        ...

    def _apply_flow(self, derivs: dict, source_id: str, target_id: str, flow) -> None:
        """Manually move `flow` from source to target (and into target_total if it
        exists). Use for spatial coupling, multi-rate FOI, births, deaths."""
        ...

    def _apply_interventions(self, t, rates: dict, prop_infective) -> tuple[dict, Any]:
        """Apply declared interventions to rates and the travel matrix for time t.
        Returns (modified_rates, travel_matrix). No-op when none configured.
        Also stores the modified matrix on self.travel_matrix — take the return
        value into a LOCAL variable, do not assign it back to self."""
        ...

    def build_travel_matrix(self, admin_zones) -> Any:
        """Override ONLY when the model travels: return the (R, R) travel matrix.
        Rows sum to 1; the diagonal is the stay-home fraction. The framework calls
        this before prepare_initial_state() and stores the result on
        self.travel_matrix (identity when not overridden). Never assign
        self.travel_matrix yourself."""
        ...

    def _prepare_demographic_state(self) -> None:
        """Expand (K, R) -> (K, A, R) using declared demographic groups."""
        ...
