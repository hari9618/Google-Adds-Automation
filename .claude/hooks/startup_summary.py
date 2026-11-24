"""SessionStart: one line when the chat opens. Yesterday's numbers, waiting suggestions, recent pauses.
Reads local files only (reports/latest.json, inbox/items, log/changes.jsonl). Standard library only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def summary(root: Path = ROOT) -> str:
    parts: list[str] = []
    latest = root / "reports" / "latest.json"
    if latest.exists():
        try:
            r = json.loads(latest.read_text(encoding="utf-8"))
            parts.append(f"{r.get('date', '?')}: ${float(r.get('spend_usd', 0)):,.2f} spent, "
                         f"{r.get('trials', r.get('conversions', 0))} trials")
            if r.get("headline"):
                parts.append(str(r["headline"]))
        except (ValueError, TypeError):
            parts.append("the latest report could not be read")
    else:
        parts.append("no report yet (say \"how did ads do yesterday?\" or set up the daily check)")
    waiting = 0
    for f in (root / "inbox" / "items").glob("*.json"):
        try:
            waiting += json.loads(f.read_text(encoding="utf-8")).get("status") == "waiting"
        except ValueError:
            continue
    parts.append(f"{waiting} suggestion(s) waiting" if waiting else "inbox empty")
    log = root / "log" / "changes.jsonl"
    if log.exists():
        lines = [x for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
        if lines:
            last = json.loads(lines[-1])
            parts.append(f"last change {last.get('at', '?')[:10]}: {last.get('summary', '')}")
    return "CaughtLeads Ads: " + " · ".join(parts)


def main() -> None:
    try:
        text = summary()
    except Exception as e:
        text = f"CaughtLeads Ads: start-up summary unavailable ({type(e).__name__})"
    print(json.dumps({"systemMessage": text,
                      "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
