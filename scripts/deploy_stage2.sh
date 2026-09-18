#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics

if [[ -d /tmp/stage2 ]]; then
  cp -a /tmp/stage2/. /opt/AI-PredictiveSalesAnalytics/
fi

find . -type f \( -name '*.sh' -o -name 'docker_entrypoint.sh' \) -exec sed -i 's/\r$//' {} +
chmod +x scripts/*.sh

set -a
# shellcheck disable=SC1091
source .env
set +a

docker compose up -d --build --force-recreate app
sleep 15
docker compose ps
docker compose logs --tail=40 app

echo "--- tables ---"
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt'

echo "--- pytest unit ---"
docker compose exec -T app pytest tests/unit -q

echo "--- pytest integration ---"
docker compose exec -T -e RUN_DB_INTEGRATION=1 app pytest tests/integration -q

echo "STAGE2_OK"
