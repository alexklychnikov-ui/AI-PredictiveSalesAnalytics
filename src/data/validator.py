from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from src.data.history import HistoryAssessment, assess_history


@dataclass
class QualityReport:
    rows_raw: int
    rows_clean: int
    date_parse_errors: int
    target_parse_errors: int
    duplicate_timestamps: int
    missing_periods: int
    zero_share: float
    negative_count: int
    constant_series: bool
    outlier_count: int
    future_dates: int
    non_zero_count: int
    history: HistoryAssessment
    warnings: list[str]
    can_forecast: bool

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["history"] = asdict(self.history)
        return payload


def _mad_outlier_mask(series: pd.Series) -> pd.Series:
    values = series.astype(float)
    median = values.median()
    mad = np.median(np.abs(values - median))
    if mad == 0 or np.isnan(mad):
        return pd.Series(False, index=series.index)
    modified_z = 0.6745 * (values - median) / mad
    return modified_z.abs() > 3.5


def build_quality_report(
    raw_df: pd.DataFrame,
    clean_df: pd.DataFrame,
    *,
    frequency: str,
    horizon: int,
    fill_missing_as_zero: bool,
) -> QualityReport:
    warnings: list[str] = []
    history = assess_history(len(clean_df), frequency=frequency, horizon=horizon)

    date_errors = int(raw_df.get("_date_error", pd.Series(dtype=bool)).fillna(False).sum()) if "_date_error" in raw_df else 0
    target_errors = (
        int(raw_df.get("_target_error", pd.Series(dtype=bool)).fillna(False).sum()) if "_target_error" in raw_df else 0
    )
    duplicate_timestamps = int(raw_df.get("_duplicate", pd.Series(dtype=bool)).fillna(False).sum()) if "_duplicate" in raw_df else 0
    missing_periods = int(raw_df.attrs.get("missing_periods", 0))
    future_dates = int((clean_df["ds"] > pd.Timestamp.now(tz="UTC")).sum()) if len(clean_df) else 0

    y = clean_df["y"] if len(clean_df) else pd.Series(dtype=float)
    zero_share = float((y == 0).mean()) if len(y) else 0.0
    negative_count = int((y < 0).sum()) if len(y) else 0
    constant_series = bool(y.nunique(dropna=True) <= 1) if len(y) else True
    outlier_count = int(_mad_outlier_mask(y).sum()) if len(y) >= 8 else 0
    non_zero_count = int((y != 0).sum()) if len(y) else 0

    if date_errors:
        warnings.append(f"Нераспознанных дат: {date_errors}")
    if target_errors:
        warnings.append(f"Нераспознанных значений target: {target_errors}")
    if duplicate_timestamps:
        warnings.append(f"Дубликатов по дате до агрегации: {duplicate_timestamps}")
    if missing_periods and not fill_missing_as_zero:
        warnings.append(f"Пропусков в календаре: {missing_periods} (не заполнены нулями)")
    if missing_periods and fill_missing_as_zero:
        warnings.append(f"Пропусков заполнено нулями: {missing_periods}")
    if zero_share > 0.4:
        warnings.append(f"Высокая доля нулей: {zero_share:.0%}")
    if negative_count:
        warnings.append(f"Отрицательных значений: {negative_count}")
    if constant_series:
        warnings.append("Ряд почти постоянный — прогноз будет слабым")
    if outlier_count:
        warnings.append(f"Потенциальных выбросов (MAD): {outlier_count}")
    if future_dates:
        warnings.append(f"Будущих дат в истории: {future_dates}")
    if history.status != "достаточно":
        warnings.append(history.message)

    can_forecast = history.can_forecast and not constant_series and len(clean_df) >= 3

    return QualityReport(
        rows_raw=len(raw_df),
        rows_clean=len(clean_df),
        date_parse_errors=date_errors,
        target_parse_errors=target_errors,
        duplicate_timestamps=duplicate_timestamps,
        missing_periods=missing_periods,
        zero_share=zero_share,
        negative_count=negative_count,
        constant_series=constant_series,
        outlier_count=outlier_count,
        future_dates=future_dates,
        non_zero_count=non_zero_count,
        history=history,
        warnings=warnings,
        can_forecast=can_forecast,
    )
