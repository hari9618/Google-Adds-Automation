#!/usr/bin/env bash
# The 7 AM daily review (read and suggest only). Mac (launchd) or Linux (cron).
#   bash scripts/daily-check.sh               run it once now
#   bash scripts/daily-check.sh --install [HH:MM]
#   bash scripts/daily-check.sh --uninstall | --status
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.caughtleads.ads-daily-review"
AT="${2:-07:00}"
HOUR="${AT%%:*}"; MIN="${AT##*:}"

case "${1:-run}" in
  --install)
    if [[ "$(uname)" == "Darwin" ]]; then
      PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
      cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$REPO/scripts/daily-check.sh</string></array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>$((10#$HOUR))</integer><key>Minute</key><integer>$((10#$MIN))</integer></dict>
</dict></plist>
PLIST
      launchctl unload "$PLIST" 2>/dev/null || true
      launchctl load "$PLIST"
    else
      (crontab -l 2>/dev/null | grep -v "$LABEL"; echo "$((10#$MIN)) $((10#$HOUR)) * * * cd $REPO && bash scripts/daily-check.sh # $LABEL") | crontab -
    fi
    echo "Installed: the daily review runs every day at $AT (read and suggest only)."
    exit 0 ;;
  --uninstall)
    if [[ "$(uname)" == "Darwin" ]]; then
      launchctl unload "$HOME/Library/LaunchAgents/$LABEL.plist" 2>/dev/null || true
      rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
    else
      (crontab -l 2>/dev/null | grep -v "$LABEL") | crontab - || true
    fi
    echo "Removed."; exit 0 ;;
  --status)
    if [[ -f "$HOME/Library/LaunchAgents/$LABEL.plist" ]] || crontab -l 2>/dev/null | grep -q "$LABEL"; then
      echo "On."; else echo "Off: the daily check is not installed."; fi
    exit 0 ;;
esac

mkdir -p "$REPO/log"
LOG="$REPO/log/daily-review.log"
cd "$REPO"
echo "$(date -u +%FT%TZ)  start" >> "$LOG"
READ_TOOLS="Read,Write,Glob,Grep,Task,Bash(uv run --no-project --quiet python tools/inbox.py:*),mcp__google-ads__search_search,mcp__google-ads__metadata_get_resource_metadata,mcp__google-ads__customers_list_accessible_customers,mcp__apply__preview_change"
BLOCKED="mcp__apply__apply_change,mcp__apply__pause_campaigns,mcp__apply__undo_change"
set +e
claude -p "/daily-review" --allowedTools "$READ_TOOLS" --disallowedTools "$BLOCKED" >> "$LOG" 2>&1
code=$?
echo "$(date -u +%FT%TZ)  end exit=$code" >> "$LOG"
exit $code
