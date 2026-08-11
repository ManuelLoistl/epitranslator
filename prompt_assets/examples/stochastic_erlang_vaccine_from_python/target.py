import jax.numpy as np
import jax
import logging
from compartment.helpers import setup_logging
from compartment.model import Model
from compartment.parameters import ValueType

setup_logging()
logger = logging.getLogger(__name__)


class StochasticErlangVaccineModel(Model):
    """Stochastic SEIR with a 2-stage Erlang latent period and a leaky vaccine.

    Faithful translation of three source features the framework CAN express:

    * Stochastic dynamics -> ``STOCHASTIC = True``; ``equation()`` returns the
      per-step change (Poisson event counts), not instantaneous rates.
    * Non-exponential latent period -> the single latent stage is kept as two
      explicit sub-compartments ``E1`` and ``E2`` (Erlang k=2), each advancing at
      rate 2 / latent_period, rather than collapsed to one exponential stage.
    * Vaccination stratum -> susceptibles are split into ``S`` and ``Sv`` with a
      vaccination flow ``S -> Sv`` and a reduced transmission edge ``beta_v`` from
      the vaccinated stratum, rather than collapsed to one population.
    """

    STOCHASTIC = True

    @classmethod
    def define_parameters(cls, schema):
        schema.set_model_info(
            disease_type="EXAMPLE_STOCH_ERLANG_VAX",
            label="Stochastic Erlang SEIR with vaccination",
            description="Stochastic SEIR with a 2-stage Erlang latent period and a leaky-vaccine stratum",
        )

        # ---- Compartments: two susceptible strata + a 2-stage Erlang latent ----
        schema.add_compartment("S", "Susceptible", "Unvaccinated susceptible population")
        schema.add_compartment("Sv", "Susceptible (vaccinated)", "Vaccinated susceptible population (reduced susceptibility)")
        schema.add_compartment("E1", "Exposed (stage 1)", "First latent sub-stage")
        schema.add_compartment("E2", "Exposed (stage 2)", "Second latent sub-stage")
        schema.add_compartment("I", "Infected", "Infectious population", infective=True)
        schema.add_compartment("R", "Recovered", "Recovered and immune")

        # ---- Edges (register parameters; the stochastic equation() applies them by hand) ----
        schema.add_transmission_edge(
            source="susceptible", target="exposed (stage 1)", variable_name="beta",
            frequency_dependent=True,
            label="Transmission Rate (S->E1)",
            description="Transmission rate for unvaccinated susceptibles",
            default=0.4, min_value=0.01, max_value=2.0,
            default_min=0.2, default_max=0.6, unit="per day",
        )
        schema.add_transmission_edge(
            source="susceptible (vaccinated)", target="exposed (stage 1)", variable_name="beta_v",
            frequency_dependent=True,
            label="Transmission Rate, vaccinated (Sv->E1)",
            description="Reduced transmission rate for vaccinated susceptibles (leaky vaccine)",
            default=0.12, min_value=0.0, max_value=2.0,
            default_min=0.04, default_max=0.2, unit="per day",
        )
        schema.add_transmission_edge(
            source="susceptible", target="susceptible (vaccinated)", variable_name="nu",
            label="Vaccination Rate (S->Sv)",
            description="Per-capita daily vaccination rate",
            default=0.01, min_value=0.0, max_value=1.0,
            default_min=0.0, default_max=0.05, unit="per day",
        )
        # Erlang latent: two explicit sub-stage edges, each a per-stage period.
        # Mean latent period 5 d over k=2 stages -> 2.5 d per stage.
        schema.add_transmission_edge(
            source="exposed (stage 1)", target="exposed (stage 2)", variable_name="theta1",
            label="Latent sub-stage 1 (E1->E2)",
            description="First Erlang latent sub-stage duration",
            default=2.5, min_value=0.5, max_value=15.0,
            default_min=1.5, default_max=4.0,
            unit="days", value_type=ValueType.DAYS,
        )
        schema.add_transmission_edge(
            source="exposed (stage 2)", target="infected", variable_name="theta2",
            label="Latent sub-stage 2 (E2->I)",
            description="Second Erlang latent sub-stage duration",
            default=2.5, min_value=0.5, max_value=15.0,
            default_min=1.5, default_max=4.0,
            unit="days", value_type=ValueType.DAYS,
        )
        schema.add_transmission_edge(
            source="infected", target="recovered", variable_name="gamma",
            label="Recovery Period (I->R)",
            description="Average infectious period before recovery",
            default=7.0, min_value=1.0, max_value=30.0,
            default_min=5.0, default_max=14.0,
            unit="days", value_type=ValueType.DAYS,
        )

    def __init__(self, config):
        super().__init__(config)
        # PRNG key for stochastic draws; pass "seed" in the config for reproducibility.
        import time
        seed = config.get("seed") if hasattr(config, "get") else None
        if seed is None:
            seed = int(time.time() * 1000) % (2 ** 31)
        self._key = jax.random.PRNGKey(seed)

    def prepare_initial_state(self):
        self.travel_matrix = np.eye(self.population_matrix.shape[1])
        return (self.population_matrix, list(self.compartment_list))

    def equation(self, y, t, p):
        """Tau-leaping stochastic step: returns per-timestep event-count deltas."""
        params = self._unpack_params(p)
        cl = self.compartment_list
        states = {c: y[i] for i, c in enumerate(cl)}

        S, Sv = states["S"], states["Sv"]
        E1, E2 = states["E1"], states["E2"]
        I = states["I"]  # noqa: E741

        non_total = [c for c in cl if not c.endswith("_total")]
        N = sum(states[c] for c in non_total)
        foi = I / (N + 1e-10)

        self._key, *ks = jax.random.split(self._key, 7)
        inf_S  = jax.random.poisson(ks[0], params["beta"]   * foi * S).astype(S.dtype)
        inf_Sv = jax.random.poisson(ks[1], params["beta_v"] * foi * Sv).astype(S.dtype)
        vacc   = jax.random.poisson(ks[2], params["nu"]     * S).astype(S.dtype)
        # Erlang stage rate = k / latent = 2 * (1/theta1). params["theta1"] is the
        # per-stage rate (framework already converted the 2.5-day period to 1/2.5).
        prog1  = jax.random.poisson(ks[3], params["theta1"] * E1).astype(S.dtype)
        prog2  = jax.random.poisson(ks[4], params["theta2"] * E2).astype(S.dtype)
        rec    = jax.random.poisson(ks[5], params["gamma"]  * I).astype(S.dtype)

        # Clamp so the two S outflows never exceed the S available.
        out_S = inf_S + vacc
        scale = np.where(out_S > S, S / (out_S + 1e-10), 1.0)
        inf_S = inf_S * scale
        vacc = vacc * scale
        inf_Sv = np.minimum(inf_Sv, Sv)
        prog1 = np.minimum(prog1, E1)
        prog2 = np.minimum(prog2, E2)
        rec = np.minimum(rec, I)

        derivs = {c: np.zeros_like(S) for c in cl}
        derivs["S"]  = -inf_S - vacc
        derivs["Sv"] = vacc - inf_Sv
        derivs["E1"] = inf_S + inf_Sv - prog1
        derivs["E2"] = prog1 - prog2
        derivs["I"]  = prog2 - rec
        derivs["R"]  = rec

        # Auto-generated cumulative tracking rows, if present.
        inflow = {"Sv": vacc, "E1": inf_S + inf_Sv, "E2": prog1, "I": prog2, "R": rec}
        for base, amount in inflow.items():
            tot = f"{base}_total"
            if tot in derivs:
                derivs[tot] = amount

        return np.stack([derivs[c] for c in cl])
