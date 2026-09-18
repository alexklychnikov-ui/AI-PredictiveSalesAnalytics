#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/stage7.tar.gz
docker compose up -d --build --force-recreate app
sleep 12
docker compose exec -T app pytest tests/unit -q --tb=line
docker compose exec -T app python <<'PY'
from src.analytics.service import apply_filters, observations_to_frame
from src.db.repositories import DatasetRepository
from src.db.session import session_scope
from src.recommendations.cache import cache_clear
from src.recommendations.facts import to_jsonable
from src.recommendations.openai_client import openai_available
from src.recommendations.service import run_insight_job
from src.schemas import ForecastPointCreate, ForecastRunCreate
from datetime import timezone

cache_clear()
with session_scope() as session:
    repo = DatasetRepository(session)
    ds = repo.list_summaries()[0]
    frame = observations_to_frame(repo.load_observations(ds.id))
    sk = (repo.list_series_keys(ds.id) or ["total"])[0]
    filtered = apply_filters(frame, series_key=sk)
    freq = ds.frequency
    dataset_id = ds.id
    meta = {"id": ds.id, "name": ds.name, "target_kpi": ds.target_kpi, "frequency": ds.frequency}

# always works without openai
job_rules = run_insight_job(
    filtered, frequency=freq, horizon=14, dataset_meta=meta,
    use_openai=False, include_prophet=False, force_refresh=True,
)
assert job_rules.source == "rules"
assert job_rules.report.recommendations

job_ai = None
if openai_available():
    job_ai = run_insight_job(
        filtered, frequency=freq, horizon=14, dataset_meta=meta,
        use_openai=True, include_prophet=False, force_refresh=True,
    )
    assert job_ai.source in {"openai", "openai_fallback_rules"}
    assert job_ai.report.recommendations

def as_utc(value):
    ts = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)

chosen = job_ai if job_ai is not None else job_rules
create = ForecastRunCreate(
    dataset_id=dataset_id,
    series_key=sk,
    model_name="insight",
    horizon=14,
    config={"purpose": "insight_container"},
    metrics={},
    quality_status="insight",
    train_start=as_utc(filtered["ds"].iloc[0]),
    train_end=as_utc(filtered["ds"].iloc[-1]),
    points=[ForecastPointCreate(ds=as_utc(filtered["ds"].iloc[-1]), yhat=0.0, scenario_type="insight_anchor")],
)
with session_scope() as session:
    repo = DatasetRepository(session)
    run = repo.save_forecast_run(create)
    insight = repo.save_insight_report(
        run_id=run.id,
        facts=to_jsonable(chosen.facts),
        recommendations=to_jsonable(chosen.report.to_dict()),
        source=chosen.source,
        openai_model=chosen.openai_model,
        notes="; ".join(chosen.notes) if chosen.notes else None,
    )
    print(
        "STAGE7_OK",
        "rules_n",
        len(job_rules.report.recommendations),
        "openai",
        openai_available(),
        "ai_source",
        None if job_ai is None else job_ai.source,
        "insight_id",
        insight.id,
        "hash",
        chosen.facts.get("facts_hash", "")[:12],
    )
PY
echo STAGE7_DONE
