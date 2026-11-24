"""The suggestion inbox: inbox/items/<id>.json. Standard library only.

  python tools/inbox.py list            waiting items, oldest first, numbered
  python tools/inbox.py check           every item is well-formed (used by the tests)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "inbox" / "items"
STATUSES = {"waiting", "done", "skipped", "refused"}
REQUIRED = ("id", "created", "by", "status", "title", "why", "change")
KINDS = {"pause_campaign", "enable_campaign", "set_daily_budget", "add_negative_keywords",
         "create_search_campaign", "add_responsive_search_ad"}


def load(items_dir: Path = ITEMS) -> list[dict]:
    out = []
    for f in sorted(items_dir.glob("*.json")):
        item = json.loads(f.read_text(encoding="utf-8"))
        item["_file"] = f.name
        out.append(item)
    return out


def problems(item: dict) -> list[str]:
    bad = [f"missing {k}" for k in REQUIRED if k not in item]
    if item.get("status") not in STATUSES:
        bad.append(f"status must be one of {sorted(STATUSES)}")
    if not isinstance(item.get("change"), dict) or item["change"].get("kind") not in KINDS:
        bad.append(f"change.kind must be one of {sorted(KINDS)}")
    return bad


def waiting(items_dir: Path = ITEMS) -> list[dict]:
    return sorted((i for i in load(items_dir) if i.get("status") == "waiting"),
                  key=lambda i: (i.get("created", ""), i.get("id", "")))


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "list"
    if cmd == "list":
        items = waiting()
        if not items:
            print("Nothing waiting.")
        for n, i in enumerate(items, 1):
            print(f"{n}. [{i['id']}] {i['title']}\n   why: {i['why']}")
        return 0
    if cmd == "check":
        bad = {i["_file"]: problems(i) for i in load() if problems(i)}
        for f, p in bad.items():
            print(f"{f}: {'; '.join(p)}")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
