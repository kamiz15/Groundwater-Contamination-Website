"""
Analytical model equations used by the Panel apps and Flask routes.
This file contains:
- liedl_lmax
- chu_lmax
- ham_lmax
and helper functions for multiple runs.
"""

from __future__ import annotations

import math
from typing import Iterable, List

from scipy.special import erf, erfcinv


# -------------------------
# LIEDL et al. (2005)
# -------------------------

def liedl_lmax(M: float, alpha_Tv: float, gamma: float, C_EA0: float, C_ED0: float) -> float:
    if alpha_Tv <= 0:
        raise ValueError("alpha_Tv must be positive")
    if C_EA0 <= 0:
        raise ValueError("C_EA0 must be positive")

    lmax = ((4.0 * M * M) / (math.pi * math.pi * alpha_Tv)) * math.log(
        ((gamma * C_ED0 + C_EA0) / C_EA0) * (4.0 / math.pi)
    )
    return float(lmax)


def compute_liedl_multiple(entries: Iterable[Iterable[float]]) -> List[float]:
    results: List[float] = []
    for row in entries:
        M, alpha_Tv, gamma, C_EA0, C_ED0 = row
        results.append(liedl_lmax(M, alpha_Tv, gamma, C_EA0, C_ED0))
    return results


# -------------------------
# CHU et al.
# -------------------------

def chu_lmax(W: float, alpha_Th: float, gamma: float, C_EA0: float, C_ED0: float, epsilon: float) -> float:
    if alpha_Th <= 0:
        raise ValueError("alpha_Th must be positive")
    if C_EA0 - epsilon <= 0:
        raise ValueError("C_EA0 - epsilon must be positive")

    lmax = ((math.pi * W * W) / (16.0 * alpha_Th)) * (((gamma * C_ED0) / (C_EA0 - epsilon)) ** 2)
    return float(lmax)


def compute_chu_multiple(entries: Iterable[Iterable[float]]) -> List[float]:
    results: List[float] = []
    for row in entries:
        W, alpha_Th, gamma, C_EA0, C_ED0, epsilon = row
        results.append(chu_lmax(W, alpha_Th, gamma, C_EA0, C_ED0, epsilon))
    return results


# -------------------------
# HAM et al.
# -------------------------

def ham_lmax(Q: float, alpha_T: float, gamma: float, C_EA0: float, C_ED0: float) -> float:
    if alpha_T <= 0:
        raise ValueError("alpha_T must be positive")
    if C_EA0 <= 0:
        raise ValueError("C_EA0 must be positive")

    lmax = ((Q * Q) / (4.0 * math.pi * alpha_T)) * (((gamma * C_ED0) / C_EA0) ** 2)
    return float(lmax)


def compute_ham_multiple(entries: Iterable[Iterable[float]]) -> List[float]:
    results: List[float] = []
    for row in entries:
        Q, alpha_T, gamma, C_EA0, C_ED0 = row
        results.append(ham_lmax(Q, alpha_T, gamma, C_EA0, C_ED0))
    return results


# -------------------------
# LIEDL 3D
# -------------------------

