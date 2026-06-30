"""Stochastic SIR model (tau-leaping) in plain Python + NumPy.

At each daily step the number of new infections and recoveries is drawn from
a Poisson distribution whose mean is the deterministic rate — giving
demographic stochasticity around the same expected trajectory as the ODE.
"""
import numpy as np


def simulate_sir(S0, I0, R0, beta, gamma, days, seed=0):
    rng = np.random.default_rng(seed)
    S, I, R = float(S0), float(I0), float(R0)
    trajectory = []

    for _ in range(days):
        N = S + I + R
        # Expected events per day
        infection_rate = beta * S * I / N          # frequency-dependent
        recovery_rate = gamma * I

        # Poisson-distributed event counts, clamped to available population
        new_infections = min(rng.poisson(infection_rate), S)
        new_recoveries = min(rng.poisson(recovery_rate), I)

        S -= new_infections
        I += new_infections - new_recoveries
        R += new_recoveries
        trajectory.append((S, I, R))

    return trajectory


# beta = 0.4 per day; recovery over a 7-day infectious period (gamma = 1/7).
if __name__ == "__main__":
    simulate_sir(S0=999999, I0=1, R0=0, beta=0.4, gamma=1 / 7, days=90)
