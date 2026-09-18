from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd


@dataclass(frozen=True)
class LoadedTable:
    frame: pd.DataFrame
    source_name: str
    encoding: str | None
    separator: str | None
    sheet_name: str | None


def _read_csv_bytes(data: bytes, separator: str | None = None) -> tuple[pd.DataFrame, str, str]:
    encodings = ("utf-8-sig", "utf-8", "cp1251", "latin-1")
    separators = [separator] if separator else [",", ";", "\t", "|"]
    last_error: Exception | None = None
    for encoding in encodings:
        for sep in separators:
            try:
                frame = pd.read_csv(BytesIO(data), sep=sep, encoding=encoding)
                if frame.shape[1] >= 2:
                    return frame, encoding, sep
            except Exception as exc:  # noqa: BLE001
                last_error = exc
    raise ValueError(f"Не удалось прочитать CSV: {last_error}")


def load_table_from_bytes(
    data: bytes,
    filename: str,
    *,
    separator: str | None = None,
    sheet_name: str | int | None = 0,
) -> LoadedTable:
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        try:
            frame = pd.read_excel(BytesIO(data), sheet_name=sheet_name)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Не удалось прочитать Excel: {exc}") from exc
        if isinstance(frame, dict):
            first_key = next(iter(frame))
            frame = frame[first_key]
            sheet = str(first_key)
        else:
            sheet = str(sheet_name)
        if frame is None or getattr(frame, "empty", False):
            raise ValueError("Excel-файл пуст или не содержит таблиц")
        return LoadedTable(
            frame=frame,
            source_name=filename,
            encoding=None,
            separator=None,
            sheet_name=sheet,
        )

    if name.endswith(".csv") or "." not in name:
        frame, encoding, sep = _read_csv_bytes(data, separator=separator)
        return LoadedTable(
            frame=frame,
            source_name=filename,
            encoding=encoding,
            separator=sep,
            sheet_name=None,
        )

    raise ValueError("Поддерживаются только CSV и XLSX")


def load_table_from_path(path: str | Path, **kwargs) -> LoadedTable:
    file_path = Path(path)
    return load_table_from_bytes(file_path.read_bytes(), file_path.name, **kwargs)


def load_table_from_upload(file_obj: BinaryIO, filename: str, **kwargs) -> LoadedTable:
    return load_table_from_bytes(file_obj.read(), filename, **kwargs)
