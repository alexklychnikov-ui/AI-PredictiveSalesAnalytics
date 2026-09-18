"""initial schema

Revision ID: 20260918_0001
Revises:
Create Date: 2026-09-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260918_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=True),
        sa.Column("frequency", sa.String(length=16), nullable=False),
        sa.Column("target_kpi", sa.String(length=64), nullable=False),
        sa.Column("column_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quality_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sales_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("ds", sa.DateTime(timezone=True), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("series_key", sa.String(length=255), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("drivers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_transformed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "ds", "series_key", name="uq_observation_series_ds"),
    )
    op.create_index("ix_sales_observations_dataset_id", "sales_observations", ["dataset_id"])
    op.create_index("ix_sales_observations_dataset_ds", "sales_observations", ["dataset_id", "ds"])

    op.create_table(
        "forecast_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("series_key", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("train_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("train_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forecast_runs_dataset_id", "forecast_runs", ["dataset_id"])
    op.create_index("ix_forecast_runs_dataset_created", "forecast_runs", ["dataset_id", "created_at"])

    op.create_table(
        "forecast_points",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ds", sa.DateTime(timezone=True), nullable=False),
        sa.Column("yhat", sa.Float(), nullable=False),
        sa.Column("yhat_lower", sa.Float(), nullable=True),
        sa.Column("yhat_upper", sa.Float(), nullable=True),
        sa.Column("scenario_type", sa.String(length=64), nullable=False),
        sa.Column("scenario_factors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["forecast_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "ds", "scenario_type", name="uq_forecast_point_scenario"),
    )
    op.create_index("ix_forecast_points_run_id", "forecast_points", ["run_id"])
    op.create_index("ix_forecast_points_run_ds", "forecast_points", ["run_id", "ds"])

    op.create_table(
        "insight_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recommendations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("openai_model", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["forecast_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insight_reports_run_id", "insight_reports", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_insight_reports_run_id", table_name="insight_reports")
    op.drop_table("insight_reports")
    op.drop_index("ix_forecast_points_run_ds", table_name="forecast_points")
    op.drop_index("ix_forecast_points_run_id", table_name="forecast_points")
    op.drop_table("forecast_points")
    op.drop_index("ix_forecast_runs_dataset_created", table_name="forecast_runs")
    op.drop_index("ix_forecast_runs_dataset_id", table_name="forecast_runs")
    op.drop_table("forecast_runs")
    op.drop_index("ix_sales_observations_dataset_ds", table_name="sales_observations")
    op.drop_index("ix_sales_observations_dataset_id", table_name="sales_observations")
    op.drop_table("sales_observations")
    op.drop_table("datasets")
