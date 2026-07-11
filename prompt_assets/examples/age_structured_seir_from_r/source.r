# Age-structured deterministic SEIR (3 age bands) with a contact matrix.
# Force of infection is contact-matrix mediated:
#   lambda_a = beta * sum_b C[a, b] * I_b / N_b
# so transmission depends on who-mixes-with-whom across age groups.
library(deSolve)

age_groups <- c("0-17", "18-55", "56+")

# Daily contact rates: rows = susceptible age group, cols = infectious age group.
contact <- matrix(c(5.46, 5.18, 0.93,
                    1.70, 9.18, 1.68,
                    0.83, 5.90, 3.80), nrow = 3, byrow = TRUE)

seir_age <- function(time, state, parms) {
  with(as.list(parms), {
    S <- state[1:3]; E <- state[4:6]; I <- state[7:9]; R <- state[10:12]
    N <- S + E + I + R
    lambda <- beta * (contact %*% (I / N))          # age-specific force of infection
    dS <- -lambda * S
    dE <-  lambda * S - E / latent_period
    dI <-  E / latent_period - I / infectious_period
    dR <-  I / infectious_period
    list(c(dS, dE, dI, dR))
  })
}

# beta = per-contact transmission; latent 5 days; infectious 7 days.
parms <- c(beta = 0.05, latent_period = 5, infectious_period = 7)

# Mostly susceptible; a few infectious adults seed the epidemic.
init  <- c(S = c(3300000, 4400000, 2200000), E = c(0, 0, 0),
           I = c(0, 100, 0), R = c(0, 0, 0))
times <- seq(0, 365, by = 1)
out   <- ode(y = init, times = times, func = seir_age, parms = parms)
