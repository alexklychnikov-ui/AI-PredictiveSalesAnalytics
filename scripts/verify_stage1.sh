#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
sed -i 's/\r$//' scripts/*.sh || true
chmod +x scripts/*.sh

docker compose exec -T app python - <<'PY'
from src.db.session import check_db
ok, msg = check_db()
print("DB_OK" if ok else "DB_FAIL")
print(msg[:160])
PY

bash scripts/backup_postgres.sh
LATEST="$(ls -1t backups/sales_analytics_*.sql.gz | head -1)"
echo "LATEST=$LATEST"
gunzip -t "$LATEST"
echo "BACKUP_OK"

echo "--- ports ---"
ss -tlnp | grep -E ':80|:443|:5432|:8501' || true
echo "--- ps ---"
docker compose ps
