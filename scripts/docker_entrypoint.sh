#!/usr/bin/env bash
set -euo pipefail

echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

exec streamlit run app.py --server.address=0.0.0.0 --server.port=8501
