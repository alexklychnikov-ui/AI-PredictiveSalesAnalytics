#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/hotfix_detached.tar.gz
docker compose up -d --build --force-recreate app
sleep 12
docker compose exec -T app python <<'PY'
from src.analytics.service import build_analytics_report, observations_to_frame
from src.db.repositories import DatasetRepository
from src.db.session import session_scope

# Reproduce UI pattern: frame built inside session, used after close
with session_scope() as session:
    repo = DatasetRepository(session)
    dataset = repo.list_summaries()[0]
    series_keys = repo.list_series_keys(dataset.id)
    frame = observations_to_frame(repo.load_observations(dataset.id))
    frequency = dataset.frequency

assert not frame.empty, "empty frame"
report = build_analytics_report(frame, frequency=frequency)
print(
    "HOTFIX_OK",
    "points",
    report.kpi.points,
    "series",
    len(series_keys),
    "anom",
    report.anomalies.count,
)
PY
echo HOTFIX_DETACHED_OK
