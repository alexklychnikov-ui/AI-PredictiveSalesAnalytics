#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/stage8.tar.gz
docker compose up -d --build --force-recreate app
# wait for app health inside container
for i in $(seq 1 40); do
  if docker compose exec -T app curl -sf "http://127.0.0.1:8501/_stcore/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose exec -T app pytest tests/unit -q --tb=line

set -a
# shellcheck disable=SC1091
source .env
set +a
USER_NAME="${BASIC_AUTH_USER:-admin}"
PASS=""
if [[ -f /tmp/basic_auth_password ]]; then
  PASS=$(tr -d '\r\n' </tmp/basic_auth_password)
  rm -f /tmp/basic_auth_password
fi
BASE="https://${APP_DOMAIN}"

code_health=$(docker compose exec -T app curl -sf -o /dev/null -w "%{http_code}" "http://127.0.0.1:8501/_stcore/health" || true)
echo "health_app=${code_health}"
test "${code_health}" = "200"

if [[ -n "${PASS}" ]]; then
  code=$(curl -sk -o /dev/null -w "%{http_code}" -u "${USER_NAME}:${PASS}" "${BASE}/" || true)
  echo "page / -> ${code}"
  test "${code}" = "200"
else
  echo "SKIP_AUTH_PAGES no password file"
fi

docker compose exec -T app python <<'PY'
from src.export.reports import forecast_points_csv, recommendations_text_report
from src.ui.session_store import serialize_forecast_job
from src.forecasting.service import run_forecast_job
import pandas as pd
import numpy as np
dates = pd.date_range("2024-01-01", periods=40, freq="D", tz="UTC")
frame = pd.DataFrame({"ds": dates, "y": np.linspace(10, 20, 40)})
job = run_forecast_job(frame, frequency="D", horizon=5, model_choice="seasonal_naive", include_prophet=False)
payload = serialize_forecast_job(job, dataset_id=1, series_key="total")
csv = forecast_points_csv(payload["points"])
assert "yhat" in csv
txt = recommendations_text_report({"source": "rules", "report": {"summary": "ok", "recommendations": [], "caveats": []}, "facts_hash": "x"})
assert "Отчёт" in txt
print("STAGE8_OK", "points", len(payload["points"]), "csv_lines", len(csv.splitlines()))
PY
echo STAGE8_DONE
