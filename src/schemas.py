from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ObservationCreate(BaseModel):
    ds: datetime
    y: float
    series_key: str = "total"
    dimensions: dict[str, Any] = Field(default_factory=dict)
    drivers: dict[str, Any] = Field(default_factory=dict)
    is_transformed: bool = False


class DatasetCreate(BaseModel):
    name: str
    source_filename: str | None = None
    frequency: str
    target_kpi: str
    column_mapping: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)
    status: str = "ready"
    observations: list[ObservationCreate] = Field(default_factory=list)


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_filename: str | None
    frequency: str
    target_kpi: str
    column_mapping: dict[str, Any]
    quality_report: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    observations_count: int = 0


class ForecastPointCreate(BaseModel):
    ds: datetime
    yhat: float
    yhat_lower: float | None = None
    yhat_upper: float | None = None
    scenario_type: str = "base"
    scenario_factors: dict[str, Any] = Field(default_factory=dict)


class ForecastRunCreate(BaseModel):
    dataset_id: int
    series_key: str = "total"
    model_name: str
    model_version: str | None = None
    train_start: datetime | None = None
    train_end: datetime | None = None
    horizon: int
    config: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    quality_status: str = "unknown"
    points: list[ForecastPointCreate] = Field(default_factory=list)


class ForecastRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    series_key: str
    model_name: str
    model_version: str | None
    train_start: datetime | None
    train_end: datetime | None
    horizon: int
    config: dict[str, Any]
    metrics: dict[str, Any]
    quality_status: str
    created_at: datetime
    points_count: int = 0
