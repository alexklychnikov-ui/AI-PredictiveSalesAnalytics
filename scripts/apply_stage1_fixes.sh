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
curl -sI https://salesanalytics.alexklyvibe.ru | head -5
curl -sI -u 'admin:[REDACTED]' https://salesanalytics.alexklyvibe.ru | head -8
bash scripts/setup_backup_cron.sh
