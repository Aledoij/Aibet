#!/bin/bash
# Cloud side, run by the "Mac update pack" scheduled task (Alex OK'd sending encrypted packs via the Aibet side
# branch, 2026-10-29): make a pack of what changed since the last one and push it, with the updater's own scripts,
# to the branch the Mac reads. Never touches main. Usage: bash push_sync.sh [clone dir]
set -e
HERE=$(cd "$(dirname "$0")" && pwd); BR=claude/project-thread-5w024f; R=${1:-/tmp/mac-sync-repo}
[ -d "$R/.git" ] || git clone -q --single-branch --branch "$BR" https://github.com/Aledoij/Aibet.git "$R"
git -C "$R" fetch -q origin "$BR" && git -C "$R" checkout -q "$BR" && git -C "$R" reset -q --hard "origin/$BR"
python3 "$HERE/sync_out.py" "$R"
for f in "$HERE"/*; do case "$(basename "$f")" in sync_state.json|__pycache__) ;; *) cp "$f" "$R/mac-updater/";; esac; done
cd "$R"; git add -A mac-updater sync
git diff --cached --quiet && { echo "nothing to push"; exit 0; }
git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit -qm "Mac update pack $(date -u +%Y-%m-%dT%H:%MZ)"
for i in 1 2 3 4; do git push -q origin "$BR" && break || sleep $((2**i)); done
echo "pushed to $BR: $(git rev-parse --short HEAD)"
