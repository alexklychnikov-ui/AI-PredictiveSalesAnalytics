#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/stage5_fix.tar.gz
docker compose up -d --build --force-recreate app
sleep 12
docker compose exec -T app pytest tests/unit/test_forecasting.py -q
docker compose exec -T app python <<'PY'
from src.analytics.service import apply_filters, observations_to_frame
from src.db.repositories import DatasetRepository
from src.db.session import session_scope
from src.forecasting.service import run_forecast_job

with session_scope() as session:
    repo = DatasetRepository(session)
    ds = repo.list_summaries()[0]
    frame = observations_to_frame(repo.load_observations(ds.id))
    sk = (repo.list_series_keys(ds.id) or ["total"])[0]
    filtered = apply_filters(frame, series_key=sk)
    freq = ds.frequency

job = run_forecast_job(filtered, frequency=freq, horizon=14, model_choice="auto")
pw = job.backtests.get("prophet").metrics.wape if job.backtests.get("prophet") else None
bw = job.backtests.get("seasonal_naive").metrics.wape if job.backtests.get("seasonal_naive") else None
print("STAGE5_FIX_OK", job.quality_status, job.selected_model, "pw", pw, "bw", bw)
assert job.forecast.points
PY
echo STAGE5_FIX_DONE
