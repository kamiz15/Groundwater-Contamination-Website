   # analytical_models.py
"""
Pure numerical model functions used by the Panel apps and Flask routes.
This file contains:
- liedl_lmax
- chu_lmax
- ham_lmax
and helper functions for multiple runs:
- compute_liedl_multiple
- compute_chu_multiple
- compute_ham_multiple
"""

from __future__ import annotations

from typing import Iterable, List


# -------------------------
# LIEDL et al. (2005)
# -------------------------

def liedl_lmax(M: float, alpha_Tv: float, gamma: float,
               C_EA0: float, C_ED0: float) -> float:
    """
    Compute Lmax for the Liedl model.

    NOTE: This is a placeholder formula. Replace with the
    correct one if you already have it.
    """
    if alpha_Tv <= 0:
        raise ValueError("alpha_Tv must be positive")

    # Dummy example formula:  (just so Panel has something to compute)
    L = (M * gamma * max(C_ED0, 1e-6)) / (alpha_Tv * max(C_EA0, 1e-6))
    return float(L)


def compute_liedl_multiple(entries: Iterable[Iterable[float]]) -> List[float]:
    """
    entries: iterable of rows [M, alpha_Tv, gamma, C_EA0, C_ED0]
    """
    results: List[float] = []
    for row in entries:
        M, alpha_Tv, gamma, C_EA0, C_ED0 = row
        L = liedl_lmax(M, alpha_Tv, gamma, C_EA0, C_ED0)
        results.append(L)
    return results


# -------------------------
# CHU et al.
# -------------------------

def chu_lmax(W: float, alpha_Th: float, gamma: float,
             C_EA0: float, C_ED0: float, epsilon: float) -> float:
    """
    Compute Lmax for the Chu model.

    Placeholder formula – replace with the real one if available.
    """
    if alpha_Th <= 0:
        raise ValueError("alpha_Th must be positive")

    eff_acceptor = max(C_EA0 - epsilon, 1e-6)
    L = (W * gamma * max(C_ED0, 1e-6)) / (alpha_Th * eff_acceptor)
    return float(L)


def compute_chu_multiple(entries: Iterable[Iterable[float]]) -> List[float]:
    """
    entries: iterable of rows [W, alpha_Th, gamma, C_EA0, C_ED0, epsilon]
    """
    results: List[float] = []
    for row in entries:
        W, alpha_Th, gamma, C_EA0, C_ED0, epsilon = row
        L = chu_lmax(W, alpha_Th, gamma, C_EA0, C_ED0, epsilon)
        results.append(L)
    return results


# -------------------------
# HAM et al.
# -------------------------

def ham_lmax(Q: float, alpha_T: float, v: float,
             C_EA0: float, C_ED0: float) -> float:
    """
    Compute Lmax for the Ham model.

    Placeholder formula – adjust to the correct equation if you have it.
    """
    if alpha_T <= 0 or v <= 0:
        raise ValueError("alpha_T and v must be positive")

    L = (Q * max(C_ED0, 1e-6)) / (alpha_T * v * max(C_EA0, 1e-6))
    return float(L)


def compute_ham_multiple(entries: Iterable[Iterable[float]]) -> List[float]:
    """
    entries: iterable of rows [Q, alpha_T, v, C_EA0, C_ED0]
    """
    results: List[float] = []
    for row in entries:
        Q, alpha_T, v, C_EA0, C_ED0 = row
        L = ham_lmax(Q, alpha_T, v, C_EA0, C_ED0)
        results.append(L)
    return results
