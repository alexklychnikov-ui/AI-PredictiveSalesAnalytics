from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class AnomalySummary:
    count: int
    points: list[dict]
    method: str

    def to_dict(self) -> dict:
        return asdict(self)


def detect_anomalies(frame: pd.DataFrame, *, z_threshold: float = 3.5) -> AnomalySummary:
    ordered = frame.sort_values("ds").reset_index(drop=True)
    if len(ordered) < 8:
        return AnomalySummary(count=0, points=[], method="mad")

    y = ordered["y"].astype(float)
    median = float(y.median())
    mad = float(np.median(np.abs(y - median)))
    if mad == 0 or np.isnan(mad):
        return AnomalySummary(count=0, points=[], method="mad")

    score = 0.6745 * (y - median) / mad
    mask = score.abs() > z_threshold
    points = [
        {
            "ds": row.ds.isoformat(),
            "y": float(row.y),
            "score": float(score.loc[idx]),
        }
        for idx, row in ordered[mask].iterrows()
    ]
    return AnomalySummary(count=len(points), points=points, method="mad")
