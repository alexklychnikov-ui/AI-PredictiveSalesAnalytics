#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <password>" >&2
  exit 1
fi

docker run --rm caddy:2.9-alpine caddy hash-password --plaintext "$1"
