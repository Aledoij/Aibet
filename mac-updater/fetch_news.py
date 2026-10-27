"""Plain-Python news fetch for the Matchup Predictor (replaces the Claude WebFetch step of the news task).

Makes live-news/raw/<UTC YYYY-MM-DDTHHMMZ>/ and writes the same CSVs, with the same columns, that the Claude news
task wrote (see live-news/README.md). A source that fails is copied from the newest earlier snapshot (except
nba_prop_lines.csv: PropLine fills that one later), so one broken page never blocks the run.

Usage: python fetch_news.py <project dir> <mode>
  mode = full      : everything (11:47am ET run also gets rosters + yesterday's box scores, see FULL_EXTRA_HOUR)
         pretip    : copy the newest snapshot, refetch only NBA lineups, injuries and news
Betting odds are never read here (PropLine prices are saved by propline_lines.py for comparison only).
"""
import csv
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(sys.argv[1])
MODE = sys.argv[2] if len(sys.argv) > 2 else "full"
RAW = ROOT / "live-news" / "raw"
ET = ZoneInfo("America/New_York")
now_utc = datetime.now(timezone.utc)
now_et = now_utc.astimezone(ET)
today = now_et.date()
FULL_EXTRA_HOUR = 13  # full runs before 1pm ET (the 11:47am one) also fetch rosters and yesterday's box scores

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/130.0 Safari/537.36")

NBA = {  # abbreviation -> full name as the app writes it
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets", "BRK": "Brooklyn Nets", "CHA": "Charlotte Hornets",
    "CHO": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets", "DET": "Detroit Pistons", "GS": "Golden State Warriors", "GSW": "Golden State Warriors",
    "HOU": "Houston Rockets", "IND": "Indiana Pacers", "LAC": "LA Clippers", "LAL": "Los Angeles Lakers",
    "MEM": "Memphis Grizzlies", "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NO": "New Orleans Pelicans", "NOP": "New Orleans Pelicans", "NY": "New York Knicks", "NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHO": "Phoenix Suns",
    "PHX": "Phoenix Suns", "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SA": "San Antonio Spurs",
    "SAS": "San Antonio Spurs", "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "UTAH": "Utah Jazz", "WAS": "Washington Wizards",
    "WSH": "Washington Wizards"}
NBA_FULL = set(NBA.values())


def get(url, tries=3):
    for i in range(tries):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200 and len(r.text) > 2000:
                return r.text
            print(f"  {url}: HTTP {r.status_code}")
            if r.status_code == 429:
                time.sleep(30)
        except requests.RequestException as e:
            print(f"  {url}: {e}")
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"could not fetch {url}")


def soup(url):
    return BeautifulSoup(get(url), "lxml")


def txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def slug_team(href, league_full):
    """/nba/teams/ATL/atlanta-hawks/ -> Atlanta Hawks (LA Clippers kept as the app writes it)."""
    m = re.search(r"/teams/([A-Z]+)/([a-z0-9-]+)", href or "")
    if not m:
        return ""
    if league_full is NBA_FULL and m.group(1) in NBA:
        return NBA[m.group(1)]
    name = " ".join(w.capitalize() for w in m.group(2).split("-"))
    return name.replace("49Ers", "49ers")


