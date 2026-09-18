#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics

python3 <<'PY'
from pathlib import Path

path = Path(".env")
out = []
openai_set = False
for line in path.read_text().splitlines():
    if line.startswith("BASIC_AUTH_PASSWORD_HASH="):
        key, value = line.split("=", 1)
        value = value.replace("$$", "$").replace("$", "$$")
        out.append(f"{key}={value}")
    else:
        out.append(line)
        if line.startswith("OPENAI_API_KEY=sk-"):
            openai_set = True
path.write_text("\n".join(out) + "\n")
print("openai_set", openai_set)
print("hash_escaped", True)
PY

chmod 600 .env
docker compose up -d --force-recreate app
sleep 6
docker compose exec -T app python - <<'PY'
from src.config import get_settings

get_settings.cache_clear()
settings = get_settings()
print("openai_enabled", settings.openai_enabled)
print("key_prefix", (settings.openai_api_key[:7] + "...") if settings.openai_api_key else "EMPTY")
PY
