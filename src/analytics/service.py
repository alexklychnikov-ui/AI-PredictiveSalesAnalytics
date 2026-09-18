from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.analytics.anomalies import AnomalySummary, detect_anomalies
from src.analytics.correlations import CorrelationSummary, compute_correlations
from src.analytics.kpi import KpiSummary, compute_kpi
from src.analytics.seasonality import SeasonalitySummary, compute_seasonality
from src.analytics.trends import TrendSummary, compute_trend


@dataclass
class AnalyticsReport:
    kpi: KpiSummary
    trend: TrendSummary
    seasonality: SeasonalitySummary
    anomalies: AnomalySummary
    correlations: CorrelationSummary
    category_contribution: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kpi": self.kpi.to_dict(),
            "trend": self.trend.to_dict(),
            "seasonality": self.seasonality.to_dict(),
            "anomalies": self.anomalies.to_dict(),
            "correlations": self.correlations.to_dict(),
            "category_contribution": self.category_contribution,
        }


def observations_to_frame(rows: list[Any]) -> pd.DataFrame:
    records = []
    for row in rows:
        record = {
            "ds": pd.Timestamp(row.ds),
            "y": float(row.y),
            "series_key": row.series_key,
        }
        dimensions = row.dimensions or {}
        drivers = row.drivers or {}
        for key, value in dimensions.items():
            record[f"dim_{key}"] = value
        for key, value in drivers.items():
            record[key] = value
        records.append(record)
    if not records:
        return pd.DataFrame(columns=["ds", "y", "series_key"])
    frame = pd.DataFrame.from_records(records)
    frame["ds"] = pd.to_datetime(frame["ds"], utc=True)
    return frame.sort_values("ds").reset_index(drop=True)


def apply_filters(
    frame: pd.DataFrame,
    *,
    series_key: str | None = None,
    dimension_filters: dict[str, str] | None = None,
) -> pd.DataFrame:
    result = frame.copy()
    if series_key and "series_key" in result.columns:
        result = result[result["series_key"] == series_key]
    if dimension_filters:
        for key, value in dimension_filters.items():
            col = f"dim_{key}" if f"dim_{key}" in result.columns else key
            if col in result.columns:
                result = result[result[col].astype(str) == str(value)]
    return result.reset_index(drop=True)


def _category_contribution(frame: pd.DataFrame) -> list[dict[str, Any]]:
    col = None
    for candidate in ("dim_category", "category"):
        if candidate in frame.columns:
            col = candidate
            break
    if col is None or frame.empty:
        return []
    grouped = (
        frame.groupby(col, dropna=False)["y"]
        .sum()
        .sort_values(ascending=False)
    )
    total = float(grouped.sum()) or 1.0
    top = grouped.head(15)
    return [
        {"category": str(idx), "total": float(val), "share_pct": float(val / total * 100.0)}
        for idx, val in top.items()
    ]


def build_analytics_report(frame: pd.DataFrame, *, frequency: str = "D") -> AnalyticsReport:
    numeric_drivers = [
        col
        for col in frame.columns
        if col not in {"ds", "y", "series_key"}
        and not str(col).startswith("dim_")
        and pd.api.types.is_numeric_dtype(frame[col])
    ]
    return AnalyticsReport(
        kpi=compute_kpi(frame, frequency=frequency),
        trend=compute_trend(frame, frequency=frequency),
        seasonality=compute_seasonality(frame, frequency=frequency),
        anomalies=detect_anomalies(frame),
        correlations=compute_correlations(frame, numeric_drivers),
        category_contribution=_category_contribution(frame),
    )
