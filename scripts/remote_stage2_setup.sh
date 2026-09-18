#!/usr/bin/env bash
set -euo pipefail
mkdir -p /tmp/stage2/src/db /tmp/stage2/migrations/versions /tmp/stage2/scripts /tmp/stage2/tests/unit /tmp/stage2/tests/integration
cd /tmp/stage2_files
cp app.py Dockerfile alembic.ini /tmp/stage2/
cp models.py session.py repositories.py __init__.py /tmp/stage2/src/db/
cp schemas.py /tmp/stage2/src/
cp env.py script.py.mako /tmp/stage2/migrations/
cp 20260918_0001_initial_schema.py /tmp/stage2/migrations/versions/
cp docker_entrypoint.sh deploy_stage2.sh /tmp/stage2/scripts/
cp test_schemas.py /tmp/stage2/tests/unit/
cp test_dataset_repository.py /tmp/stage2/tests/integration/
touch /tmp/stage2/src/__init__.py
sed -i 's/\r$//' /tmp/stage2/scripts/*.sh
bash /tmp/stage2/scripts/deploy_stage2.sh
