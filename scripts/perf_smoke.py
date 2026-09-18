#!/usr/bin/env python3
"""Замер импорта и прогноза на целевом объёме (синтетика ~1 год daily)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from src.data.mapper import ColumnMapping
from src.data.pipeline import preview_from_bytes, preview_ingest
from src.forecasting.service import run_forecast_job


def _make_csv(n: int = 1096) -> bytes:
    ds = pd.date_range("2022-01-01", periods=n, freq="D")
    y = 1000 + np.arange(n) * 0.5 + np.sin(np.arange(n) / 7.0) * 40
    frame = pd.DataFrame({"date": ds.strftime("%Y-%m-%d"), "revenue": y})
    return frame.to_csv(index=False).encode("utf-8")


def main() -> None:
    raw = _make_csv()
    t0 = time.perf_counter()
    loaded, mapping = preview_from_bytes(raw, "perf.csv")
    preview = preview_ingest(
        loaded.frame,
        source_name=loaded.source_name,
        mapping=mapping or ColumnMapping(date_column="date", target_column="revenue"),
        frequency="D",
        agg="sum",
        horizon=30,
        fill_missing_as_zero=False,
    )
    t_ingest = time.perf_counter() - t0

    history = preview.transform.clean[["ds", "y"]].copy()
    history["series_key"] = "default"
    t1 = time.perf_counter()
    job = run_forecast_job(
        history,
        frequency="D",
        horizon=30,
        model_choice="auto",
        include_prophet=True,
    )
    t_forecast = time.perf_counter() - t1

    print(
        {
            "rows": len(history),
            "ingest_s": round(t_ingest, 3),
            "forecast_s": round(t_forecast, 3),
            "selected_model": job.selected_model,
            "quality_status": job.quality_status,
            "sample": str(Path("sample_data/synthetic_sales.csv").exists()),
        }
    )


if __name__ == "__main__":
    main()
