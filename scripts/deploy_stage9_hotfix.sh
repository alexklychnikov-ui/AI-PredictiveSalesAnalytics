#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/stage9b.tar.gz
docker compose up -d --build --force-recreate app
for i in $(seq 1 30); do
  if docker compose exec -T app curl -sf "http://127.0.0.1:8501/_stcore/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose exec -T app pytest tests/unit/test_security.py -q --tb=line
code=$(docker compose exec -T app curl -sf -o /dev/null -w "%{http_code}" "http://127.0.0.1:8501/_stcore/health" || true)
echo "health_app=${code}"
test "${code}" = "200"
echo STAGE9_HOTFIX_OK
