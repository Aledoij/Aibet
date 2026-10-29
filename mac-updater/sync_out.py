"""Cloud side of the code sync: pack what Claude threads changed in /mnt/project-files since the last pack, so the
Mac picks up new features and fixes (its runs then use the same code and model files as the Claude runs).

What ships: every new or changed .py/.sh/.js/.md/.css file, plus data files in the folders the live runs use
(LIVE, found from the run scripts themselves), EXCEPT the Mac's own running data (logs, snapshots, odds history and
the run outputs in STATE). Files under sports-app/export/ ship only if the Mac doesn't have them yet.
Packs are incremental: mac-updater/sync_state.json remembers what was shipped (size + time), and
<repo>/sync/index.json lists every pack in order; the Mac applies the ones it hasn't. Packs are encrypted with the
passphrase in mac-updater/.sync_pass (the Mac has it as SYNC_PASS in settings.env).
Usage: python sync_out.py <clone of the thread's branch>     (then commit + push that clone's sync/ folder)
"""
import fnmatch
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/mnt/project-files")
SYNC = Path(sys.argv[1]) / "sync"
STATEF = ROOT / "mac-updater" / "sync_state.json"
BASE = datetime(2026, 10, 27, 1, 9, tzinfo=timezone.utc).timestamp()  # the Mac's first copy was cut at 01:09Z
CODE = (".py", ".sh", ".js", ".md", ".css")
NEVER = ("uploads/", "mac-updater/", "full-audit/backups/", "outside-check/", "real-app/", "day-audit/", "tennis-push/",
         "tennis-prediction/")
STATE = ["live-news/raw/*", "live-news/odds_history/*", "live-news/espn_*", "live-news/bet_results/*", "live-news/*.csv",
         "live-news/*.json", "live-news/*/*.csv", "live-news/*/*.json", "live-news/*/*/*", "simulator/live_data/*",
         "nba-challenger/shadow/*", "accuracy-remaining/nba/work/*", "sports-app/matchup-predictor.html", "*_live.csv",
         "*_latest.csv", "pre-ufc-records/debut_*.json", "auto-retrain/registry*.json", "auto-retrain/history.jsonl",
         "auto-retrain/previous/*", "nfl-win-prediction/pregame_features*.csv", "nfl-win-prediction/injury_features.csv",
         "nfl-win-prediction/nfl_model.json", "nfl-player-props/upcoming_*", "nfl-player-props/spread_tables.json",
         "*.zip", "*.pyc", "*/__pycache__/*", "*/node_modules/*"]


def live_dirs():
    """Top-level folders the live run scripts name (one hop: run scripts -> folders they read)."""
    names = {p.name for p in ROOT.iterdir() if p.is_dir()}
    txt = ""
    for pat in ("live-news/*.py", "sports-app/*.py", "sports-app/*/*.py", "simulator/live/*.py", "auto-retrain/*.py",
                "mac-updater/*.py"):
        for f in ROOT.glob(pat):
            txt += f.read_text(errors="ignore")
    found = {n for n in names if re.search(r'["/ (]' + re.escape(n) + r'["/)]', txt)}
    return found | {"live-news", "sports-app", "simulator"}


LIVE = live_dirs()


def kind(rel):
    if rel.startswith(NEVER) or any(fnmatch.fnmatch(rel, p) for p in STATE):
        return None
    if rel.endswith(CODE):
        return "file"
    if rel.split("/")[0] not in LIVE:
        return None
    return "missing-only" if rel.startswith("sports-app/export/") else "file"


shipped = json.load(open(STATEF)) if STATEF.exists() else {}
files, missing_only, now_state = [], [], {}
for dp, dn, fn in os.walk(ROOT):
    dn[:] = [d for d in dn if d not in ("__pycache__", ".git", "node_modules", "uploads")]
    for f in fn:
        p = Path(dp) / f
        rel = str(p.relative_to(ROOT))
        try:
            st = p.stat()
        except OSError:
            continue
        if st.st_mtime <= BASE or st.st_size > 90_000_000:
            continue
        sig = [st.st_size, int(st.st_mtime)]
        if shipped.get(rel) == sig:
            continue
        k = kind(rel)
        if k:
            files.append(rel)
            now_state[rel] = sig
            if k == "missing-only":
                missing_only.append(rel)
if not files:
    print("sync pack: nothing new")
    sys.exit(0)
SYNC.mkdir(parents=True, exist_ok=True)
version = time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:xz") as t:
    for rel in sorted(files):
        t.add(ROOT / rel, arcname=rel)
raw = SYNC / "tmp.tar.xz"
raw.write_bytes(buf.getvalue())
enc_f = SYNC / "tmp.enc"
subprocess.run(["openssl", "enc", "-aes-256-cbc", "-md", "sha256", "-salt", "-pass",
                f"file:{ROOT / 'mac-updater' / '.sync_pass'}", "-in", str(raw), "-out", str(enc_f)],
               check=True, stderr=subprocess.DEVNULL)
raw.unlink()
enc = enc_f.read_bytes()
enc_f.unlink()
PART = 45 * 1024 * 1024  # GitHub refuses files over 100 MB
parts = [enc[i:i + PART] for i in range(0, len(enc), PART)]
for i, b in enumerate(parts):
    (SYNC / f"{version}.part{i:02d}").write_bytes(b)
idx_f = SYNC / "index.json"
idx = json.load(open(idx_f)) if idx_f.exists() else {"packs": []}
idx["packs"].append({"version": version, "sha256": hashlib.sha256(enc).hexdigest(), "parts": len(parts),
                     "files": len(files), "bytes": len(enc), "missing_only": missing_only})
json.dump(idx, open(idx_f, "w"), indent=1)
shipped.update(now_state)
json.dump(shipped, open(STATEF, "w"))
print(f"sync pack {version}: {len(files)} files, {len(enc) / 1e6:.1f} MB in {len(parts)} parts")
