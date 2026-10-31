"""NFL refresh (Wed + Sat), the same steps as the Claude task "Matchup Predictor NFL refresh", as a plain script.

nflverse data (GitHub) -> nfl-win-prediction build_features / injuries / final (regenerates nfl_model.json) ->
export_nfl.py (nfl.json + upcoming.json["nfl"]) -> nfl_injuries_live.py -> player props -> player grades -> kickoffs.
Past seasons' files are kept in the work folder and only this season's are downloaded again.
If the win model steps fail, nothing after them runs and the app keeps its NFL tab. Betting lines are never used.
Usage: python nfl_refresh.py <project dir> <work dir>
"""
import shutil
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT, WORK = Path(sys.argv[1]), Path(sys.argv[2])
NWP, EXPORT, NEWS = ROOT / "nfl-win-prediction", ROOT / "sports-app" / "export", ROOT / "live-news"
D, G = WORK / "nfl", WORK / "grades"
for d in (D, G):
    d.mkdir(parents=True, exist_ok=True)
py = sys.executable
B = "https://github.com/nflverse/nflverse-data/releases/download"
t = date.today()
season = t.year if t.month >= 3 else t.year - 1


def fetch(url, path, always=False):
    if path.exists() and path.stat().st_size and not always:
        return
    for i in range(3):
        try:
            data = urllib.request.urlopen(url, timeout=300).read()
            path.write_bytes(data)
            return
        except Exception as e:  # noqa: BLE001
            print("  retry", url, e)
    raise RuntimeError(f"download failed: {url}")


def run(args, cwd):
    print(">>", " ".join(map(str, args)), flush=True)
    r = subprocess.run([py, *map(str, args)], cwd=cwd)
    return r.returncode == 0


print("downloading nflverse data (first run takes a few minutes)")
fetch("https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv", D / "games.csv", True)
for y in range(2006, season + 1):
    fetch(f"{B}/pbp/play_by_play_{y}.parquet", D / f"play_by_play_{y}.parquet", y == season)
for y in range(2012, season + 1):
    fetch(f"{B}/injuries/injuries_{y}.parquet", D / f"injuries_{y}.parquet", y == season)
    fetch(f"{B}/snap_counts/snap_counts_{y}.parquet", D / f"snap_counts_{y}.parquet", y == season)
fetch(f"{B}/players/players.parquet", D / "players.parquet", True)

ok = (run(["build_features.py", D, "pregame_features.csv"], NWP)
      and run(["injuries.py", D, "injury_features.csv"], NWP)
      and run(["final.py", "pregame_features.csv", "injury_features.csv", "pregame_features_qbs.csv", "."], NWP)
      and run(["export_nfl.py", "../../nfl-win-prediction", "nfl.json", "upcoming.json"], EXPORT))
if not ok:
    sys.exit("NFL win model steps failed: NFL tab left as it was")
run(["nfl_injuries_live.py", "../sports-app/export", "."], NEWS)  # put the latest injury report back into upcoming.json

# player props (rebuilt only when a game is within 3 days, like every news run)
run([NEWS / "nfl_props_refresh.py", ROOT, WORK / "nfl_props"], NEWS)

# player grades (display only); a failure keeps the old file
try:
    for y in (season - 1, season):
        fetch(f"{B}/pfr_advstats/advstats_week_def_{y}.parquet", G / f"def_{y}.parquet", y == season)
        fetch(f"{B}/stats_player/stats_player_week_{y}.parquet", G / f"st_{y}.parquet", y == season)
        fetch(f"{B}/snap_counts/snap_counts_{y}.parquet", G / f"snaps_{y}.parquet", y == season)
    fetch(f"{B}/players/players.parquet", G / "players.parquet", True)
    PG = ROOT / "player-grades-synergy"
    new = G / "nfl_ovr_new.csv"
    if run(["nfl_ovr.py", "../sports-app/export/nfl.json", G, "../player-impact/nfl_player_grades_latest.csv",
            "results_nfl_ovr_weights.json", new], PG) and new.exists() and sum(1 for _ in open(new)) >= 500:
        shutil.copyfile(new, PG / "nfl_ovr_latest.csv")
except Exception as e:  # noqa: BLE001
    print("player grades skipped:", e)

run(["export/nfl_kickoffs.py"], ROOT / "sports-app")
print("NFL refresh done")
