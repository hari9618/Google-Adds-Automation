"""The Apply connector: the ONLY way this repo changes the Google Ads account.

An MCP server (stdio) that Claude Code starts from .mcp.json. Its tools:

  preview_change   check + Google test run; returns a preview id and before/after. Changes nothing.
  apply_change     make a previewed change. .claude/settings.json puts this tool on "ask", so
                   Claude Code shows you an Allow prompt every single time.
  pause_campaigns  switch campaigns off now (all live ones if none named). Stopping spend is
                   always safe, so it needs no preview.
  undo_change      preview the reverse of a logged change (it then needs apply_change + Allow).
  recent_changes   the last entries of log/changes.jsonl.

Run: python -m apply.server
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from apply.core import Applier, Preview, Refused

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_FILE = ROOT / "settings" / "account.json"

server = MCPServer("caughtleads-apply", instructions=(
    "The only way to change the CaughtLeads Google Ads account. Always preview_change first and show the "
    "person the summary; apply_change needs their Allow. Never try to change the account any other way."))

_applier: Applier | None = None


def applier() -> Applier:
    global _applier
    if _applier is None:
        from apply.gateway import GoogleGateway

        acct = json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))
        customer = str(acct.get("customer_id", "")).replace("-", "")
        if not customer.isdigit():
            raise Refused("settings/account.json has no customer_id yet (the Google Ads account number, digits only)")
        if not (ROOT / "secrets" / "google-ads.yaml").exists():
            raise Refused("secrets/google-ads.yaml is missing: run the Google sign-in step in README.md first")
        _applier = Applier(GoogleGateway(customer, str(acct.get("login_customer_id", "")).replace("-", "")))
    return _applier


def _show(p: Preview) -> dict[str, Any]:
    return {"preview_id": p.id, "will": p.summary, "before": p.before, "after": p.after,
            "google_test_run": "passed", "next": "call apply_change with this preview_id; the person must click Allow"}


def _safe(fn: Any) -> dict[str, Any]:
    try:
        return fn()
    except Refused as e:
        return {"refused": str(e)}


@server.tool()
def preview_change(change: dict[str, Any]) -> dict[str, Any]:
    """Check a change and test-run it with Google. Changes NOTHING.

    `change` has a `kind` and its fields:
      pause_campaign / enable_campaign: campaign_id
      set_daily_budget: campaign_id, daily_budget (US dollars)
      add_negative_keywords: campaign_id, keywords (list of text), match_type (EXACT|PHRASE|BROAD)
      create_search_campaign: name, daily_budget, final_url, locations (geo target ids), keywords
        ([{text, match_type}]), negative_keywords, headlines (3-15, max 30 chars), descriptions (2-4, max 90)
      add_responsive_search_ad: ad_group_id, final_url, headlines, descriptions
    """
    return _safe(lambda: _show(applier().preview(change)))


@server.tool()
def apply_change(preview_id: str) -> dict[str, Any]:
    """Make a previewed change for real. Re-checks every limit first. Logged with an undo."""
    return _safe(lambda: {"done": applier().apply(preview_id)})


@server.tool()
def pause_campaigns(campaign_ids: list[str] | None = None) -> dict[str, Any]:
    """Switch campaigns off now. With no ids: every live campaign. Always allowed, always logged."""
    return _safe(lambda: {"paused": [e["summary"] for e in applier().pause(campaign_ids)]})


@server.tool()
def undo_change(change_id: str) -> dict[str, Any]:
    """Preview the reverse of a logged change. It still has to go through apply_change and Allow."""
    return _safe(lambda: _show(applier().undo_preview(change_id)))


@server.tool()
def recent_changes(limit: int = 20) -> dict[str, Any]:
    """The last changes made through this tool, newest first."""
    path = ROOT / "log" / "changes.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []
    return {"changes": [{k: r[k] for k in ("id", "at", "summary", "undo")} for r in reversed(rows[-limit:])]}


if __name__ == "__main__":
    server.run("stdio")
