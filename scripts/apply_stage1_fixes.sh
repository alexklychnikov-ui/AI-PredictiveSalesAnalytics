#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics

cp /tmp/stage1fix/compose.yaml .
cp /tmp/stage1fix/config.py src/config.py
cp /tmp/stage1fix/app.py .
cp /tmp/stage1fix/env.example .
cp /tmp/stage1fix/restore_postgres.sh scripts/
cp /tmp/stage1fix/setup_backup_cron.sh scripts/
sed -i 's/\r$//' scripts/*.sh compose.yaml || true
chmod +x scripts/*.sh

python3 <<'PY'
from pathlib import Path
path = Path(".env")
lines = []
for line in path.read_text().splitlines():
    if line.startswith("DATABASE_URL="):
        lines.append("DATABASE_URL=")
    else:
        lines.append(line)
# ensure postgres host not required in .env
path.write_text("\n".join(lines) + "\n")
print("env cleaned")
PY

docker compose up -d --build --force-recreate app caddy
sleep 10
docker compose ps
docker compose exec -T app python - <<'PY'
from src.db.session import check_db
ok, msg = check_db()
print("DB_OK" if ok else "DB_FAIL")
print(msg[:160])
PY
echo "--- caddy env keys ---"
docker compose exec -T caddy env | cut -d= -f1 | sort
echo "--- auth ---"
set -a
# shellcheck disable=SC1091
source .env
set +a
AUTH_USER="${BASIC_AUTH_USER:-admin}"
AUTH_PASS="${BASIC_AUTH_PASSWORD:-}"
if [[ -z "$AUTH_PASS" && -f /tmp/basic_auth_password ]]; then
  AUTH_PASS=$(tr -d '\r\n' </tmp/basic_auth_password)
fi
curl -sI "https://${APP_DOMAIN}" | head -5
if [[ -n "$AUTH_PASS" ]]; then
  curl -sI -u "${AUTH_USER}:${AUTH_PASS}" "https://${APP_DOMAIN}" | head -8
else
  echo "BASIC_AUTH_PASSWORD not set — skip authenticated probe"
fi
bash scripts/setup_backup_cron.sh
