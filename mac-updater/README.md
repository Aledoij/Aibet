# Matchup Predictor updater for Alex's Mac (no Claude needed)

Started 2026-10-27 ("Run app updates without Claude" thread). Does on Alex's MacBook what the Claude scheduled tasks
did: fetch the news, sportsbook lines (compare only), rebuild models/grades/page, and upload picks to GitHub
(Aledoij/Aibet) for the Mac and iPhone apps. Odds never feed a model, pick or grade. No tennis. Times ET.

## On the Mac: ~/MatchupPredictor-Updater/
- `project/`   copy of the project files the runs use (the cloud's /mnt/project-files paths are rewritten to here)
- `updater/`   these scripts
- `venv/`, `browsers/`  Python 3.13 + packages, Chromium (Playwright), installed by `install.sh`
- `settings.env`  PROPLINE_API_KEY, GITHUB_TOKEN, PUBLISH_FILE (chmod 600; never copied anywhere)
- `repo/`  clone of Aledoij/Aibet used for uploads; `logs/` one log per run + `history.txt`
- Double-click helpers: `Set up keys.command`, `Update now.command`, `Check updater.command`

## Schedule (launchd, ~/Library/LaunchAgents/com.matchuppredictor.*.plist; `updater/schedule.py install|remove|status`)
| mode | when (ET) | replaces Claude task |
|---|---|---|
| full | 11:47am, 5:47pm | News and model refresh (twice daily ET) + UFC part of Matchup Predictor odds refresh |
| pretip | 6:17pm, 9:17pm (NBA nights only) | NBA pre-tip-off refresh |
| nfl | Wed + Sat 10:31am | Matchup Predictor NFL refresh |
| retrain | Tue 6:13am | Weekly model retrain |
| opening | 10:07am, 11:07pm | Opening odds snapshot (skipped while PUBLISH_FILE is not picks.html, to stay under PropLine's 1,000 requests/day) |

## What changed vs the Claude tasks
- WebFetch pages -> `fetch_news.py` (requests + BeautifulSoup): CBS NBA injuries, RotoWire lineups + NBA news, CBS
  NBA rosters (11:47 run), CBS NFL QB injuries, bestfightodds UFC card, RotoWire MMA fight changes (kind found by
  keywords, text = the blurb without the source credit). Same CSV columns as live-news/README.md.
- NBA results + box scores now from ESPN's public feeds (basketball-reference blocks scripts). ESPN minutes are whole
  numbers; names have no accents.
- Dropped: VegasInsider NBA prop lines (PropLine fills nba_prop_lines.csv) and the "extra odds" task (PropLine game
  lines win in build_page anyway); bettorsinsider NBA odds (ESPN schedule + PropLine cover it).
- Not on the Mac: publishing the claude.ai artifact link, the 12:43pm "Daily picks" chat message, and the Claude
  check-in/report threads (they read /mnt/project-files, which stops updating once the Mac takes over).
- Test period: uploads go to `picks-mac.html` (the apps read `picks.html`), so the Claude runs stay in charge until
  Alex agrees to switch. Switch: set PUBLISH_FILE=picks.html in settings.env, copy fresh project data, then turn off
  the Claude tasks (ask Alex first).
