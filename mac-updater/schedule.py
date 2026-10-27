"""Turn the updater's schedule on or off on this Mac (launchd jobs in ~/Library/LaunchAgents).

Usage: python schedule.py install | remove | status
Times are US Eastern. If the Mac's clock is set to another time zone they are converted (and re-run install after a
daylight-saving change). A job missed while the Mac was asleep runs once when it wakes up.
"""
import plistlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

H = Path.home() / "MatchupPredictor-Updater"
AGENTS = Path.home() / "Library" / "LaunchAgents"
LABEL = "com.matchuppredictor.{}"
ET = ZoneInfo("America/New_York")
# mode -> list of (weekday or None for every day [0 = Sunday], hour ET, minute)
SCHEDULE = {
    "full": [(None, 11, 47), (None, 17, 47)],
    "pretip": [(None, 18, 17), (None, 21, 17)],
    "opening": [(None, 10, 7), (None, 23, 7)],
    "nfl": [(3, 10, 31), (6, 10, 31)],
    "retrain": [(2, 6, 13)],
}


def to_local(wd, h, m):
    now = datetime.now(ET)
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    loc = t.astimezone()  # this Mac's time zone
    shift = (loc.date() - t.date()).days
    d = {"Hour": loc.hour, "Minute": loc.minute}
    if wd is not None:
        d["Weekday"] = (wd + shift) % 7
    return d


def install():
    AGENTS.mkdir(parents=True, exist_ok=True)
    (H / "logs").mkdir(exist_ok=True)
    tz = datetime.now().astimezone().tzname()
    if datetime.now(ET).utcoffset() != datetime.now().astimezone().utcoffset():
        print(f"note: this Mac's clock is not on Eastern time ({tz}); times converted for now")
    for mode, times in SCHEDULE.items():
        label = LABEL.format(mode)
        f = AGENTS / f"{label}.plist"
        plist = {"Label": label, "ProgramArguments": ["/bin/bash", str(H / "updater" / "run.sh"), mode],
                 "StartCalendarInterval": [to_local(*t) for t in times],
                 "StandardOutPath": str(H / "logs" / "launchd.out"), "StandardErrorPath": str(H / "logs" / "launchd.err"),
                 "ProcessType": "Background"}
        subprocess.run(["launchctl", "unload", str(f)], capture_output=True)
        with open(f, "wb") as fh:
            plistlib.dump(plist, fh)
        subprocess.run(["launchctl", "load", "-w", str(f)], check=True)
        print(f"{mode:8s} on:", ", ".join(f"{['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][t[0]] + ' ' if t[0] is not None else ''}"
                                         f"{(datetime(2000, 1, 1, t[1], t[2])).strftime('%-I:%M %p')} ET" for t in times))


def remove():
    for mode in SCHEDULE:
        f = AGENTS / f"{LABEL.format(mode)}.plist"
        subprocess.run(["launchctl", "unload", "-w", str(f)], capture_output=True)
        f.unlink(missing_ok=True)
        print(mode, "off")


def status():
    out = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
    for mode in SCHEDULE:
        print(f"{mode:8s}", "scheduled" if LABEL.format(mode) in out else "NOT scheduled")
    for f in sorted((H / "logs").glob("last_*.txt")):
        print(f.read_text().strip())


if __name__ == "__main__":
    {"install": install, "remove": remove, "status": status}[sys.argv[1] if len(sys.argv) > 1 else "status"]()
