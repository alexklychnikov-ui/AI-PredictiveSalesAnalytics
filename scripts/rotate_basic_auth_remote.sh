#!/usr/bin/env bash
# Run on VPS: reads plaintext from /tmp/basic_auth_password_new, updates .env hash, recreates caddy.
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics

PASS_FILE="${1:-/tmp/basic_auth_password_new}"
test -f "$PASS_FILE"
NEW_PASS="$(tr -d '\r\n' <"$PASS_FILE")"
test -n "$NEW_PASS"

HASH="$(docker compose run --rm --no-deps --entrypoint caddy caddy hash-password --plaintext "$NEW_PASS")"
HASH_ESC="$(printf '%s' "$HASH" | sed 's/\$/\$\$/g')"

python3 - "$HASH_ESC" <<'PY'
from pathlib import Path
import sys
hash_esc = sys.argv[1]
env_path = Path(".env")
text = env_path.read_text(encoding="utf-8")
lines = []
found = False
for line in text.splitlines():
    if line.startswith("BASIC_AUTH_PASSWORD_HASH="):
        lines.append("BASIC_AUTH_PASSWORD_HASH=" + hash_esc)
        found = True
    else:
        lines.append(line)
if not found:
    lines.append("BASIC_AUTH_PASSWORD_HASH=" + hash_esc)
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("ENV_HASH_UPDATED")
PY

docker compose up -d --force-recreate caddy
sleep 3
docker compose ps caddy
rm -f "$PASS_FILE"
echo "ROTATE_DONE"
