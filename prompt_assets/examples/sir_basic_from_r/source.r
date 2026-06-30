# Basic deterministic SIR model, written in R using the deSolve package.
# Frequency-dependent transmission; recovery expressed as an infectious period.

library(deSolve)

sir_model <- function(time, state, parameters) {
  with(as.list(c(state, parameters)), {
    N <- S + I + R
    infection <- beta * S * I / N   # frequency-dependent force of infection
    recovery  <- gamma * I
    dS <- -infection
    dI <-  infection - recovery
    dR <-  recovery
    list(c(dS, dI, dR))
  })
}

# Parameters
beta <- 0.3                      # transmission rate (per day)
infectious_period <- 10          # days
gamma <- 1 / infectious_period   # recovery rate (per day)

parameters <- c(beta = beta, gamma = gamma)

# Initial state (one population)
init  <- c(S = 999990, I = 10, R = 0)
times <- seq(0, 365, by = 1)

out <- ode(y = init, times = times, func = sir_model, parms = parameters)
