from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.data.history import clamp_horizon
from src.data.loader import LoadedTable, load_table_from_bytes, load_table_from_path
from src.data.mapper import ColumnMapping, suggest_mapping
from src.data.transformer import TransformResult, normalize_frame
from src.data.validator import QualityReport, build_quality_report
from src.schemas import DatasetCreate, ObservationCreate


@dataclass
class IngestPreview:
    loaded: LoadedTable
    mapping: ColumnMapping
    transform: TransformResult
    quality: QualityReport
    allowed_horizon: int


def preview_ingest(
    frame: pd.DataFrame,
    *,
    source_name: str,
    mapping: ColumnMapping,
    frequency: str,
    agg: str,
    horizon: int,
    fill_missing_as_zero: bool,
    encoding: str | None = None,
    separator: str | None = None,
    sheet_name: str | None = None,
) -> IngestPreview:
    loaded = LoadedTable(
        frame=frame,
        source_name=source_name,
        encoding=encoding,
        separator=separator,
        sheet_name=sheet_name,
    )
    transform = normalize_frame(
        frame,
        mapping,
        frequency=frequency,
        agg=agg,
        fill_missing_as_zero=fill_missing_as_zero,
    )
    quality = build_quality_report(
        transform.audited,
        transform.clean,
        frequency=frequency,
        horizon=horizon,
        fill_missing_as_zero=fill_missing_as_zero,
    )
    allowed = clamp_horizon(len(transform.clean), frequency=frequency, horizon=horizon)
    return IngestPreview(
        loaded=loaded,
        mapping=mapping,
        transform=transform,
        quality=quality,
        allowed_horizon=allowed,
    )


def preview_from_bytes(data: bytes, filename: str, **kwargs) -> tuple[LoadedTable, ColumnMapping]:
    loaded = load_table_from_bytes(data, filename)
    mapping = suggest_mapping(list(loaded.frame.columns))
    return loaded, mapping


def preview_from_path(path: str, **kwargs) -> tuple[LoadedTable, ColumnMapping]:
    loaded = load_table_from_path(path)
    mapping = suggest_mapping(list(loaded.frame.columns))
    return loaded, mapping


def to_dataset_create(
    preview: IngestPreview,
    *,
    name: str,
    target_kpi: str,
    frequency: str,
) -> DatasetCreate:
    observations = [
        ObservationCreate(
            ds=row.ds.to_pydatetime() if hasattr(row.ds, "to_pydatetime") else row.ds,
            y=float(row.y),
            series_key=str(row.series_key),
            dimensions=row.dimensions if isinstance(row.dimensions, dict) else {},
            drivers=row.drivers if isinstance(row.drivers, dict) else {},
            is_transformed=bool(row.is_transformed),
        )
        for row in preview.transform.clean.itertuples(index=False)
    ]
    status = "ready" if preview.quality.can_forecast else "limited"
    return DatasetCreate(
        name=name,
        source_filename=preview.loaded.source_name,
        frequency=frequency,
        target_kpi=target_kpi,
        column_mapping=preview.mapping.to_dict(),
        quality_report=preview.quality.to_dict(),
        status=status,
        observations=observations,
    )
