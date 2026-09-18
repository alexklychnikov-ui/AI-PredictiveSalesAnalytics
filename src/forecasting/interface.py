"""Общий интерфейс прогнозных моделей."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd


@dataclass
class ForecastPointOut:
    ds: pd.Timestamp
    yhat: float
    yhat_lower: float | None = None
    yhat_upper: float | None = None


@dataclass
class FitPredictResult:
    points: list[ForecastPointOut]
    model_name: str
    model_version: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


class ForecastModel(Protocol):
    name: str

    def fit_predict(
        self,
        history: pd.DataFrame,
        *,
        horizon: int,
        frequency: str,
    ) -> FitPredictResult: ...
