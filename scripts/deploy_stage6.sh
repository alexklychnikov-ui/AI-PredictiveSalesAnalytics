#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/stage6.tar.gz
docker compose up -d --build --force-recreate app
sleep 12
docker compose exec -T app pytest tests/unit -q --tb=line
docker compose exec -T app python <<'PY'
from src.analytics.service import apply_filters, observations_to_frame
from src.db.repositories import DatasetRepository
from src.db.session import session_scope
from src.scenarios.service import run_scenario_job
from src.schemas import ForecastPointCreate, ForecastRunCreate
from datetime import timezone

with session_scope() as session:
    repo = DatasetRepository(session)
    ds = repo.list_summaries()[0]
    frame = observations_to_frame(repo.load_observations(ds.id))
    sk = (repo.list_series_keys(ds.id) or ["total"])[0]
    filtered = apply_filters(frame, series_key=sk)
    freq = ds.frequency
    dataset_id = ds.id

elig = [e for e in __import__("src.scenarios.eligibility", fromlist=["assess_all_factors"]).assess_all_factors(filtered) if e.eligible]
factor_values = {}
for e in elig[:2]:
    # сдвиг к верхней половине диапазона
    if e.min_value is not None and e.max_value is not None:
        factor_values[e.factor] = float(e.min_value + 0.75 * (e.max_value - e.min_value))

job = run_scenario_job(
    filtered,
    frequency=freq,
    horizon=14,
    optimistic_pct=10,
    pessimistic_pct=-10,
    custom_pct=5,
    factor_values=factor_values or None,
    model_choice="seasonal_naive",
    include_prophet=False,
)
assert job.base_points
assert len(job.stress) == 3
rows = job.comparison_rows()
assert any(r["тип"] == "stress_optimistic" for r in rows)

def as_utc(value):
    ts = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)

points = []
for p in job.base_points:
    points.append(ForecastPointCreate(ds=as_utc(p.ds), yhat=p.yhat, yhat_lower=p.yhat_lower, yhat_upper=p.yhat_upper, scenario_type="base"))
for s in job.stress:
    for p in s.points:
        points.append(ForecastPointCreate(ds=as_utc(p.ds), yhat=p.yhat, scenario_type=s.scenario_type, scenario_factors={"pct_change": s.pct_change}))
allowed_factors = 0
for f in job.factor_scenarios:
    if not f.model.allowed:
        continue
    allowed_factors += 1
    for p in f.points:
        points.append(ForecastPointCreate(ds=as_utc(p.ds), yhat=p.yhat, scenario_type=f.scenario_type, scenario_factors={f.factor: f.scenario_value}))

create = ForecastRunCreate(
    dataset_id=dataset_id,
    series_key=sk,
    model_name="scenario",
    horizon=job.horizon,
    config=job.config,
    metrics={"comparison": rows},
    quality_status="scenario",
    points=points,
)
with session_scope() as session:
    run = DatasetRepository(session).save_forecast_run(create)
    run_id = run.id
    n_pts = len(DatasetRepository(session).load_forecast_points(run_id))

print(
    "STAGE6_OK",
    "stress",
    len(job.stress),
    "elig",
    len(elig),
    "factor_ok",
    allowed_factors,
    "rows",
    len(rows),
    "run",
    run_id,
    "pts",
    n_pts,
    "profit",
    bool(job.profit and job.profit.available),
)
PY
echo STAGE6_DONE
