"""Descriptive statistics and distribution-plot data preparation.

Returns plain arrays / DataFrames so the Panel layer only has to draw them.
Distributions are restricted to normal and lognormal, per the requirements.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

DISTRIBUTIONS = ("normal", "lognormal")


def describe_frame(df: pd.DataFrame) -> pd.DataFrame:
    """``df.describe()`` transposed, augmented with skew, kurtosis and missing counts.

    Only numeric columns appear (describe's default). Raises ``ValueError`` when
    there are no numeric columns to summarise.
    """
    numeric = df.select_dtypes(include=[np.number])
    if numeric.shape[1] == 0:
        raise ValueError("No numeric columns to summarise.")
    out = numeric.describe().T
    out["skew"] = numeric.skew(numeric_only=True)
    out["kurtosis"] = numeric.kurtosis(numeric_only=True)
    out["missing"] = numeric.isna().sum()
    return out


def stats_csv_bytes(df: pd.DataFrame) -> bytes:
    """CSV of :func:`describe_frame`, with the column name as the first field."""
    table = describe_frame(df)
    return table.to_csv(index=True, index_label="column").encode("utf-8")


def frame_csv_bytes(df: pd.DataFrame) -> bytes:
    """CSV of the current (cleaned) dataset for download."""
    return df.to_csv(index=False).encode("utf-8")


@dataclass
class QQData:
    theoretical: np.ndarray
    ordered: np.ndarray
    slope: float
    intercept: float
    r: float
    space_label: str


def qq_data(values: np.ndarray, dist: str = "normal") -> QQData:
    """Quantile-quantile data against a normal or lognormal reference.

    For lognormal we probability-plot ``log(values)`` against a normal, which is
    the standard construction and requires strictly positive values.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 3:
        raise ValueError("Need at least 3 values for a Q-Q plot.")

    if dist == "normal":
        data = values
        space_label = "Theoretical quantiles (normal)"
    elif dist == "lognormal":
        if np.any(values <= 0):
            raise ValueError("Lognormal Q-Q plot needs strictly positive values.")
        data = np.log(values)
        space_label = "Theoretical quantiles (normal, log-space)"
    else:
        raise ValueError(f"Unsupported distribution '{dist}'.")

    (osm, osr), (slope, intercept, r) = stats.probplot(data, dist="norm")
    return QQData(
        theoretical=osm, ordered=osr,
        slope=float(slope), intercept=float(intercept), r=float(r),
        space_label=space_label,
    )


@dataclass
class DistData:
    # Histogram (density-normalised) for the PDF panel.
    bin_edges: np.ndarray
    density: np.ndarray
    pdf_x: np.ndarray
    pdf_y: np.ndarray
    # ECDF + fitted CDF for the CDF panel.
    ecdf_x: np.ndarray
    ecdf_y: np.ndarray
    cdf_x: np.ndarray
    cdf_y: np.ndarray
    params_label: str


def pdf_cdf_data(values: np.ndarray, dist: str = "normal", bins: int = 30) -> DistData:
    """Prepare histogram+fitted-PDF and ECDF+fitted-CDF for one distribution."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 3:
        raise ValueError("Need at least 3 values to fit a distribution.")

    density, bin_edges = np.histogram(values, bins=bins, density=True)
    xg = np.linspace(float(values.min()), float(values.max()), 300)

    if dist == "normal":
        mu, sigma = stats.norm.fit(values)
        frozen = stats.norm(mu, sigma)
        params_label = f"normal (μ={mu:.4g}, σ={sigma:.4g})"
    elif dist == "lognormal":
        if np.any(values <= 0):
            raise ValueError("Lognormal fit needs strictly positive values.")
        shape, loc, scale = stats.lognorm.fit(values, floc=0)
        frozen = stats.lognorm(shape, loc=loc, scale=scale)
        params_label = f"lognormal (σ={shape:.4g}, scale={scale:.4g})"
    else:
        raise ValueError(f"Unsupported distribution '{dist}'.")

    ordered = np.sort(values)
    ecdf_y = np.arange(1, ordered.size + 1) / ordered.size

    return DistData(
        bin_edges=bin_edges, density=density,
        pdf_x=xg, pdf_y=frozen.pdf(xg),
        ecdf_x=ordered, ecdf_y=ecdf_y,
        cdf_x=xg, cdf_y=frozen.cdf(xg),
        params_label=params_label,
    )
