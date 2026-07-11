import jax.numpy as np
import logging
from compartment.helpers import setup_logging
from compartment.model import Model
from compartment.parameters import ValueType

setup_logging()
logger = logging.getLogger(__name__)


class AgeStructuredSeirModel(Model):
    """Age-structured SEIR with a demographic contact matrix.

    The source stratifies S/E/I/R by age and drives infection through an
    age-by-age contact matrix. Faithful translation: declare the age bands with
    ``add_demographic_group`` (opting into the built-in Prem 2021 matrices) and
    apply the age-structured force of infection manually with ``_apply_flow`` and
    ``self.contact_matrix``. The S->E infection edge is skipped from the standard
    edge computation and applied by hand; E->I and I->R are standard edges.
    """

    @classmethod
    def define_parameters(cls, schema):
        schema.set_model_info(
            disease_type="EXAMPLE_AGE_SEIR",
            label="Age-structured SEIR",
            description="An SEIR model with age-stratified contact-matrix transmission",
        )

        # ---- Compartments ----
        schema.add_compartment("S", "Susceptible", "Susceptible population")
        schema.add_compartment("E", "Exposed", "Exposed but not yet infectious")
        schema.add_compartment("I", "Infected", "Infectious population", infective=True)
        schema.add_compartment("R", "Recovered", "Recovered and immune")

        # ---- Transmission edges ----
        # S->E infection: frequency-dependent; applied manually (age contact matrix).
        schema.add_transmission_edge(
            source="susceptible", target="exposed", variable_name="beta",
            frequency_dependent=True,
            label="Transmission Rate (S->E)",
            description="Per-contact transmission rate, scaled by the age contact matrix",
            default=0.05, min_value=0.001, max_value=1.0,
            default_min=0.02, default_max=0.1, unit="per day",
        )
        # E->I: incubation expressed as a period (framework converts 1/days -> rate).
        schema.add_transmission_edge(
            source="exposed", target="infected", variable_name="theta",
            label="Incubation Period (E->I)",
            description="Average days from exposure to becoming infectious",
            default=5.0, min_value=1.0, max_value=30.0,
            default_min=3.0, default_max=8.0,
            unit="days", value_type=ValueType.DAYS,
        )
        # I->R: recovery period.
        schema.add_transmission_edge(
            source="infected", target="recovered", variable_name="gamma",
            label="Recovery Period (I->R)",
            description="Average infectious period before recovery",
            default=7.0, min_value=1.0, max_value=60.0,
            default_min=4.0, default_max=14.0,
            unit="days", value_type=ValueType.DAYS,
        )

        # ---- Intervention ----
        # The source's contact reduction maps to a rate reduction on beta.
        schema.add_intervention(
            id="contact_reduction", label="Contact reduction",
            description="Reduces transmission by cutting contacts (e.g. distancing)",
            target_rates=["beta"], adherence=60.0, transmission_reduction=30.0,
        )

        # ---- Demographics ----
        # age_range opts into the country's built-in Prem 2021 contact matrix
        # aggregated to these bands. The source's contact cell values are NOT
        # transcribed — the schema supplies the matrix.
        schema.add_demographic_group("age_0_17",    "Children (0-17)", default_weight=33.0, age_range=(0, 17))
        schema.add_demographic_group("age_18_55",   "Adults (18-55)",  default_weight=44.0, age_range=(18, 55))
        schema.add_demographic_group("age_56_plus", "Elderly (56+)",   default_weight=23.0, age_range=(56, 120))

    def __init__(self, config):
        super().__init__(config)
        self.compartment_list = config["compartment_list"]
        self.travel_matrix = np.fill_diagonal(
            np.array(config["travel_matrix"]), 1.0, inplace=False
        )
        self.sigma = config["travel_volume"]["leaving"]

    def prepare_initial_state(self):
        # Expand (K, R) -> (K, A, R) using the declared age groups.
        self._prepare_demographic_state()
        return self.population_matrix, self.compartment_list

    def derivative(self, y, t, p):
        C = self.COMPARTMENTS
        params = self._unpack_params(p)

        states = {comp: y[i] for i, comp in enumerate(self.compartment_list)}
        S = states[C.S]
        I = states[C.I]  # noqa: E741

        non_total = [c for c in self.compartment_list if not c.endswith("_total")]
        N_total = sum(states[c] for c in non_total).sum(axis=0)
        I_frac = I / N_total[None, :]

        # Interventions modify beta (and possibly the travel matrix).
        rates = {"beta": params["beta"]}
        prop_infective = I.sum() / N_total.sum()
        rates, travel_matrix = self._apply_interventions(t, rates, prop_infective)
        for name, value in params.items():
            if name != "beta" and value is not None:
                rates[name] = value

        # Standard edges (E->I, I->R); skip the infection edge (applied manually).
        derivs = self._compute_derivatives(states, rates, skip_edges={"beta"})

        # Age-structured force of infection: spatial mixing then the contact matrix.
        BETA = ((rates["beta"] * travel_matrix) @ I_frac.T).T
        omega = self.contact_matrix @ BETA
        self._apply_flow(derivs, "S", "E", S * omega)

        return np.stack([derivs[comp] for comp in self.compartment_list])
