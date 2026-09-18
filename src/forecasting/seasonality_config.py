"""Выбор сезонностей и ограничений горизонта по длине истории."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class SeasonalityPlan:
    frequency: str
    n_points: int
    seasonal_period: int
    weekly: bool
    yearly: bool
    max_horizon: int
    history_status: str  # недостаточно | ограниченно | достаточно
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def seasonal_period_for(frequency: str) -> int:
    freq = (frequency or "D").upper()
    if freq.startswith("W"):
        return 52
    if freq.startswith("M"):
        return 12
    return 7


def build_seasonality_plan(n_points: int, frequency: str, *, requested_horizon: int) -> SeasonalityPlan:
    freq = (frequency or "D").upper()
    period = seasonal_period_for(freq)
    notes: list[str] = []

    weekly = False
    yearly = False
    if freq.startswith("D"):
        weekly = n_points >= 14
        yearly = n_points >= 730
        if not weekly:
            notes.append("Недельная сезонность отключена: меньше 2 недель истории")
        if not yearly:
            notes.append("Годовая сезонность отключена: меньше 2 лет дневной истории")
    elif freq.startswith("W"):
        yearly = n_points >= 104
        if not yearly:
            notes.append("Годовая сезонность отключена: меньше 2 лет недельной истории")
    elif freq.startswith("M"):
        yearly = n_points >= 24
        if not yearly:
            notes.append("Годовая сезонность отключена: меньше 24 месяцев истории")

    # history >= 4 * horizon → max_horizon = n // 4; минимум 1
    max_horizon = max(1, n_points // 4)
    # sufficiency / notes считаем по горизонту, который реально будет использован
    horizon = max(1, min(int(requested_horizon), max_horizon))

    preferred_min = max(3 * period, 5 * horizon)
    practical_min = max(2 * period, 4 * horizon)

    if n_points < max(period + 1, 2 * horizon + 1):
        history_status = "недостаточно"
        notes.append("Недостаточно точек даже для одного backtest-сплита")
    elif n_points < practical_min:
        history_status = "ограниченно"
        notes.append(f"История короче практического минимума ({practical_min} точек)")
    elif n_points < preferred_min:
        history_status = "ограниченно"
        notes.append(f"История короче предпочтительного объёма ({preferred_min} точек)")
    else:
        history_status = "достаточно"

    if horizon < int(requested_horizon):
        notes.append(f"Горизонт уменьшен до {horizon} по правилу history >= 4×horizon")

    return SeasonalityPlan(
        frequency=freq[:1] if freq else "D",
        n_points=n_points,
        seasonal_period=period,
        weekly=weekly,
        yearly=yearly,
        max_horizon=max_horizon,
        history_status=history_status,
        notes=notes,
    )
