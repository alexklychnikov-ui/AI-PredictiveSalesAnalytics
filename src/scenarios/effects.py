"""Оценка эффекта фактора по регрессии + сравнение с/без фактора."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from src.forecasting.interface import ForecastPointOut
from src.forecasting.metrics import mae
from src.scenarios.eligibility import FactorEligibility, check_range


@dataclass
class FactorEffectModel:
    factor: str
    coefficient: float
    intercept: float
    baseline_value: float
    mae_with: float | None
    mae_without: float | None
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    n_train: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FactorScenarioResult:
    factor: str
    scenario_value: float
    baseline_value: float
    effect_per_unit: float
    delta_total: float
    points: list[ForecastPointOut]
    range_check: dict[str, Any]
    model: FactorEffectModel
    scenario_type: str
    disclaimer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "scenario_value": self.scenario_value,
            "baseline_value": self.baseline_value,
            "effect_per_unit": self.effect_per_unit,
            "delta_total": self.delta_total,
            "range_check": self.range_check,
            "model": self.model.to_dict(),
            "scenario_type": self.scenario_type,
            "disclaimer": self.disclaimer,
            "total": float(sum(p.yhat for p in self.points)),
            "points": [
                {
                    "ds": str(p.ds),
                    "yhat": p.yhat,
                    "yhat_lower": p.yhat_lower,
                    "yhat_upper": p.yhat_upper,
                }
                for p in self.points
            ],
        }


_DISCLAIMER = (
    "Оценка «что если» по истории продаж: насколько фактор обычно шёл вместе с показателем. "
    "Это не доказательство причины. Сценарий показывается только если учёт фактора "
    "не ухудшает прогноз на проверочном отрезке."
)


def _ols_multi(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def fit_factor_effect(
    history: pd.DataFrame,
    factor: str,
    *,
    eligibility: FactorEligibility | None = None,
) -> FactorEffectModel:
    reasons: list[str] = []
    if eligibility is not None and not eligibility.eligible:
        return FactorEffectModel(
            factor=factor,
            coefficient=0.0,
            intercept=0.0,
            baseline_value=0.0,
            mae_with=None,
            mae_without=None,
            allowed=False,
            reasons=list(eligibility.reasons),
        )

    frame = history[["ds", "y", factor]].copy()
    frame[factor] = pd.to_numeric(frame[factor], errors="coerce")
    frame = frame.dropna().sort_values("ds").reset_index(drop=True)
    if len(frame) < 30:
        return FactorEffectModel(
            factor=factor,
            coefficient=0.0,
            intercept=0.0,
            baseline_value=0.0,
            mae_with=None,
            mae_without=None,
            allowed=False,
            reasons=["Недостаточно строк после очистки"],
        )

    y = frame["y"].to_numpy(dtype=float)
    x = frame[factor].to_numpy(dtype=float)
    t = np.arange(len(frame), dtype=float)
    split = max(20, int(len(frame) * 0.8))
    if split >= len(frame) - 5:
        split = len(frame) - 5

    idx_train = np.arange(0, split)
    idx_test = np.arange(split, len(frame))
    ones_tr = np.ones(len(idx_train))
    ones_te = np.ones(len(idx_test))
    X_with_tr = np.column_stack([ones_tr, t[idx_train], x[idx_train]])
    X_with_te = np.column_stack([ones_te, t[idx_test], x[idx_test]])
    X_wo_tr = np.column_stack([ones_tr, t[idx_train]])
    X_wo_te = np.column_stack([ones_te, t[idx_test]])

    beta_with = _ols_multi(X_with_tr, y[idx_train])
    beta_wo = _ols_multi(X_wo_tr, y[idx_train])
    pred_with = X_with_te @ beta_with
    pred_without = X_wo_te @ beta_wo

    mae_with = mae(y[idx_test], pred_with)
    mae_without = mae(y[idx_test], pred_without)

    allowed = True
    if mae_with is None or mae_without is None:
        allowed = False
        reasons.append("Не удалось сравнить модели с/без фактора")
    elif mae_without is not None and mae_with > mae_without * 1.05 + 1e-9:
        allowed = False
        reasons.append(
            f"С фактором ошибка больше, чем без него "
            f"({mae_with:.3f} > {mae_without:.3f}) — сценарий не применяем"
        )

    baseline = float(frame[factor].iloc[-1])
    coef = float(beta_with[2]) if len(beta_with) > 2 else 0.0
    intercept = float(beta_with[0])

    if allowed:
        X_full = np.column_stack([np.ones(len(frame)), t, x])
        beta_full = _ols_multi(X_full, y)
        coef = float(beta_full[2])
        intercept = float(beta_full[0])

    return FactorEffectModel(
        factor=factor,
        coefficient=coef,
        intercept=intercept,
        baseline_value=baseline,
        mae_with=mae_with,
        mae_without=mae_without,
        allowed=allowed,
        reasons=reasons,
        n_train=len(frame),
    )


def apply_factor_scenario(
    base_points: list[ForecastPointOut],
    history: pd.DataFrame,
    *,
    factor: str,
    scenario_value: float,
    eligibility: FactorEligibility,
    clip_negative: bool = True,
) -> FactorScenarioResult:
    model = fit_factor_effect(history, factor, eligibility=eligibility)
    range_check = check_range(scenario_value, eligibility)
    if not model.allowed:
        return FactorScenarioResult(
            factor=factor,
            scenario_value=scenario_value,
            baseline_value=model.baseline_value,
            effect_per_unit=0.0,
            delta_total=0.0,
            points=list(base_points),
            range_check=range_check,
            model=model,
            scenario_type=f"factor_{factor}",
            disclaimer=_DISCLAIMER,
        )

    delta = model.coefficient * (scenario_value - model.baseline_value)
    points: list[ForecastPointOut] = []
    for p in base_points:
        yhat = float(p.yhat) + delta
        lower = None if p.yhat_lower is None else float(p.yhat_lower) + delta
        upper = None if p.yhat_upper is None else float(p.yhat_upper) + delta
        if clip_negative:
            yhat = max(0.0, yhat)
            if lower is not None:
                lower = max(0.0, lower)
            if upper is not None:
                upper = max(0.0, upper)
        points.append(
            ForecastPointOut(ds=pd.Timestamp(p.ds), yhat=yhat, yhat_lower=lower, yhat_upper=upper)
        )
    return FactorScenarioResult(
        factor=factor,
        scenario_value=scenario_value,
        baseline_value=model.baseline_value,
        effect_per_unit=model.coefficient,
        delta_total=float(delta * len(points)),
        points=points,
        range_check=range_check,
        model=model,
        scenario_type=f"factor_{factor}",
        disclaimer=_DISCLAIMER,
    )
