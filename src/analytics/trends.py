from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class TrendSummary:
    slope_per_period: float
    slope_pct_per_period: float | None
    recent_mean: float
    earlier_mean: float
    recent_vs_earlier_pct: float | None
    rolling_mean: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def compute_trend(frame: pd.DataFrame, *, frequency: str = "D") -> TrendSummary:
    ordered = frame.sort_values("ds").reset_index(drop=True)
    if ordered.empty:
        return TrendSummary(0.0, None, 0.0, 0.0, None, [])

    y = ordered["y"].astype(float).to_numpy()
    x = np.arange(len(y), dtype=float)
    if len(y) < 2 or np.allclose(y, y[0]):
        slope = 0.0
    else:
        slope = float(np.polyfit(x, y, 1)[0])

    mean_y = float(np.mean(y))
    slope_pct = float(slope / abs(mean_y) * 100.0) if mean_y != 0 else None

    window = {"D": 14, "W": 8, "M": 4}.get(frequency.upper(), 14)
    half = max(2, len(y) // 2)
    recent = y[-half:]
    earlier = y[:half]
    recent_mean = float(np.mean(recent))
    earlier_mean = float(np.mean(earlier))
    cmp_pct = None
    if earlier_mean != 0:
        cmp_pct = float((recent_mean - earlier_mean) / abs(earlier_mean) * 100.0)

    rolling = ordered["y"].rolling(window=min(window, max(2, len(y))), min_periods=1).mean()
    points = [
        {"ds": row.ds.isoformat(), "rolling_mean": float(val)}
        for row, val in zip(ordered.itertuples(index=False), rolling, strict=True)
        if pd.notna(val)
    ]
    return TrendSummary(
        slope_per_period=slope,
        slope_pct_per_period=slope_pct,
        recent_mean=recent_mean,
        earlier_mean=earlier_mean,
        recent_vs_earlier_pct=cmp_pct,
        rolling_mean=points,
    )
