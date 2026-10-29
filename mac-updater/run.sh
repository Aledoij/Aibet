#!/bin/bash
# Started by the Mac's scheduler (launchd). Runs one update and writes its log to logs/.
# Usage: run.sh <full|pretip|nfl|retrain|opening>
HERE=$(cd "$(dirname "$0")" && pwd); H=$(dirname "$HERE"); MODE=${1:-full}
mkdir -p "$H/logs"
LOG="$H/logs/$(date -u +%Y-%m-%dT%H%MZ)_$MODE.log"
# one run at a time: wait up to 45 minutes for an earlier run to finish
for i in $(seq 1 90); do mkdir "$H/.lock" 2>/dev/null && break; sleep 30; done
trap 'rmdir "$H/.lock" 2>/dev/null' EXIT
export PATH="$H/venv/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PLAYWRIGHT_BROWSERS_PATH="$H/browsers"
# keep the Mac awake while the run works (it's fine for the screen to be off)
/usr/bin/caffeinate -i "$H/venv/bin/python" "$HERE/run.py" "$MODE" >"$LOG" 2>&1
find "$H/logs" -name "*.log" -mtime +30 -delete 2>/dev/null
exit 0
