#!/bin/bash
# Double-click me to run a full update right now (takes about 15-30 minutes). The window shows progress.
H="$HOME/MatchupPredictor-Updater"
bash "$H/updater/run.sh" full &
sleep 3; tail -f "$(ls -t "$H"/logs/*_full.log | head -1)" &
wait %1; sleep 2; kill %2 2>/dev/null
echo; cat "$H/logs/last_full.txt"; echo "Done. You can close this window."
