#!/bin/bash
# Double-click me. Saves your PropLine key and GitHub token for the Matchup Predictor updater (only on this Mac).
H="$HOME/MatchupPredictor-Updater"; F="$H/settings.env"
touch "$F"; chmod 600 "$F"
get() { grep -E "^$1=" "$F" | head -1 | cut -d= -f2-; }
put() { grep -v -E "^$1=" "$F" > "$F.tmp"; echo "$1=$2" >> "$F.tmp"; mv "$F.tmp" "$F"; chmod 600 "$F"; }
echo "Matchup Predictor updater: keys"
echo
echo "1) PropLine API key (from your prop-line.com account). Paste it and press Return (just Return keeps the saved one):"
read -r -s k; [ -n "$k" ] && put PROPLINE_API_KEY "$k" && echo "   saved"
echo
echo "2) GitHub token for Aledoij/Aibet (github.com > Settings > Developer settings > Fine-grained tokens)."
echo "   Paste it and press Return (just Return keeps the saved one):"
read -r -s t; [ -n "$t" ] && put GITHUB_TOKEN "$t" && echo "   saved"
[ -z "$(get PUBLISH_FILE)" ] && put PUBLISH_FILE picks-mac.html
echo
echo "Checking..."
k=$(get PROPLINE_API_KEY); t=$(get GITHUB_TOKEN)
[ -n "$k" ] && curl -s -o /dev/null -w "   PropLine: HTTP %{http_code} (200 = OK)\n" -H "X-API-Key: $k" "https://api.prop-line.com/v1/sports" || echo "   PropLine: no key saved"
[ -n "$t" ] && git ls-remote "https://x-access-token:$t@github.com/Aledoij/Aibet.git" HEAD >/dev/null 2>&1 && echo "   GitHub: OK" || echo "   GitHub: token missing or not working"
echo
echo "Done. You can close this window."
