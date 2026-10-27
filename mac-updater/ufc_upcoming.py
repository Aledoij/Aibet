"""Next UFC card -> sports-app/export/upcoming.json["ufc"] (replaces the Claude "odds refresh" task's UFC part).

Reads the newest live-news/raw/*/ufc_card.csv (bestfightodds names, written by fetch_news.py) and rewrites the "ufc"
key with that card's fights, names mapped to the app's fighter keys. Odds are left empty here: PropLine fills them
in build_page.py (compare only, never a model input). Fights already listed keep their saved odds. Other keys
(nba, nfl) are not touched.
Usage: python ufc_upcoming.py <project dir>
"""
import csv
import difflib
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(sys.argv[1])
EXPORT = ROOT / "sports-app" / "export"
today = str(datetime.now(ZoneInfo("America/New_York")).date())
cards = sorted(p for p in (ROOT / "live-news" / "raw").glob("*/ufc_card.csv") if not p.parent.name.startswith("backfill"))
rows = list(csv.DictReader(open(cards[-1]))) if cards else []
if not rows or rows[0]["date"] < today:
    print("ufc upcoming: no future card in the newest snapshot, left as is")
    sys.exit(0)
norm = lambda n: re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower())  # noqa: E731
keys = {norm(n): n for n in json.load(open(EXPORT / "ufc.json"))["entities"]}


def name(n):
    k = norm(n)
    if k in keys:
        return keys[k]
    c = difflib.get_close_matches(k, list(keys), n=1, cutoff=0.9)
    return keys[c[0]] if c else n


up = json.load(open(EXPORT / "upcoming.json"))
old = up.get("ufc") or {}
odds = {frozenset((g["a"], g["b"])): g for g in old.get("games", [])}
games = []
for r in rows:
    a, b = name(r["a"]), name(r["b"])
    g = odds.get(frozenset((a, b)))
    games.append({"a": a, "b": b, "oa": g.get("oa") if g and g["a"] == a else g.get("ob") if g else None,
                  "ob": g.get("ob") if g and g["a"] == a else g.get("oa") if g else None, "date": r["date"]})
up["ufc"] = {"title": rows[0]["event"], "date": rows[0]["date"], "fetched": today,
             "source": "bestfightodds.com card (names); odds from PropLine", "games": games}
tmp = EXPORT / "upcoming.json.tmp"
json.dump(up, open(tmp, "w"), indent=1)
tmp.replace(EXPORT / "upcoming.json")
print(f"ufc upcoming: {rows[0]['event']} {rows[0]['date']}, {len(games)} fights")
