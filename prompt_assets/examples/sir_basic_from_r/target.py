import jax.numpy as jnp
import numpy as np
import logging
from compartment.model import Model, ValueType

logger = logging.getLogger(__name__)


class ExampleSirJaxModel(Model):
    """A simple SIR compartmental model."""

    @classmethod
    def define_parameters(cls, schema):
        schema.set_model_info(
            disease_type="EXAMPLE_SIR",
            label="Example SIR",
            description="A simple SIR model",
        )

        # Compartments — I is infective (contributes to the force of infection).
        schema.add_compartment("S", "Susceptible", "Population susceptible to infection")
        schema.add_compartment("I", "Infected", "Currently infectious population", infective=True)
        schema.add_compartment("R", "Recovered", "Recovered and immune")

        # S->I: frequency-dependent transmission (beta * S * I / N).
        schema.add_transmission_edge(
            source="susceptible",
            target="infected",
            variable_name="beta",
            frequency_dependent=True,
            label="Transmission Rate (S->I)",
            description="Rate at which susceptibles become infected through contact",
            default=0.3,
            default_min=0.1,
            default_max=0.5,
            min_value=0.01,
            max_value=2.0,
            unit="per day",
        )

        # I->R: recovery. The source expresses this as a 10-day infectious
        # period, so declare it in DAYS — the framework converts 1/10 -> rate.
        schema.add_transmission_edge(
            source="infected",
            target="recovered",
            variable_name="gamma",
            label="Recovery Period (I->R)",
            description="Average infectious period before recovery",
            default=10.0,
            default_min=5.0,
            default_max=20.0,
            min_value=1.0,
            max_value=100.0,
            value_type=ValueType.DAYS,
            unit="days",
        )

    def __init__(self, config):
        super().__init__(config)

    def prepare_initial_state(self):
        R = self.population_matrix.shape[1]
        # No inter-region travel: identity keeps each region self-contained.
        self.travel_matrix = np.eye(R)
        return self.population_matrix, list(self.compartment_list)

    def derivative(self, y, t, p):
        C = self.COMPARTMENTS
        params = self._unpack_params(p)

        states = {c: y[i] for i, c in enumerate(self.compartment_list)}

        I = states[C.I]  # noqa: E741
        non_total = [c for c in C if not c.endswith("_total")]
        N_total = sum(states[c] for c in non_total)
        prop_infective = I.sum() / (N_total.sum() + 1e-10)

        # No-op when no interventions are configured.
        rates, self.travel_matrix = self._apply_interventions(
            t, {"beta": params["beta"]}, prop_infective
        )
        rates["gamma"] = params["gamma"]

        # Framework applies the edges (frequency-dependent S->I, mass-action
        # I->R) and accumulates cumulative I_total / R_total automatically.
        derivs = self._compute_derivatives(states, rates)
        return jnp.stack([derivs[c] for c in self.compartment_list])
