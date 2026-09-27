#!/usr/bin/env bash
# cron example: 30 8 * * * /path/to/job-app-agent/run_daily.sh
cd "$(dirname "$0")" && source .venv/bin/activate && python main.py run >> logs/daily_run.log 2>&1
