#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/ux_corr.tar.gz
docker compose up -d --build --force-recreate app
for i in $(seq 1 25); do
  if docker compose exec -T app curl -sf "http://127.0.0.1:8501/_stcore/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
code=$(docker compose exec -T app curl -sf -o /dev/null -w "%{http_code}" "http://127.0.0.1:8501/_stcore/health" || true)
echo "health_app=${code}"
test "${code}" = "200"
echo UX_CORR_OK
