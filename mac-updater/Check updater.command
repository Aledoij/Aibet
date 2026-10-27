#!/bin/bash
# Double-click me to see whether the updater is scheduled and how the last runs went.
H="$HOME/MatchupPredictor-Updater"
"$H/venv/bin/python" "$H/updater/schedule.py" status
echo; echo "Last 10 runs:"; tail -10 "$H/logs/history.txt" 2>/dev/null
echo; echo "You can close this window."
