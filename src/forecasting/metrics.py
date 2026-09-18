"""Метрики качества прогноза."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class MetricSet:
    mae: float | None
    rmse: float | None
    wape: float | None
    smape: float | None
    n: int

    def to_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


def _as_arrays(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> tuple[np.ndarray, np.ndarray]:
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(yt) & np.isfinite(yp)
    return yt[mask], yp[mask]


def mae(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> float | None:
    yt, yp = _as_arrays(y_true, y_pred)
    if yt.size == 0:
        return None
    return float(np.mean(np.abs(yt - yp)))


def rmse(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> float | None:
    yt, yp = _as_arrays(y_true, y_pred)
    if yt.size == 0:
        return None
    return float(np.sqrt(np.mean((yt - yp) ** 2)))


def wape(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> float | None:
    yt, yp = _as_arrays(y_true, y_pred)
    if yt.size == 0:
        return None
    denom = float(np.sum(np.abs(yt)))
    if denom == 0.0:
        return None
    return float(np.sum(np.abs(yt - yp)) / denom * 100.0)


def smape(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> float | None:
    yt, yp = _as_arrays(y_true, y_pred)
    if yt.size == 0:
        return None
    denom = np.abs(yt) + np.abs(yp)
    valid = denom > 0
    if not np.any(valid):
        return None
    return float(np.mean(2.0 * np.abs(yt[valid] - yp[valid]) / denom[valid]) * 100.0)


def compute_metrics(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> MetricSet:
    yt, yp = _as_arrays(y_true, y_pred)
    return MetricSet(
        mae=mae(yt, yp),
        rmse=rmse(yt, yp),
        wape=wape(yt, yp),
        smape=smape(yt, yp),
        n=int(yt.size),
    )
