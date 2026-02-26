# empirical_models.py
import math

def maier_lmax(M, tv, g, Ca, Cd):
    """
    Maier & Grathwohl plume length (Lmax)
    lMax = 0.5 * (M^2 / tv) * ((g*Cd/Ca)^0.3)
    """
    if tv <= 0 or Ca <= 0:
        raise ValueError("tv and Ca must be > 0")
    lmax = 0.5 * ((M * M) / tv) * (((g * Cd) / Ca) ** 0.3)
    return float(lmax)

def birla_lmax(M, tv, g, Ca, Cd, R):
    """
    Birla et al. plume length (Lmax)
    lMax = (1 - 0.047*M^0.404*R^1.883) * ((4*M^2)/(pi^2*tv)) * ln((((g*Cd)+Ca)/Ca) * (4/pi))
    """
    if tv <= 0 or Ca <= 0:
        raise ValueError("tv and Ca must be > 0")
    factor = (1 - (0.047 * (M ** 0.404) * (R ** 1.883)))
    inside_log = (((g * Cd) + Ca) / Ca) * (4 / math.pi)
    if inside_log <= 0:
        raise ValueError("Log argument must be > 0")
    lmax = factor * ((4 * M * M) / (math.pi * math.pi * tv)) * math.log(inside_log)
    return float(lmax)
