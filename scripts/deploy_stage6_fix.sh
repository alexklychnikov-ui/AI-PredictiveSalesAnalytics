#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/stage6_fix.tar.gz
docker compose up -d --build --force-recreate app
sleep 12
docker compose exec -T app pytest tests/unit/test_scenarios.py -q --tb=line
docker compose exec -T app python <<'PY'
from src.analytics.service import apply_filters, observations_to_frame
from src.db.repositories import DatasetRepository
from src.db.session import session_scope
from src.scenarios.eligibility import assess_all_factors
from src.scenarios.service import run_scenario_job

with session_scope() as session:
    repo = DatasetRepository(session)
    ds = repo.list_summaries()[0]
    frame = observations_to_frame(repo.load_observations(ds.id))
    sk = (repo.list_series_keys(ds.id) or ["total"])[0]
    filtered = apply_filters(frame, series_key=sk)
    freq = ds.frequency

elig = [e for e in assess_all_factors(filtered) if e.eligible]
# last values → should skip all factor scenarios
factor_last = {}
for e in elig:
    import pandas as pd
    factor_last[e.factor] = float(pd.to_numeric(filtered[e.factor], errors="coerce").dropna().iloc[-1])

job_skip = run_scenario_job(
    filtered, frequency=freq, horizon=14, factor_values=factor_last,
    model_choice="seasonal_naive", include_prophet=False,
)
assert job_skip.factor_scenarios == []

# changed marketing_spend if eligible
factor_values = {}
for e in elig:
    if e.factor == "marketing_spend" and e.max_value is not None and e.min_value is not None:
        factor_values[e.factor] = float(e.min_value + 0.8 * (e.max_value - e.min_value))
        break

job = run_scenario_job(
    filtered, frequency=freq, horizon=14,
    optimistic_pct=10, pessimistic_pct=-10, custom_pct=5,
    factor_values=factor_values or None,
    model_choice="seasonal_naive", include_prophet=False,
)
print(
    "STAGE6_FIX_OK",
    "stress", len(job.stress),
    "elig", len(elig),
    "factor_applied", sum(1 for f in job.factor_scenarios if f.model.allowed),
    "skip_notes", sum(1 for n in job_skip.notes if "без изменения" in n),
    "profit", bool(job.profit and job.profit.available),
)
assert job.base_points and len(job.stress) == 3
PY
echo STAGE6_FIX_DONE
