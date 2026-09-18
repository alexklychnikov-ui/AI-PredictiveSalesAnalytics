"""Подписи таблиц для UI (внутренние коды → русский)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.ui.labels import OPTIONAL_FACTOR_LABELS, label_or_raw

POINT_COL_LABELS = {
    "ds": "дата",
    "y": "значение",
    "yhat": "прогноз",
    "yhat_lower": "нижняя граница",
    "yhat_upper": "верхняя граница",
    "score": "насколько необычно",
}

METRIC_COL_LABELS = {
    "модель": "модель",
    "MAE": "средняя ошибка (MAE)",
    "RMSE": "ошибка RMSE",
    "WAPE %": "ошибка WAPE, %",
    "sMAPE %": "ошибка sMAPE, %",
    "folds": "проверок",
}


def factor_label(code: str) -> str:
    return label_or_raw(OPTIONAL_FACTOR_LABELS, code)


def rename_records(rows: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append({mapping.get(k, k): v for k, v in row.items()})
    return out


def rename_frame(frame: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    return frame.rename(columns={k: v for k, v in mapping.items() if k in frame.columns})
