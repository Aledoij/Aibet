#!/bin/bash
# One-time setup of the Matchup Predictor updater on this Mac. Safe to run again (it only adds what's missing).
#   1. Python 3.13 + the packages the models need, in ~/MatchupPredictor-Updater/venv (nothing system-wide)
#   2. Chromium for the page checks (Playwright), in ~/MatchupPredictor-Updater/browsers
#   3. Points the project's scripts at this folder instead of the cloud's /mnt/project-files
#   4. The schedule (launchd), in US Eastern times: see SCHEDULE below
set -e
H="$HOME/MatchupPredictor-Updater"; cd "$H"
echo "== Python"
if ! command -v uv >/dev/null; then curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; fi
[ -x venv/bin/python ] || uv venv --python 3.13 venv
uv pip install --python venv/bin/python -q pandas numpy scipy scikit-learn pyarrow lightgbm playwright requests beautifulsoup4 lxml
# lightgbm needs the OpenMP library on Macs (without it the NBA props step crashes: "Library not loaded: libomp.dylib")
if command -v brew >/dev/null && ! brew list libomp >/dev/null 2>&1; then brew install libomp; fi
echo "== Chromium"
PLAYWRIGHT_BROWSERS_PATH="$H/browsers" venv/bin/python -m playwright install chromium
echo "== project paths"
# scripts written for the cloud say /mnt/project-files; point them here (only .py/.sh files, data untouched)
grep -rlI --include=*.py --include=*.sh "/mnt/project-files" project | while read -r f; do
  sed -i '' "s#/mnt/project-files#$H/project#g" "$f"; done
chmod +x updater/*.sh
[ -f settings.env ] || { printf 'PROPLINE_API_KEY=\nGITHUB_TOKEN=\nPUBLISH_FILE=picks-mac.html\n' > settings.env; }
chmod 600 settings.env
echo "== schedule"
venv/bin/python updater/schedule.py install
echo "ALL SET"
