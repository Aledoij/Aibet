#!/bin/bash
# Upload the newest predictor page to GitHub (Aledoij/Aibet main) for the Mac and iPhone apps.
# Same page wrapper as real-app/mac/publish_picks.sh. Settings (settings.env one folder up):
#   GITHUB_TOKEN   fine-grained token with Contents read/write on Aledoij/Aibet only (blank = use the Mac's saved git login)
#   PUBLISH_FILE   picks-mac.html while testing side by side with Claude; picks.html once the Mac takes over
set -e
HERE=$(cd "$(dirname "$0")" && pwd); HOME_DIR=$(dirname "$HERE")
set -a; [ -f "$HOME_DIR/settings.env" ] && . "$HOME_DIR/settings.env"; set +a
OUT=${PUBLISH_FILE:-picks-mac.html}
R="$HOME_DIR/repo"; P="$HOME_DIR/project"
if [ -n "$GITHUB_TOKEN" ]; then URL="https://x-access-token:${GITHUB_TOKEN}@github.com/Aledoij/Aibet.git"; else URL="https://github.com/Aledoij/Aibet.git"; fi
[ -d "$R/.git" ] || git clone -q --depth 5 "$URL" "$R"
git -C "$R" remote set-url origin "$URL"
git -C "$R" fetch -q origin main
git -C "$R" checkout -q -B main origin/main
"$HOME_DIR/venv/bin/python" - "$P/sports-app/matchup-predictor.html" "$R/$OUT" <<'PY'
import sys, time
page = open(sys.argv[1]).read()
open(sys.argv[2], "w").write('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    f'<meta name="mp-built" content="{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}">'
    '<meta name="mp-source" content="mac-updater">'
    '<meta name="theme-color" content="#070b16"><meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black">'
    '<meta name="apple-mobile-web-app-title" content="Predictor"><meta name="robots" content="noindex, nofollow">'
    '<link rel="manifest" href="manifest.webmanifest"><link rel="icon" href="icons/icon-192.png">'
    '<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">'
    '<script>if (location.protocol === "https:" && "serviceWorker" in navigator) addEventListener("load", () => navigator.serviceWorker.register("sw.js"));</script>'
    '</head><body>\n' + page + "\n</body></html>\n")
PY
cd "$R"
git add "$OUT"
git -c user.name="Matchup Predictor (Mac)" -c user.email="noreply@users.noreply.github.com" \
    commit -qm "Update $OUT from Mac $(date -u +%Y-%m-%dT%H:%MZ)" || { echo "no change"; exit 0; }
for i in 1 2 3 4; do git push -q origin HEAD:main && break || { sleep $((2**i)); git fetch -q origin main; git rebase -q origin/main; }; done
[ "$(git ls-remote origin refs/heads/main | cut -f1)" = "$(git rev-parse HEAD)" ] || { echo "PUSH FAILED: GitHub main is not $(git rev-parse --short HEAD)"; exit 1; }
echo "pushed $OUT ($(git rev-parse --short HEAD)) to main"
