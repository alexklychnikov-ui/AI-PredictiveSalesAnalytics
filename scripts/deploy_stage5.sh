#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/stage5.tar.gz
docker compose up -d --build --force-recreate app
sleep 15
docker compose exec -T app pytest tests/unit -q --tb=line
docker compose exec -T app python <<'PY'
from src.analytics.service import apply_filters, observations_to_frame
from src.db.repositories import DatasetRepository
from src.db.session import session_scope
from src.forecasting.service import run_forecast_job
from src.schemas import ForecastPointCreate, ForecastRunCreate

with session_scope() as session:
    repo = DatasetRepository(session)
    dataset = repo.list_summaries()[0]
    frame = observations_to_frame(repo.load_observations(dataset.id))
    series_key = (repo.list_series_keys(dataset.id) or ["total"])[0]
    filtered = apply_filters(frame, series_key=series_key)
    frequency = dataset.frequency
    dataset_id = dataset.id

job = run_forecast_job(
    filtered,
    frequency=frequency,
    horizon=14,
    model_choice="auto",
    include_prophet=True,
)
assert job.quality_status != "unavailable", job.unavailable_reason
assert job.forecast.points, "empty forecast"
assert "seasonal_naive" in job.backtests

from datetime import timezone

def as_utc(value):
    ts = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)

create = ForecastRunCreate(
    dataset_id=dataset_id,
    series_key=series_key,
    model_name=job.selected_model,
    model_version=job.forecast.model_version,
    train_start=as_utc(job.train_start),
    train_end=as_utc(job.train_end),
    horizon=job.horizon,
    config=job.config,
    metrics=job.metrics_payload,
    quality_status=job.quality_status,
    points=[
        ForecastPointCreate(
            ds=as_utc(p.ds),
            yhat=p.yhat,
            yhat_lower=p.yhat_lower,
            yhat_upper=p.yhat_upper,
            scenario_type="base",
        )
        for p in job.forecast.points
    ],
)
with session_scope() as session:
    run = DatasetRepository(session).save_forecast_run(create)
    run_id = run.id
    points_n = len(DatasetRepository(session).load_forecast_points(run_id))

print(
    "STAGE5_OK",
    "quality",
    job.quality_status,
    "model",
    job.selected_model,
    "horizon",
    job.horizon,
    "points",
    len(job.forecast.points),
    "run_id",
    run_id,
    "saved_points",
    points_n,
    "prophet_wape",
    (job.backtests.get("prophet").metrics.wape if job.backtests.get("prophet") else None),
    "baseline_wape",
    (job.backtests.get("seasonal_naive").metrics.wape if job.backtests.get("seasonal_naive") else None),
)
PY
echo STAGE5_DONE
