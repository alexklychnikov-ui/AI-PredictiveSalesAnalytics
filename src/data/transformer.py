from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.data.mapper import ColumnMapping

AGG_FUNCS = {
    "sum": "sum",
    "mean": "mean",
    "median": "median",
    "min": "min",
    "max": "max",
    "count": "count",
}

FREQ_RULES = {
    "D": "D",
    "W": "W-MON",
    "M": "MS",
}


@dataclass
class TransformResult:
    clean: pd.DataFrame
    audited: pd.DataFrame
    missing_periods: int


def _to_utc_timestamp(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    errors = parsed.isna() & series.notna()
    return parsed, errors


def _reduce_optional(tmp: pd.DataFrame, logical: str) -> pd.DataFrame:
    if logical.endswith("_flag") or logical in {"discount_pct", "marketing_spend", "unit_price"}:
        return tmp.groupby("ds", as_index=False)[logical].mean()
    return tmp.groupby("ds", as_index=False)[logical].agg(
        lambda s: s.mode().iloc[0] if len(s.mode()) else s.iloc[0]
    )


def normalize_frame(
    frame: pd.DataFrame,
    mapping: ColumnMapping,
    *,
    frequency: str = "D",
    agg: str = "sum",
    fill_missing_as_zero: bool = False,
) -> TransformResult:
    if mapping.date_column not in frame.columns or mapping.target_column not in frame.columns:
        raise ValueError("Выбранные колонки date/target отсутствуют в данных")
    if agg not in AGG_FUNCS:
        raise ValueError(f"Неизвестный способ агрегации: {agg}")
    if frequency not in FREQ_RULES:
        raise ValueError("frequency must be D, W or M")

    work = frame.copy()
    ds, date_errors = _to_utc_timestamp(work[mapping.date_column])
    y = pd.to_numeric(work[mapping.target_column], errors="coerce")
    target_errors = y.isna() & work[mapping.target_column].notna()

    work["ds"] = ds
    work["y"] = y
    work["_date_error"] = date_errors
    work["_target_error"] = target_errors

    optional_frames: dict[str, pd.Series] = {}
    for logical, source_col in mapping.optional_columns.items():
        if source_col not in work.columns:
            continue
        series = work[source_col]
        if logical.endswith("_flag"):
            optional_frames[logical] = pd.to_numeric(series, errors="coerce").fillna(0).clip(0, 1)
        elif logical in {"discount_pct", "marketing_spend", "unit_price"}:
            optional_frames[logical] = pd.to_numeric(series, errors="coerce")
        else:
            optional_frames[logical] = series.where(series.notna(), other=pd.NA).astype("string")

    valid = work.dropna(subset=["ds", "y"]).copy()
    if valid.empty:
        empty = pd.DataFrame(columns=["ds", "y", "series_key", "dimensions", "drivers", "is_transformed"])
        audited = work.copy()
        audited["_duplicate"] = False
        audited.attrs["missing_periods"] = 0
        return TransformResult(clean=empty, audited=audited, missing_periods=0)

    dup_counts = valid["ds"].value_counts()
    work["_duplicate"] = work["ds"].map(dup_counts).fillna(0).astype(int) > 1

    grouped = valid.groupby("ds", as_index=False).agg(y=( "y", AGG_FUNCS[agg]))
    for logical, series in optional_frames.items():
        tmp = pd.DataFrame({"ds": valid["ds"], logical: series.loc[valid.index]})
        grouped = grouped.merge(_reduce_optional(tmp, logical), on="ds", how="left")

    grouped = grouped.sort_values("ds").set_index("ds")
    rule = FREQ_RULES[frequency]

    # aggregate to target frequency; empty buckets must stay NaN (sum would become 0)
    resampled = grouped.resample(rule)
    counts = resampled["y"].count()
    if agg == "count":
        # y already holds per-timestamp event counts from the first groupby
        y_agg = resampled["y"].sum()
    else:
        y_agg = getattr(resampled["y"], AGG_FUNCS[agg])()
    clean = y_agg.to_frame(name="y")
    clean.loc[counts == 0, "y"] = pd.NA
    for logical in optional_frames:
        if logical not in grouped.columns:
            continue
        if logical.endswith("_flag") or logical in {"discount_pct", "marketing_spend", "unit_price"}:
            clean[logical] = resampled[logical].mean()
        else:
            clean[logical] = resampled[logical].first()
        clean.loc[counts == 0, logical] = pd.NA

    observed = clean.dropna(subset=["y"]).copy()
    if observed.empty:
        work.attrs["missing_periods"] = 0
        empty = pd.DataFrame(columns=["ds", "y", "series_key", "dimensions", "drivers", "is_transformed"])
        return TransformResult(clean=empty, audited=work, missing_periods=0)

    full_index = pd.date_range(observed.index.min(), observed.index.max(), freq=rule, tz="UTC")
    missing_periods = int((~full_index.isin(observed.index)).sum())
    clean = observed.reindex(full_index)

    if fill_missing_as_zero:
        clean["y"] = clean["y"].fillna(0.0)
        for logical in list(optional_frames):
            if logical in clean.columns and logical.endswith("_flag"):
                clean[logical] = clean[logical].fillna(0.0)
    else:
        clean = clean.dropna(subset=["y"])

    clean = clean.reset_index(names="ds")
    clean["series_key"] = "total"
    clean["dimensions"] = [{} for _ in range(len(clean))]
    drivers = []
    for _, row in clean.iterrows():
        driver = {}
        for logical in optional_frames:
            if logical in clean.columns and pd.notna(row[logical]):
                value = row[logical]
                if value is pd.NA or str(value).lower() == "nan":
                    continue
                driver[logical] = float(value) if isinstance(value, (int, float)) else str(value)
        drivers.append(driver)
    clean["drivers"] = drivers
    clean["is_transformed"] = True
    clean = clean[["ds", "y", "series_key", "dimensions", "drivers", "is_transformed"]]

    work.attrs["missing_periods"] = missing_periods
    return TransformResult(clean=clean, audited=work, missing_periods=missing_periods)
