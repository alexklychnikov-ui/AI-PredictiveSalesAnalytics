"""Data ingestion package."""

from src.data.history import HistoryAssessment, assess_history, clamp_horizon
from src.data.loader import LoadedTable, load_table_from_bytes, load_table_from_path
from src.data.mapper import ColumnMapping, suggest_mapping
from src.data.pipeline import IngestPreview, preview_ingest, to_dataset_create
from src.data.transformer import TransformResult, normalize_frame
from src.data.validator import QualityReport, build_quality_report

__all__ = [
    "ColumnMapping",
    "HistoryAssessment",
    "IngestPreview",
    "LoadedTable",
    "QualityReport",
    "TransformResult",
    "assess_history",
    "build_quality_report",
    "clamp_horizon",
    "load_table_from_bytes",
    "load_table_from_path",
    "normalize_frame",
    "preview_ingest",
    "suggest_mapping",
    "to_dataset_create",
]
