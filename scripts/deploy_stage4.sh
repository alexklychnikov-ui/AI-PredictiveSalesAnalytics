#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/stage4.tar.gz
docker compose up -d --build --force-recreate app
sleep 12
docker compose exec -T app pytest tests/unit -q
docker compose exec -T app python <<'PY'
from src.analytics.service import build_analytics_report, observations_to_frame
from src.db.repositories import DatasetRepository
from src.db.session import session_scope

with session_scope() as session:
    repo = DatasetRepository(session)
    dataset = repo.list_summaries()[0]
    rows = repo.load_observations(dataset.id)
    frame = observations_to_frame(rows)
    report = build_analytics_report(frame, frequency=dataset.frequency)
    print(
        "points",
        report.kpi.points,
        "anom",
        report.anomalies.count,
        "corr",
        len(report.correlations.pairs),
    )
PY
echo STAGE4_OK
