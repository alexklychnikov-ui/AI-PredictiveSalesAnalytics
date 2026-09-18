from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    target_kpi: Mapped[str] = mapped_column(String(64), nullable=False)
    column_mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    quality_report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    observations: Mapped[list["SalesObservation"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    forecast_runs: Mapped[list["ForecastRun"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SalesObservation(Base):
    __tablename__ = "sales_observations"
    __table_args__ = (
        UniqueConstraint("dataset_id", "ds", "series_key", name="uq_observation_series_ds"),
        Index("ix_sales_observations_dataset_ds", "dataset_id", "ds"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ds: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    series_key: Mapped[str] = mapped_column(String(255), nullable=False, default="total")
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    drivers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_transformed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    dataset: Mapped[Dataset] = relationship(back_populates="observations")


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    __table_args__ = (Index("ix_forecast_runs_dataset_created", "dataset_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    series_key: Mapped[str] = mapped_column(String(255), nullable=False, default="total")
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    train_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    train_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    dataset: Mapped[Dataset] = relationship(back_populates="forecast_runs")
    points: Mapped[list["ForecastPoint"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    insight_reports: Mapped[list["InsightReport"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ForecastPoint(Base):
    __tablename__ = "forecast_points"
    __table_args__ = (
        Index("ix_forecast_points_run_ds", "run_id", "ds"),
        UniqueConstraint("run_id", "ds", "scenario_type", name="uq_forecast_point_scenario"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("forecast_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ds: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    yhat: Mapped[float] = mapped_column(Float, nullable=False)
    yhat_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    yhat_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    scenario_type: Mapped[str] = mapped_column(String(64), nullable=False, default="baseline")
    scenario_factors: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    run: Mapped[ForecastRun] = relationship(back_populates="points")


class InsightReport(Base):
    __tablename__ = "insight_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("forecast_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    recommendations: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="rules")
    openai_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[ForecastRun] = relationship(back_populates="insight_reports")
