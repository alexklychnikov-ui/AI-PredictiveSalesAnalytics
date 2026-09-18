from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

MIN_POINTS = 12


@dataclass
class CorrelationSummary:
    pairs: list[dict]
    disclaimer: str

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_corr(a: pd.Series, b: pd.Series, method: str) -> float | None:
    aligned = pd.concat([a, b], axis=1).dropna()
    if len(aligned) < MIN_POINTS:
        return None
    left = aligned.iloc[:, 0]
    right = aligned.iloc[:, 1]
    if left.nunique() < 2 or right.nunique() < 2:
        return None
    if method == "spearman":
        # rank + pearson avoids hard dependency on scipy for Spearman
        value = left.rank().corr(right.rank(), method="pearson")
    else:
        value = left.corr(right, method="pearson")
    if pd.isna(value):
        return None
    return float(value)


def compute_correlations(frame: pd.DataFrame, driver_cols: list[str], *, max_lag: int = 7) -> CorrelationSummary:
    disclaimer = "Корреляция не доказывает причинность. Лаги считаются только по прошлым значениям фактора."
    pairs: list[dict] = []
    if frame.empty or not driver_cols:
        return CorrelationSummary(pairs=pairs, disclaimer=disclaimer)

    ordered = frame.sort_values("ds").reset_index(drop=True)
    y = ordered["y"].astype(float)
    for col in driver_cols:
        if col not in ordered.columns:
            continue
        series = pd.to_numeric(ordered[col], errors="coerce")
        pearson = _safe_corr(y, series, "pearson")
        spearman = _safe_corr(y, series, "spearman")
        best_lag = None
        best_lag_corr = None
        for lag in range(1, max_lag + 1):
            lagged = series.shift(lag)
            corr = _safe_corr(y, lagged, "pearson")
            if corr is None:
                continue
            if best_lag_corr is None or abs(corr) > abs(best_lag_corr):
                best_lag = lag
                best_lag_corr = corr
        if pearson is None and spearman is None and best_lag_corr is None:
            continue
        pairs.append(
            {
                "factor": col,
                "pearson": pearson,
                "spearman": spearman,
                "best_lag": best_lag,
                "best_lag_pearson": best_lag_corr,
                "n": int(pd.concat([y, series], axis=1).dropna().shape[0]),
            }
        )
    return CorrelationSummary(pairs=pairs, disclaimer=disclaimer)