def liedl3d_lmax(
    M: float,
    alpha_Th: float,
    alpha_Tv: float,
    W: float,
    Cthres: float,
    C_EA0: float,
    C_ED0: float,
    gamma: float,
) -> float:
    if M <= 0 or alpha_Th <= 0 or alpha_Tv <= 0 or W <= 0:
        raise ValueError("M, alpha_Th, alpha_Tv, and W must be positive")
    if C_EA0 <= 0 or C_ED0 <= 0:
        raise ValueError("C_EA0 and C_ED0 must be positive")
    if Cthres <= 0:
        raise ValueError("Cthres must be positive")

    ratio = (gamma * Cthres + C_EA0) / (gamma * C_ED0 + C_EA0)
    if ratio <= 0:
        raise ValueError("Invalid concentration ratio for Liedl 3D.")

    pi_term = 0.25 * math.pi * ratio
    if not (0 < pi_term < 1):
        raise ValueError("Liedl 3D inputs must satisfy 0 < (pi/4)*ratio < 1.")

    def f_lm(x: float) -> float:
        if x <= 0:
            raise ValueError("Liedl 3D requires a positive plume length iterate.")
        return erf(W / math.sqrt(4.0 * alpha_Th * x)) * math.exp(
            -alpha_Tv * x * (math.pi / (2.0 * M)) ** 2
        ) - (math.pi / 4.0) * ratio

    def df_lm(x: float) -> float:
        h = 1e-4
        return (f_lm(x + h) - f_lm(max(x - h, 1e-8))) / max((x + h) - max(x - h, 1e-8), 1e-8)

    ma_1 = -1.0 / (math.pi * (alpha_Th / (W * W)) * math.log(1.0 - pi_term))
    ma_2 = -2.0 / (math.pi * math.pi * (alpha_Tv / (M * M))) * math.log(pi_term)
    ma_3 = (4.0 / (math.pi * math.pi)) * ((M * M) / alpha_Tv) * math.log((4.0 / math.pi) / ratio)

    ma_x0 = min(max(ma_1, ma_2), ma_3)
    min_x0 = min(ma_1, ma_2)
    x = ma_x0 if math.isclose(ma_x0, ma_3, rel_tol=1e-9, abs_tol=1e-9) else min_x0
    x = max(float(x), 1e-6)

    tol = 1e-6
    for _ in range(100):
        fx = f_lm(x)
        dfx = df_lm(x)
        if abs(dfx) < 1e-12:
            raise ValueError("Liedl 3D solver encountered a zero derivative.")
        step = fx / dfx
        x_next = x - step
        if x_next <= 0:
            x_next = x / 2.0
        if abs(x_next - x) < tol:
            return float(x_next)
        x = x_next

    raise ValueError("Liedl 3D solver did not converge for the provided inputs.")


def compute_liedl3d_multiple(entries: Iterable[Iterable[float]]) -> List[float]:
    results: List[float] = []
    for row in entries:
        M, alpha_Th, alpha_Tv, W, Cthres, C_EA0, C_ED0, gamma = row
        results.append(liedl3d_lmax(M, alpha_Th, alpha_Tv, W, Cthres, C_EA0, C_ED0, gamma))
    return results


# -------------------------
# CIRPKA et al. (2005)
# -------------------------

def cirpka_2005(Sw: float = 10, Ath: float = 0.1, Ca: float = 8, Cd: float = 5, Ga: float = 3.5) -> float:
    """
    Compute maximum plume length using the Cirpka et al. (2005) horizontal flow model.

    Parameters match the provided reference script:
    Sw = source width [L]
    Ath = transverse horizontal dispersivity [L]
    Ca = reactant concentration [M/L^3]
    Cd = source concentration [M/L^3]
    Ga = stoichiometric coefficient of the reactant [-]
    """
    if Sw <= 0:
        raise ValueError("Sw must be positive")
    if Ath <= 0:
        raise ValueError("Ath must be positive")
    if Ca <= 0:
        raise ValueError("Ca must be positive")
    if (Ga * Cd + Ca) <= 0:
        raise ValueError("Ga * Cd + Ca must be positive")

    cf = Ca / (Ga * Cd + Ca)
    Lm = (Sw ** 2) / (16.0 * Ath * erfcinv(cf) ** 2)
    return float(Lm)


def cirpka_lmax(Sw: float, alpha_Th: float, gamma: float, C_A: float, C_D: float) -> float:
    """Compatibility wrapper using canonical CAST parameter names."""
    return cirpka_2005(Sw=Sw, Ath=alpha_Th, Ca=C_A, Cd=C_D, Ga=gamma)


def cirpka_domain_length(lmax: float) -> float:
    """Domain length = 1.5 × L_max."""
    return 1.5 * lmax


def compute_cirpka_multiple(entries):
    """Batch compute for multiple parameter sets."""
    results = []
    for row in entries:
        Sw, alpha_Th, gamma, C_A, C_D = row
        lmax = cirpka_lmax(Sw, alpha_Th, gamma, C_A, C_D)
        results.append({"Lmax": lmax, "LD": cirpka_domain_length(lmax)})
    return results
