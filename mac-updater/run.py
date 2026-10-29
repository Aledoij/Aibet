"""Matchup Predictor updater for Alex's Mac: does what the Claude scheduled tasks did, with plain scripts only.

Usage: python run.py <mode>
  full     11:47am + 5:47pm ET  news + lines + models + grading + page, then upload picks
  pretip   6:17pm + 9:17pm ET   NBA lineups/injuries/news again before tip-off, then upload picks
  nfl      Wed + Sat 10:31am ET NFL results, stats, QBs, injuries, props, grades (nflverse), then upload picks
  retrain  Tue 6:13am ET        weekly UFC retrain (weights change only when a challenger wins), then upload picks
  opening  10:07am + 11:07pm ET opening odds snapshot (history only, compare only)
Settings come from settings.env next to this file's folder (PROPLINE_API_KEY, GITHUB_TOKEN, PUBLISH_FILE).
Betting odds never feed a model, pick or grade: they are only saved and shown side by side.
Each run's log goes to logs/<UTC time>_<mode>.log; logs/last_<mode>.txt says how it ended.
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HOME = Path(__file__).resolve().parent.parent          # ~/MatchupPredictor-Updater
UPD = HOME / "updater"
ROOT = HOME / "project"                                 # the copy of the project files
WORK = HOME / "work"
LOGS = HOME / "logs"
ET = ZoneInfo("America/New_York")
MODE = sys.argv[1] if len(sys.argv) > 1 else "full"
py = sys.executable


def load_settings():
    f = HOME / "settings.env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def sh(name, args, cwd=None, timeout=3600, env=None):
    print(f"\n##### {name}  ({datetime.now(ET):%I:%M %p ET})", flush=True)
    try:
        r = subprocess.run([str(a) for a in args], cwd=cwd, timeout=timeout, env=env)
        ok = r.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"{name}: stopped after {timeout // 60} minutes")
        ok = False
    if not ok:
        problems.append(name)
    return ok


def newest_snap():
    raw = ROOT / "live-news" / "raw"
    s = sorted(p for p in raw.iterdir() if p.is_dir() and p.name[:2] == "20")
    return s[-1]


def nba_games_today(late_only=False):
    """Pre-tip runs only go ahead on NBA days (ESPN schedule); the 9:17pm one only if a game starts 9:30pm ET or later."""
    import json
    import urllib.request
    d = datetime.now(ET)
    try:
        js = json.load(urllib.request.urlopen(
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d:%Y%m%d}", timeout=30))
    except Exception as e:  # noqa: BLE001  can't tell: run anyway
        print("ESPN schedule not reachable, running anyway:", e)
        return True
    starts = [datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(ET) for e in js.get("events", [])]
    if late_only:
        starts = [s for s in starts if (s.hour, s.minute) >= (21, 30)]
    return bool(starts)


def publish():
    return sh("upload picks to GitHub (Mac + iPhone apps)", ["bash", UPD / "publish.sh"], cwd=UPD, timeout=600)


def build_page():
    return sh("build page", [py, "build_page.py"], cwd=ROOT / "sports-app")


def news_run(pretip):
    sh("fetch news pages", [py, UPD / "fetch_news.py", ROOT, "pretip" if pretip else "full"], timeout=1500)
    snap = newest_snap()
    sh("sportsbook lines (PropLine, compare only)", [py, ROOT / "live-news" / "propline_lines.py", snap],
       cwd=ROOT / "live-news", timeout=1200)
    if not pretip:
        sh("next UFC card", [py, UPD / "ufc_upcoming.py", ROOT])
    run_dir = WORK / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    # run_updates.py prints PROBLEMS: ... at the end; its own failed steps don't stop the upload (same as the Claude task)
    print(f"\n##### models, grading and page (run_updates.py)  ({datetime.now(ET):%I:%M %p ET})", flush=True)
    try:  # pass its output through, and count the steps it reports as failed in its last "PROBLEMS:" line
        p = subprocess.Popen([py, str(ROOT / "live-news" / "run_updates.py"), str(ROOT), str(run_dir)],
                             cwd=ROOT / "live-news", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        last = ""
        for line in p.stdout:
            print(line, end="", flush=True)
            if line.startswith("PROBLEMS:"):
                last = line.split(":", 1)[1].strip()
        p.wait(timeout=3600)
        if p.returncode:
            problems.append("run_updates.py crashed")
        elif last and last != "none":
            problems.append(f"run_updates: {last}")
    except Exception as e:  # noqa: BLE001
        print("run_updates.py:", e)
        problems.append("run_updates.py")
    page = ROOT / "sports-app" / "matchup-predictor.html"
    if page.exists() and time.time() - page.stat().st_mtime < 3 * 3600:
        publish()
    else:
        print("page was not rebuilt this run, upload skipped")
        problems.append("page not rebuilt")


def nfl_run():
    if sh("NFL refresh (nflverse)", [py, UPD / "nfl_refresh.py", ROOT, WORK / "nfl"], timeout=5400):
        build_page() and publish()


def retrain_run():
    if sh("weekly UFC retrain", [py, ROOT / "auto-retrain" / "retrain_ufc.py", ROOT, WORK / "ufc"],
          cwd=ROOT / "auto-retrain", timeout=5400):
        build_page() and publish()


if __name__ == "__main__":
    load_settings()
    LOGS.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    problems = []
    started = datetime.now(timezone.utc)
    print(f"Matchup Predictor updater: {MODE} run, {datetime.now(ET):%a %b %d %I:%M %p ET}", flush=True)
    # new features and fixes from the cloud copy (Claude threads), plus the updater's own scripts; never blocks the run
    sh("code sync", [py, UPD / "sync_in.py"], timeout=1200) or problems.remove("code sync")
    if MODE == "full":
        news_run(pretip=False)
    elif MODE == "pretip":
        if nba_games_today(late_only=datetime.now(ET).hour >= 21):
            news_run(pretip=True)
        else:
            print("no NBA games left tonight: nothing to do")
    elif MODE == "nfl":
        nfl_run()
    elif MODE == "retrain":
        retrain_run()
    elif MODE == "opening" and os.environ.get("PUBLISH_FILE", "picks-mac.html") != "picks.html":
        # while testing beside the Claude tasks, those already save opening lines; this keeps PropLine's free
        # 1,000 requests a day from running out
        print("test period: opening snapshot left to the Claude task")
    elif MODE == "opening":
        sh("opening odds snapshot", [py, ROOT / "live-news" / "opening_snapshot.py"], cwd=ROOT / "live-news", timeout=1200)
    else:
        sys.exit(f"unknown mode {MODE}")
    mins = (datetime.now(timezone.utc) - started).seconds // 60
    end = f"{datetime.now(ET):%Y-%m-%d %I:%M %p ET}  {MODE}  {mins} min  problems: {', '.join(problems) or 'none'}"
    (LOGS / f"last_{MODE}.txt").write_text(end + "\n")
    with open(LOGS / "history.txt", "a") as f:
        f.write(end + "\n")
    print("\nDONE:", end)