def write(snap, name, header, rows):
    with open(snap / name, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    print(f"  {name}: {len(rows)} rows")


# ------------------------------------------------------------------ sources
def cbs_injuries(snap, league, only_qb=False):
    s = soup(f"https://www.cbssports.com/{league}/injuries/")
    rows = []
    for w in s.select(".TableBaseWrapper"):
        a = w.select_one(".TeamName a") or w.select_one("a[href*='/teams/']")
        team = slug_team(a.get("href") if a else "", NBA_FULL if league == "nba" else None)
        for tr in w.select("tbody tr"):
            td = tr.find_all("td")
            if len(td) < 5:
                continue
            player = txt(td[0].select_one(".CellPlayerName--long")) or txt(td[0])
            pos = txt(td[1])
            if only_qb and pos != "QB":
                continue
            rows.append([team, player, pos, txt(td[2]), txt(td[3]), txt(td[4])])
    if len({r[0] for r in rows}) < (5 if only_qb else 15):
        raise RuntimeError(f"CBS {league} injuries: only {len(rows)} rows, page layout changed?")
    write(snap, "nfl_qb_injuries.csv" if only_qb else "nba_injuries.csv",
          ["team", "player", "position", "updated", "injury", "status"], rows)


def rw_lineups(snap):
    s = soup("https://www.rotowire.com/basketball/nba-lineups.php")
    m = re.search(r"Starting lineups for (\w+ \d+, \d{4})", txt(s.select_one(".page-title__secondary")) or s.get_text())
    day = datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat() if m else today.isoformat()
    rows = []
    for g in s.select("div.lineup.is-nba"):
        if "is-tools" in g.get("class", []):
            continue
        ab = [txt(x) for x in g.select(".lineup__abbr")]
        if len(ab) != 2 or ab[0] not in NBA or ab[1] not in NBA:
            continue
        away, home = NBA[ab[0]], NBA[ab[1]]
        for side, team, opp, h in (("is-visit", away, home, 0), ("is-home", home, away, 1)):
            ul = g.select_one(f"ul.lineup__list.{side}")
            if not ul:
                continue
            may_not = False
            for li in ul.find_all("li", recursive=False):
                if "lineup__title" in li.get("class", []):
                    may_not = True
                    continue
                if "lineup__player" not in li.get("class", []):
                    continue
                a = li.find("a")
                name = (a.get("title") or txt(a)) if a else ""
                inj = txt(li.select_one(".lineup__inj"))
                if not name:
                    continue
                if not may_not:  # listed starter (also tagged Ques/Prob/... when the page shows a tag)
                    rows.append([day, team, opp, h, name, "starter"])
                if inj:
                    rows.append([day, team, opp, h, name, inj])
    if not rows:
        raise RuntimeError("RotoWire lineups: no games found")
    write(snap, "nba_lineups.csv", ["date", "team", "opponent", "home", "player", "role"], rows)


def rw_news_items(url):
    s = soup(url)
    out = []
    for n in s.select(".news-update"):
        try:
            d = datetime.strptime(txt(n.select_one(".news-update__timestamp")), "%B %d, %Y").date()
        except ValueError:
            d = today
        meta = n.select_one(".news-update__meta div")
        pos = txt(meta.select_one(".news-update__pos")) if meta else ""
        team = txt(meta)[len(pos):].strip() if meta else ""
        out.append(dict(date=d, player=txt(n.select_one(".news-update__player-link")),
                        headline=txt(n.select_one(".news-update__headline")), team=team,
                        text=txt(n.select_one(".news-update__news")).replace(" .", ".").replace(" ,", ","),
                        links=[txt(a) for a in n.select(".news-update__news a[href*='/player/']")]))
    return out


def rw_nba_news(snap):
    items = rw_news_items("https://www.rotowire.com/basketball/news.php")
    if not items:
        raise RuntimeError("RotoWire NBA news: no items")
    with open(snap / "nba_news.csv", "w", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writerow(["date", "player", "team", "headline", "text"])
        for i in items:
            w.writerow([i["date"].isoformat(), i["player"], i["team"], i["headline"], i["text"]])
    print(f"  nba_news.csv: {len(items)} rows")


KINDS = [("weight_miss", r"missed weight|miss(es|ed)? (the )?weight|catchweight|over the (division|non-title) limit"),
         ("cancelled", r"cancel|scrapped|no longer (fight|face)|called off|off the card|removed from the card"),
         ("withdrawal", r"withdr[ae]w|pulled out|pull out|out of (his|her|the) (bout|fight)|injur|will not fight|dropped from|forced out"),
         ("replacement", r"replac|short[- ]notice|steps? in|will (now )?(take on|face|fight|meet)|accepted|new opponent|stepping in")]


def rw_mma_news(snap):
    items = rw_news_items("https://www.rotowire.com/mma/news.php")
    rows = []
    for i in items:
        if (today - i["date"]).days > 10 or i["team"] not in ("UFC", ""):
            continue
        t = (i["headline"] + " " + i["text"]).lower()
        kind = next((k for k, rx in KINDS if re.search(rx, t)), "other")
        if kind == "other":
            continue
        ev = re.search(r"UFC (Fight Night|Vegas|Paris|London|Abu Dhabi|Macau|Rio|Perth|Qatar|Nashville|Seattle)?\s?\d{2,3}", i["text"])
        fighters = [i["player"]] + [x for x in i["links"] if x and x != i["player"]]
        first = re.sub(r",? (per|according to) [^.]*\.?$", "", i["text"]).rstrip(".")
        rows.append([i["date"].isoformat(), ev.group(0) if ev else "", ";".join(fighters), kind, first])
    write(snap, "ufc_news.csv", ["date", "event", "fighters", "kind", "text"], rows)


def bfo_card(snap):
    """Next UFC event's fights (names only) from bestfightodds."""
    s = soup("https://www.bestfightodds.com/")
    for t in s.select("div.table-div"):
        h1 = txt(t.select_one(".table-header h1"))
        if not h1.startswith("UFC"):
            continue
        event = re.sub(r"\s*Odds$", "", h1)
        dtxt = re.sub(r"(st|nd|rd|th)$", "", txt(t.select_one(".table-header-date")))
        try:
            d = datetime.strptime(f"{dtxt} {today.year}", "%B %d %Y").date()
            if d < today - timedelta(days=60):
                d = d.replace(year=today.year + 1)
        except ValueError:
            continue
        names, rows = [], []
        tb = t.select_one("table.odds-table tbody") or t
        for tr in tb.find_all("tr", recursive=False):
            nm = txt(tr.select_one("th a span") or tr.select_one("th a"))
            if not nm:
                continue
            if tr.get("id", "").startswith("mu-"):
                names = [nm]
            elif len(names) == 1:
                rows.append([event, d.isoformat(), names[0], nm])
                names = []
        if rows:
            write(snap, "ufc_card.csv", ["event", "date", "a", "b"], rows)
            return
    raise RuntimeError("bestfightodds: no UFC event found")


def espn_results(snap, days=(1, 2), box_day=None):
    """Final scores (and, for box_day, every player's line) from ESPN's public scoreboard + summary feeds.
    (The Claude task read basketball-reference; it blocks plain scripts, ESPN does not. Same columns.)"""
    rows, box = [], []
    base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
    for k in days:
        d = today - timedelta(days=k)
        js = S.get(f"{base}/scoreboard?dates={d:%Y%m%d}", timeout=40).json()
        for e in js.get("events", []):
            c = e["competitions"][0]
            if c["status"]["type"].get("name") != "STATUS_FINAL":
                continue
            t = {x["homeAway"]: x for x in c["competitors"]}
            away, home = t["away"]["team"]["displayName"], t["home"]["team"]["displayName"]
            rows.append([d.isoformat(), away, t["away"]["score"], home, t["home"]["score"], int(c["status"].get("period", 4) > 4)])
            if box_day == k:
                sm = S.get(f"{base}/summary?event={e['id']}", timeout=40).json()
                for tp in sm.get("boxscore", {}).get("players", []):
                    st = tp["statistics"][0]
                    ix = {l: i for i, l in enumerate(st["labels"])}
                    for a in st.get("athletes", []):
                        v = a.get("stats") or []
                        mins = int(v[ix["MIN"]]) if v and v[ix["MIN"]].isdigit() else 0
                        g = lambda lab: (v[ix[lab]].split("-")[0] if mins else 0)  # noqa: E731
                        box.append([d.isoformat(), tp["team"]["displayName"], a["athlete"]["displayName"], mins,
                                    g("PTS"), g("REB"), g("AST"), g("3PT")])
                time.sleep(0.3)
    if not rows:
        raise RuntimeError("ESPN: no finished NBA games in the last two days")
    write(snap, "nba_results.csv", ["date", "away", "away_pts", "home", "home_pts", "ot"], rows)
    if box_day:
        write(snap, "nba_player_box.csv", ["date", "team", "player", "minutes", "pts", "reb", "ast", "fg3m"], box)


def cbs_rosters(snap):
    s = soup("https://www.cbssports.com/nba/teams/")
    links = sorted({a["href"] for a in s.select("a[href*='/nba/teams/']") if re.search(r"/nba/teams/[A-Z]+/[a-z0-9-]+/?$", a["href"])})
    rows = []
    for href in links:
        url = "https://www.cbssports.com" + href.rstrip("/").split("cbssports.com")[-1] + "/roster/"
        team = slug_team(href, NBA_FULL)
        try:
            r = soup(url)
        except RuntimeError as e:
            print("  roster skipped:", e)
            continue
        for tr in r.select("table.TableBase-table tbody tr"):
            p = txt(tr.select_one(".CellPlayerName--long a")) or txt(tr.select_one(".CellPlayerName--long"))
            if p:
                rows.append([team, p])
        time.sleep(1)
    if len({r[0] for r in rows}) < 25:
        raise RuntimeError(f"CBS rosters: only {len({r[0] for r in rows})} teams")
    write(snap, "nba_rosters.csv", ["team", "player"], rows)


# ------------------------------------------------------------------ run
def main():
    prev = sorted(p for p in RAW.iterdir() if p.is_dir() and not p.name.startswith("backfill") and p.name[:2] == "20")
    snap = RAW / now_utc.strftime("%Y-%m-%dT%H%MZ")
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "meta.txt").write_text(f"fetched_at={now_utc.strftime('%Y-%m-%dT%H:%MZ')}\nsource=mac-updater ({MODE})\n")
    last = prev[-1] if prev and prev[-1] != snap else None

    def carry(name):
        if last and (last / name).exists() and not (snap / name).exists():
            shutil.copyfile(last / name, snap / name)
            print(f"  {name}: copied from {last.name}")

    if MODE == "pretip" and last:  # keep everything this run doesn't refetch
        for f in last.glob("*.csv"):
            if f.name != "nba_prop_lines.csv":
                shutil.copyfile(f, snap / f.name)
    jobs = [("nba_lineups.csv", rw_lineups), ("nba_injuries.csv", lambda s: cbs_injuries(s, "nba")),
            ("nba_news.csv", rw_nba_news)]
    if MODE == "full":
        morning = now_et.hour < FULL_EXTRA_HOUR or os.environ.get("MP_MORNING") == "1"
        jobs += [("nba_results.csv", lambda s: espn_results(s, box_day=1 if morning else None)),
                 ("ufc_card.csv", bfo_card), ("ufc_news.csv", rw_mma_news)]
        if now_et.month >= 9 or now_et.month <= 2:
            jobs.append(("nfl_qb_injuries.csv", lambda s: cbs_injuries(s, "nfl", only_qb=True)))
        if morning:
            jobs.append(("nba_rosters.csv", cbs_rosters))
    failed = []
    for name, fn in jobs:
        print("==", name)
        try:
            fn(snap)
        except Exception as e:  # noqa: BLE001  one broken source never blocks the rest
            print(f"  FAILED: {e}")
            failed.append(name)
            (snap / name).unlink(missing_ok=True)
            carry(name)
    if MODE == "full":  # files this run didn't fetch (results in the evening, rosters, QB report out of season)
        for f in ("nba_results.csv", "nfl_qb_injuries.csv", "ufc_card.csv", "ufc_news.csv"):
            carry(f)
    print("SNAPSHOT", snap)
    print("FETCH PROBLEMS:", failed or "none")


if __name__ == "__main__":
    main()
