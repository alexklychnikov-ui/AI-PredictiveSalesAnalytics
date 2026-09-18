#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
tar -xzf /tmp/stage9.tar.gz
test -f requirements-dev.txt
test -f pyproject.toml

docker compose up -d --build --force-recreate app

for i in $(seq 1 40); do
  if docker compose exec -T app curl -sf "http://127.0.0.1:8501/_stcore/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "=== ruff ==="
docker compose exec -T app sh -c 'pip install -q -r requirements-dev.txt && ruff check src tests pages scripts'
echo "=== mypy (src focused) ==="
docker compose exec -T app sh -c 'mypy src/security src/ui src/data/loader.py src/recommendations/facts.py src/forecasting/service.py --ignore-missing-imports'
echo "=== pytest unit ==="
docker compose exec -T app pytest tests/unit -q --tb=line
echo "=== pytest integration ==="
docker compose exec -T app pytest tests/integration -q --tb=line

echo "=== perf smoke ==="
docker compose exec -T app sh -c 'PYTHONPATH=/app python scripts/perf_smoke.py'

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

echo STAGE9_DONE
