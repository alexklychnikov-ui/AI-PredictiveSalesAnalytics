from __future__ import annotations

from dataclasses import dataclass

FREQ_TO_SEASONAL_CYCLE = {
    "D": 365,
    "W": 52,
    "M": 12,
}

FREQ_LABEL = {
    "D": "дневная",
    "W": "недельная",
    "M": "месячная",
}


@dataclass(frozen=True)
class HistoryAssessment:
    status: str
    history_points: int
    seasonal_cycle: int
    practical_minimum: int
    recommended_minimum: int
    max_horizon: int
    requested_horizon: int
    allowed_horizon: int
    can_forecast: bool
    message: str


def assess_history(history_points: int, *, frequency: str, horizon: int) -> HistoryAssessment:
    freq = frequency.upper()
    if freq not in FREQ_TO_SEASONAL_CYCLE:
        raise ValueError("frequency must be one of D, W, M")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")

    cycle = FREQ_TO_SEASONAL_CYCLE[freq]
    practical_minimum = max(2 * cycle, 4 * horizon)
    recommended_minimum = max(3 * cycle, 5 * horizon)

    # max horizon such that history >= max(2*cycle, 4*h)  => h <= history/4
    # also keep at least some room for weekly seasonality on daily data
    max_horizon = max(1, history_points // 4)
    if history_points < 8:
        max_horizon = 0

    allowed_horizon = min(horizon, max_horizon) if max_horizon else 0
    can_forecast = history_points >= max(8, 4 * 1) and allowed_horizon >= 1

    if history_points >= recommended_minimum:
        status = "достаточно"
        message = (
            f"История {history_points} точек ({FREQ_LABEL[freq]}) достаточна "
            f"(рекомендуется ≥ {recommended_minimum})."
        )
    elif history_points >= practical_minimum:
        status = "ограниченно"
        message = (
            f"История {history_points} точек на нижней границе "
            f"(практический минимум {practical_minimum}, лучше {recommended_minimum})."
        )
    else:
        status = "недостаточно"
        message = (
            f"История {history_points} точек недостаточна для уверенного сезонного прогноза "
            f"(нужно ≥ {practical_minimum}). Допустимый горизонт: {allowed_horizon}."
        )
        can_forecast = allowed_horizon >= 1 and history_points >= 8

    return HistoryAssessment(
        status=status,
        history_points=history_points,
        seasonal_cycle=cycle,
        practical_minimum=practical_minimum,
        recommended_minimum=recommended_minimum,
        max_horizon=max_horizon,
        requested_horizon=horizon,
        allowed_horizon=allowed_horizon,
        can_forecast=can_forecast,
        message=message,
    )


def clamp_horizon(history_points: int, *, frequency: str, horizon: int) -> int:
    return assess_history(history_points, frequency=frequency, horizon=horizon).allowed_horizon
