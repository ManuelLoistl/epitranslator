"""Stochastic SEIR with a 2-stage Erlang latent period and a leaky vaccine.

Fixed daily timestep. New events are Poisson draws around the deterministic rate
(demographic stochasticity). The latent period is split into TWO sequential
sub-stages E1 -> E2 (Erlang k=2), giving a non-exponential incubation rather than
an exponential one. Susceptibles are split into unvaccinated (S) and vaccinated
(Sv): vaccination moves S -> Sv at rate nu, and vaccinated individuals are less
susceptible (leaky vaccine) so they acquire infection at a reduced rate beta_v.
"""
import numpy as np


def step(S, Sv, E1, E2, I, R, beta, beta_v, sigma, gamma, nu, rng):
    N = S + Sv + E1 + E2 + I + R
    foi = I / N                                   # frequency-dependent force of infection
    inf_S  = rng.poisson(beta   * foi * S)        # S  -> E1
    inf_Sv = rng.poisson(beta_v * foi * Sv)       # Sv -> E1 (reduced susceptibility)
    vacc   = rng.poisson(nu * S)                  # S  -> Sv (vaccination)
    prog1  = rng.poisson(2.0 * sigma * E1)        # E1 -> E2  (Erlang stage rate = k/latent = 2*sigma)
    prog2  = rng.poisson(2.0 * sigma * E2)        # E2 -> I
    rec    = rng.poisson(gamma * I)               # I  -> R

    S  = S  - inf_S - vacc
    Sv = Sv - inf_Sv + vacc
    E1 = E1 + inf_S + inf_Sv - prog1
    E2 = E2 + prog1 - prog2
    I  = I  + prog2 - rec
    R  = R  + rec
    return S, Sv, E1, E2, I, R


# beta 0.4/day; leaky-vaccine beta_v 0.12 (~70% efficacy); latent 5 d (sigma=1/5);
# infectious 7 d (gamma=1/7); vaccination 1%/day (nu=0.01).
if __name__ == "__main__":
    rng = np.random.default_rng(0)
    state = (999000.0, 0.0, 0.0, 0.0, 1000.0, 0.0)
    for _ in range(200):
        state = step(*state, beta=0.4, beta_v=0.12, sigma=1 / 5, gamma=1 / 7, nu=0.01, rng=rng)
