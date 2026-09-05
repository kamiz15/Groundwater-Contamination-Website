"""
Köhler et al. (2024) data-driven model.

Two second-order polynomial surrogates for BIOSCREEN-AT (Karanovic et al.,
2007), fitted to ~1000 synthetic sample sets:

    L_max  = A1 + A2*lambda_eff + A3*v     + A4*lambda_eff^2 + A5*v^2     + A6*lambda_eff*v
    T_Lmax = B1 + B2*lambda_eff + B3*gamma + B4*lambda_eff^2 + B5*gamma^2 + B6*lambda_eff*gamma

The point of the model is how little it asks for: BIOSCREEN-AT needs more than
ten field parameters and an iterative search to produce L_max, while these two
algebraic expressions need three between them.

  L_max  needs  lambda_eff and v
  T_Lmax needs  lambda_eff and gamma

The A and B coefficients are empirical, fixed, and not physically
interpretable — they are not inputs and are never exposed to the user.

Reference
    Köhler, A., P.K. Yadav, R. Liedl, J.B. Shil, T. Grischek, P. Dietrich
    (2024). A data-driven approach for simplifying the estimation of time for
    contaminant plumes to reach their maximum extent.
    J. Contam. Hydrol. 263: 104336.  doi:10.1016/j.jconhyd.2024.104336
    Eqs. (13) and (14); coefficients from Table 2.

Units are those the coefficients were fitted in and are NOT interchangeable:
    lambda_eff  [1/year]   effective first-order decay rate constant in the plume
    v           [m/year]   linear (average) groundwater velocity
    gamma       [1/year]   source decay rate constant
    L_max       [m]
    T_Lmax      [year]

Note on the name ``gamma``: elsewhere in CAST ``gamma`` is the stoichiometric
coefficient of the Liedl/Cirpka/Maier family. Here it is the SOURCE DECAY rate
constant, written Γ in the model manual and γ in the paper — the same quantity
BIOSCREEN calls ``sourceDecayCoefficient_gamma``. The two are unrelated; the
argument names below spell it out to keep them apart.
"""

from __future__ import annotations

from typing import Iterable, List

# Fitted coefficients (Köhler et al. 2024, Table 2)
# Fixed by the publication.
A1, A2, A3, A4, A5, A6 = 840.647, -5808.705, 49.982, 10338.393, -0.024, -85.617
B1, B2, B3, B4, B5, B6 = 114.000, -398.104, -47.176, 444.466, 14.728, 67.708

# Range of the synthetic training data (Köhler et al. 2024, Table 1).
LAMBDA_EFF_RANGE = (0.1, 0.45)   # 1/year
V_RANGE = (1.0, 61.0)            # m/year
GAMMA_RANGE = (0.0, 1.0)         # 1/year


# KÖHLER et al. (2024)

def kohler_lmax(lambda_eff: float, v: float) -> float:
    """
    Maximum plume length L_max [m] — Köhler et al. (2024), Eq. (13).

    lambda_eff : effective first-order decay rate constant in the plume [1/y]
    v          : linear groundwater velocity [m/y]
    """
    lambda_eff = float(lambda_eff)
    v = float(v)
    if lambda_eff < 0:
        raise ValueError("lambda_eff must be >= 0")
    if v <= 0:
        raise ValueError("v must be positive")

    lmax = (A1
            + A2 * lambda_eff
            + A3 * v
            + A4 * lambda_eff * lambda_eff
            + A5 * v * v
            + A6 * lambda_eff * v)
    return float(lmax)


def kohler_tlmax(lambda_eff: float, source_decay_gamma: float) -> float:
    """
    Time to reach the maximum plume extent T_Lmax [y] — Eq. (14).

    lambda_eff         : first-order decay rate constant in the plume [1/y]
    source_decay_gamma : source decay rate constant Γ [1/y]  (NOT the CAST
                         stoichiometric coefficient — see the module docstring)
    """
    lambda_eff = float(lambda_eff)
    g = float(source_decay_gamma)
    if lambda_eff < 0:
        raise ValueError("lambda_eff must be >= 0")
    if g < 0:
        raise ValueError("source_decay_gamma must be >= 0")

    tlmax = (B1
             + B2 * lambda_eff
             + B3 * g
             + B4 * lambda_eff * lambda_eff
             + B5 * g * g
             + B6 * lambda_eff * g)
    return float(tlmax)


def kohler_model(lambda_eff: float, v: float, source_decay_gamma: float) -> dict:
    """
    Run both expressions and report which inputs fell outside the fitted range.

    Returns
        {"Lmax": float, "TLmax": float, "warnings": [str, ...]}

    The polynomials are conic sections, so an extreme parameter combination can
    push either output negative. That is a sign the inputs are outside what the
    fit supports, not a plume that runs upstream — it is reported as a warning
    and the raw value is returned unchanged rather than silently clipped.
    """
    lmax = kohler_lmax(lambda_eff, v)
    tlmax = kohler_tlmax(lambda_eff, source_decay_gamma)

    warnings: List[str] = []
    for name, value, (lo, hi), unit in (
        ("lambda_eff", float(lambda_eff), LAMBDA_EFF_RANGE, "1/y"),
        ("v", float(v), V_RANGE, "m/y"),
        ("gamma (source decay)", float(source_decay_gamma), GAMMA_RANGE, "1/y"),
    ):
        if not (lo <= value <= hi):
            warnings.append(
                f"{name} = {value:g} {unit} is outside the fitted range "
                f"{lo:g}–{hi:g} {unit}; the result is an extrapolation."
            )
    if lmax < 0:
        warnings.append(
            f"L_max came out negative ({lmax:.2f} m) — this parameter "
            f"combination is outside where the polynomial is meaningful."
        )
    if tlmax < 0:
        warnings.append(
            f"T_Lmax came out negative ({tlmax:.2f} y) — this parameter "
            f"combination is outside where the polynomial is meaningful."
        )

    return {"Lmax": lmax, "TLmax": tlmax, "warnings": warnings}


def compute_kohler_multiple(entries: Iterable[Iterable[float]]) -> List[dict]:
    """
    Batch form for the multiple-computing interface.

    Each row is (lambda_eff, v, source_decay_gamma), in that order — the same
    column order the CSV upload should use.
    """
    results: List[dict] = []
    for row in entries:
        lambda_eff, v, source_decay_gamma = row
        results.append(kohler_model(lambda_eff, v, source_decay_gamma))
    return results


if __name__ == "__main__":
    # The two field sites from Köhler et al. (2024), Table 4. v is not printed
    # in that table; 20 and 26 m/y are the values that reproduce its published
    # L_max column, and are used here as the check.
    cases = [
        ("Brand / Niedergörsdorf (low end)",  0.365,  20.0, 0.00033),
        ("Brand / Niedergörsdorf (high end)", 0.730,  20.0, 0.0125),
        ("Bemidji (low end)",                 0.0185, 26.0, 0.091),
        ("Bemidji (high end)",                0.0435, 26.0, 0.182),
    ]
    print(f"{'site':<36} {'L_max [m]':>11} {'T_Lmax [y]':>11}")
    for label, lam, v, g in cases:
        out = kohler_model(lam, v, g)
        print(f"{label:<36} {out['Lmax']:>11.1f} {out['TLmax']:>11.1f}")
