from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

DOW_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTH_RU = [
    "янв",
    "фев",
    "мар",
    "апр",
    "май",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
]


@dataclass
class SeasonalitySummary:
    by_dow: list[dict]
    by_month: list[dict]
    by_quarter: list[dict]
    weekly_strength: float | None
    yearly_strength: float | None
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _strength(series: pd.Series, period: int) -> float | None:
    if len(series) < period * 2:
        return None
    values = series.astype(float).to_numpy()
    deseason = values.copy()
    for i in range(period, len(values)):
        deseason[i] = values[i] - values[i - period]
    var_all = float(np.var(values))
    if var_all <= 1e-12:
        return 0.0
    var_des = float(np.var(deseason[period:]))
    return float(max(0.0, min(1.0, 1.0 - var_des / var_all)))


def compute_seasonality(frame: pd.DataFrame, *, frequency: str = "D") -> SeasonalitySummary:
    notes: list[str] = []
    ordered = frame.sort_values("ds").copy()
    if ordered.empty:
        return SeasonalitySummary([], [], [], None, None, ["Нет данных"])

    ordered["dow"] = ordered["ds"].dt.dayofweek
    ordered["month"] = ordered["ds"].dt.month
    ordered["quarter"] = ordered["ds"].dt.quarter

    by_dow = []
    by_month = []
    by_quarter = []

    if frequency.upper() == "D":
        grouped = ordered.groupby("dow", as_index=False)["y"].mean()
        by_dow = [
            {"key": DOW_RU[int(row.dow)], "value": float(row.y)}
            for row in grouped.itertuples(index=False)
        ]
    else:
        notes.append("Профиль дня недели доступен только для дневной частоты")

    if len(ordered) >= 60 or frequency.upper() in {"W", "M"}:
        grouped_m = ordered.groupby("month", as_index=False)["y"].mean()
        by_month = [
            {"key": MONTH_RU[int(row.month) - 1], "value": float(row.y)}
            for row in grouped_m.itertuples(index=False)
        ]
        grouped_q = ordered.groupby("quarter", as_index=False)["y"].mean()
        by_quarter = [
            {"key": f"Q{int(row.quarter)}", "value": float(row.y)}
            for row in grouped_q.itertuples(index=False)
        ]
    else:
        notes.append("Для устойчивого месячного профиля желательно больше истории")

    weekly_strength = _strength(ordered["y"], 7) if frequency.upper() == "D" else None
    yearly_period = {"D": 365, "W": 52, "M": 12}[frequency.upper()]
    yearly_strength = _strength(ordered["y"], yearly_period)
    if weekly_strength is None and frequency.upper() == "D":
        notes.append("Недостаточно циклов для оценки недельной сезонности")
    if yearly_strength is None:
        notes.append("Недостаточно циклов для оценки годовой сезонности")

    return SeasonalitySummary(
        by_dow=by_dow,
        by_month=by_month,
        by_quarter=by_quarter,
        weekly_strength=weekly_strength,
        yearly_strength=yearly_strength,
        notes=notes,
    )
