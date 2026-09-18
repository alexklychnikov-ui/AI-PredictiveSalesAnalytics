#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics

if [[ -f /tmp/stage3.tar.gz ]]; then
  tar -xzf /tmp/stage3.tar.gz -C /opt/AI-PredictiveSalesAnalytics
fi

find . -type f -name '*.sh' -exec sed -i 's/\r$//' {} +
chmod +x scripts/*.sh || true

set -a
# shellcheck disable=SC1091
source .env
set +a

docker compose up -d --build --force-recreate app
sleep 15
docker compose ps
docker compose logs --tail=25 app

echo "--- unit ---"
docker compose exec -T app pytest tests/unit -q

echo "--- sample ingest smoke ---"
docker compose exec -T app python - <<'PY'
from pathlib import Path
from src.data.pipeline import preview_from_path, preview_ingest, to_dataset_create
from src.db.repositories import DatasetRepository
from src.db.session import session_scope

path = Path("sample_data/synthetic_sales.csv")
loaded, mapping = preview_from_path(str(path))
preview = preview_ingest(
    loaded.frame,
    source_name=loaded.source_name,
    mapping=mapping,
    frequency="D",
    agg="sum",
    horizon=30,
    fill_missing_as_zero=False,
)
print("rows", preview.quality.rows_clean, "status", preview.quality.history.status, "horizon", preview.allowed_horizon)
payload = to_dataset_create(preview, name="synthetic_demo", target_kpi="revenue", frequency="D")
with session_scope() as session:
    created = DatasetRepository(session).create_with_observations(payload)
    print("saved_id", created.id, "obs", len(payload.observations))
PY

echo "STAGE3_OK"
