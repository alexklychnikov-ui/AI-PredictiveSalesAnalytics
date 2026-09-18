"""Проверки допустимости факторов для сценариев."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

KNOWN_FACTORS = (
    "unit_price",
    "discount_pct",
    "promo_flag",
    "marketing_spend",
)

PROFIT_FIELDS = ("margin_pct", "unit_cost", "cost", "gross_margin")

MIN_NON_NULL = 30
MIN_UNIQUE_OPTIMIZE = 3


@dataclass
class FactorEligibility:
    factor: str
    eligible: bool
    n_non_null: int
    n_unique: int
    std: float | None
    min_value: float | None
    max_value: float | None
    mean_value: float | None
    can_optimize_levels: bool
    confidence: str  # низкая | средняя | высокая
    reasons: list[str] = field(default_factory=list)
    missing_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_factor_columns(frame: pd.DataFrame) -> list[str]:
    cols = []
    for col in frame.columns:
        if col in {"ds", "y", "series_key"} or str(col).startswith("dim_"):
            continue
        if col in KNOWN_FACTORS or col in PROFIT_FIELDS:
            cols.append(col)
            continue
        if pd.api.types.is_numeric_dtype(frame[col]):
            cols.append(col)
    # приоритет известных
    ordered = [c for c in KNOWN_FACTORS if c in cols]
    ordered.extend([c for c in cols if c not in ordered and c not in PROFIT_FIELDS])
    return ordered


def assess_factor(frame: pd.DataFrame, factor: str) -> FactorEligibility:
    if factor not in frame.columns:
        return FactorEligibility(
            factor=factor,
            eligible=False,
            n_non_null=0,
            n_unique=0,
            std=None,
            min_value=None,
            max_value=None,
            mean_value=None,
            can_optimize_levels=False,
            confidence="низкая",
            reasons=["Фактор отсутствует в данных"],
            missing_hint=f"Начните собирать колонку «{factor}»",
        )

    series = pd.to_numeric(frame[factor], errors="coerce")
    valid = series.dropna()
    n_non_null = int(valid.shape[0])
    n_unique = int(valid.nunique())
    std = float(valid.std()) if n_non_null > 1 else 0.0
    min_v = float(valid.min()) if n_non_null else None
    max_v = float(valid.max()) if n_non_null else None
    mean_v = float(valid.mean()) if n_non_null else None
    reasons: list[str] = []

    if n_non_null < MIN_NON_NULL:
        reasons.append(f"Мало наблюдений: {n_non_null} < {MIN_NON_NULL}")
    if n_unique < 2 or std is None or std <= 1e-12:
        reasons.append("Фактор почти константа — эффект оценить нельзя")
    if factor == "promo_flag" and n_unique < 2:
        reasons.append("Нужны оба состояния акции (0 и 1)")
    if factor == "discount_pct" and n_unique < 2:
        reasons.append("Скидка не менялась")

    eligible = len(reasons) == 0
    can_optimize = eligible and n_unique >= MIN_UNIQUE_OPTIMIZE
    if factor == "discount_pct" and eligible and not can_optimize:
        reasons.append(
            f"Оптимизация размера скидки недоступна: уникальных уровней {n_unique} < {MIN_UNIQUE_OPTIMIZE}"
        )

    if n_non_null >= 120 and std and std > 0 and n_unique >= 3:
        confidence = "высокая"
    elif n_non_null >= MIN_NON_NULL and eligible:
        confidence = "средняя"
    else:
        confidence = "низкая"

    return FactorEligibility(
        factor=factor,
        eligible=eligible,
        n_non_null=n_non_null,
        n_unique=n_unique,
        std=std,
        min_value=min_v,
        max_value=max_v,
        mean_value=mean_v,
        can_optimize_levels=can_optimize,
        confidence=confidence,
        reasons=reasons,
    )


def assess_all_factors(frame: pd.DataFrame) -> list[FactorEligibility]:
    return [assess_factor(frame, name) for name in discover_factor_columns(frame)]


def profit_data_status(frame: pd.DataFrame) -> dict[str, Any]:
    def _non_null(col: str) -> int:
        return int(pd.to_numeric(frame[col], errors="coerce").dropna().shape[0])

    if "margin_pct" in frame.columns and _non_null("margin_pct") >= 10:
        return {"available": True, "mode": "margin", "fields": ["margin_pct"], "n": _non_null("margin_pct")}
    if "gross_margin" in frame.columns and _non_null("gross_margin") >= 10:
        return {"available": True, "mode": "margin", "fields": ["gross_margin"], "n": _non_null("gross_margin")}
    cost_col = "unit_cost" if "unit_cost" in frame.columns else ("cost" if "cost" in frame.columns else None)
    if cost_col and "unit_price" in frame.columns and _non_null(cost_col) >= 10 and _non_null("unit_price") >= 10:
        return {
            "available": True,
            "mode": "cost_price",
            "fields": [cost_col, "unit_price"],
            "n": min(_non_null(cost_col), _non_null("unit_price")),
        }
    if cost_col and _non_null(cost_col) >= 1 and "unit_price" not in frame.columns:
        return {
            "available": False,
            "mode": None,
            "fields": [cost_col],
            "missing": ["unit_price"],
            "hint": "Для прибыли нужны unit_cost/cost и unit_price",
        }
    return {
        "available": False,
        "mode": None,
        "fields": [],
        "missing": list(PROFIT_FIELDS),
        "hint": "Для profit/ROI начните собирать margin_pct или unit_cost+unit_price",
    }


def check_range(
    value: float,
    eligibility: FactorEligibility,
    *,
    stretch: float = 0.1,
) -> dict[str, Any]:
    if eligibility.min_value is None or eligibility.max_value is None:
        return {"ok": False, "warning": "Нет исторического диапазона"}
    lo = eligibility.min_value
    hi = eligibility.max_value
    span = hi - lo
    soft_lo = lo - stretch * span
    soft_hi = hi + stretch * span
    if value < lo or value > hi:
        if value < soft_lo or value > soft_hi:
            return {
                "ok": False,
                "warning": (
                    f"Значение {value:.4g} далеко за историческим диапазоном "
                    f"[{lo:.4g}, {hi:.4g}]"
                ),
            }
        return {
            "ok": True,
            "warning": (
                f"Значение {value:.4g} вне строгого диапазона [{lo:.4g}, {hi:.4g}] — "
                "экстраполяция, уверенность ниже"
            ),
        }
    return {"ok": True, "warning": None}
