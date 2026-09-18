#!/usr/bin/env bash
set -euo pipefail
cd /opt/AI-PredictiveSalesAnalytics
sed -i 's/\r$//' scripts/*.sh || true
chmod +x scripts/*.sh

TMP_CRON="$(mktemp)"
crontab -l 2>/dev/null | grep -v 'backup_postgres.sh' > "$TMP_CRON" || true
echo '15 3 * * * /opt/AI-PredictiveSalesAnalytics/scripts/backup_postgres.sh >> /var/log/sales_analytics_backup.log 2>&1' >> "$TMP_CRON"
crontab "$TMP_CRON"
rm -f "$TMP_CRON"
echo CRON_OK
crontab -l
