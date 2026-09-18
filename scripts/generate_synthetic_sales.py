#!/usr/bin/env python3
"""Generate synthetic daily sales with trend, seasonality, promo, ads, outliers, stockouts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sample_data" / "synthetic_sales.csv"


def main() -> None:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2023-01-01", "2025-12-31", freq="D")
    n = len(dates)
    t = np.arange(n)

    trend = 800 + 0.35 * t
    yearly = 120 * np.sin(2 * np.pi * t / 365.25)
    weekly = 80 * np.sin(2 * np.pi * dates.dayofweek / 7)
    noise = rng.normal(0, 40, n)

    promo_flag = ((dates.day == 15) | (dates.day == 16) | (dates.month == 11)).astype(int)
    discount_pct = np.where(promo_flag == 1, rng.choice([5, 10, 15, 20], size=n), 0)
    marketing_spend = np.where(promo_flag == 1, rng.uniform(200, 800, n), rng.uniform(20, 80, n))
    stockout_flag = (rng.random(n) < 0.02).astype(int)

    revenue = trend + yearly + weekly + noise
    revenue = revenue * (1 + 0.004 * discount_pct) + 0.05 * marketing_spend
    revenue = np.where(stockout_flag == 1, revenue * 0.25, revenue)

    # inject a few outliers
    outlier_idx = rng.choice(n, size=8, replace=False)
    revenue[outlier_idx] *= rng.choice([0.2, 2.5], size=8)

    frame = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "revenue": np.round(np.maximum(revenue, 0), 2),
            "discount_pct": discount_pct,
            "promo_flag": promo_flag,
            "marketing_spend": np.round(marketing_spend, 2),
            "stockout_flag": stockout_flag,
            "category": rng.choice(["A", "B", "C"], size=n),
        }
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT, index=False)
    print(f"Wrote {OUT} rows={len(frame)}")


if __name__ == "__main__":
    main()
