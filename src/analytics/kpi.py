from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import numpy as np
import pandas as pd


@dataclass
class KpiSummary:
    total: float
    mean: float
    median: float
    std: float
    min_value: float
    max_value: float
    min_date: datetime | None
    max_date: datetime | None
    last_value: float
    prev_period_change_pct: float | None
    rolling_mean_7: float | None
    volatility: float | None
    points: int

    def to_dict(self) -> dict:
        return asdict(self)


def compute_kpi(frame: pd.DataFrame, *, frequency: str = "D") -> KpiSummary:
    if frame.empty:
        return KpiSummary(
            total=0.0,
            mean=0.0,
            median=0.0,
            std=0.0,
            min_value=0.0,
            max_value=0.0,
            min_date=None,
            max_date=None,
            last_value=0.0,
            prev_period_change_pct=None,
            rolling_mean_7=None,
            volatility=None,
            points=0,
        )

    ordered = frame.sort_values("ds").reset_index(drop=True)
    y = ordered["y"].astype(float)
    window = {"D": 7, "W": 4, "M": 3}.get(frequency.upper(), 7)
    rolling = y.rolling(window=window, min_periods=max(2, window // 2)).mean()
    change = None
    if len(y) >= window * 2:
        recent = y.iloc[-window:].sum()
        previous = y.iloc[-2 * window : -window].sum()
        if previous != 0:
            change = float((recent - previous) / abs(previous) * 100.0)

    min_idx = int(y.idxmin())
    max_idx = int(y.idxmax())
    return KpiSummary(
        total=float(y.sum()),
        mean=float(y.mean()),
        median=float(y.median()),
        std=float(y.std(ddof=0)),
        min_value=float(y.min()),
        max_value=float(y.max()),
        min_date=ordered.loc[min_idx, "ds"].to_pydatetime(),
        max_date=ordered.loc[max_idx, "ds"].to_pydatetime(),
        last_value=float(y.iloc[-1]),
        prev_period_change_pct=change,
        rolling_mean_7=float(rolling.iloc[-1]) if not np.isnan(rolling.iloc[-1]) else None,
        volatility=float(y.std(ddof=0) / abs(y.mean())) if y.mean() != 0 else None,
        points=int(len(y)),
    )
