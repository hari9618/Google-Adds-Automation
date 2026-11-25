"""PreToolUse guard: the rules that must hold whatever an agent is told. Standard library only.

Blocks:
  * any google-ads connector tool except the three read tools (it ships tools that change the account);
  * an Apply preview whose ad copy breaks the copy rules (Apply checks again; this just says it sooner);
  * shell commands that reach the Google Ads API or its credentials directly, around the Apply tool;
  * reading secrets/, and editing the files a person owns: the limits, the copy rules, the account,
    the Claude settings, the connector config, the hooks, the Apply code and the change log.

Fails CLOSED: if anything goes wrong in here, the tool call is denied. (A hook that crashes is treated
by Claude Code as "allow", which would switch the guard off silently.)

Developing the repo itself: set CL_ADS_DEV=1 in the shell that starts Claude Code to allow edits to
the protected files. Never set it for day-to-day use.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READ_TOOLS = {"mcp__google-ads__search_search", "mcp__google-ads__metadata_get_resource_metadata",
              "mcp__google-ads__customers_list_accessible_customers"}
PROTECTED = ("settings/limits.json", "settings/copy_rules.json", "settings/account.json", ".claude/settings.json",
             ".claude/hooks/", ".mcp.json", "google-ads-mcp/", "apply/", "secrets/", "log/changes.jsonl",
             "upstream/sources.json", ".github/")
SHELL_BLOCK = re.compile(r"googleads\.googleapis|google\.ads\.googleads|GoogleAdsClient|google-ads\.yaml|"
                         r"secrets[/\\]|application_default_credentials|CL_ADS_DEV", re.I)


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


def rel(path: str, cwd: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd or ROOT) / p
    try:
        return p.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return p.resolve().as_posix()


def is_protected(r: str) -> bool:
    return any(r == p.rstrip("/") or r.startswith(p) for p in PROTECTED)


def decide(event: dict) -> str | None:
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    cwd = event.get("cwd", "")
    dev = os.environ.get("CL_ADS_DEV") == "1"

    if tool.startswith("mcp__google-ads__") and tool not in READ_TOOLS:
        return (f"{tool} can change the Google Ads account. This repo only reads through google-ads; "
                "every change goes through the Apply connector (mcp__apply__preview_change).")

    if tool == "mcp__apply__preview_change":
        change = ti.get("change") or {}
        if change.get("headlines") or change.get("descriptions"):
            sys.path.insert(0, str(ROOT))
            from apply.copy_rules import check_ad

            problems = check_ad(list(change.get("headlines") or []), list(change.get("descriptions") or []))
            if problems:
                return "The ad copy breaks the rules, so it was not sent:\n- " + "\n- ".join(problems)

    if tool in ("Bash", "PowerShell"):
        cmd = str(ti.get("command", ""))
        if SHELL_BLOCK.search(cmd):
            return ("That command reaches the Google Ads API, its credentials or the guard's switch directly. "
                    "Read with the google-ads connector and change with the Apply connector.")

    if tool in ("Read", "Grep", "Glob"):
        target = str(ti.get("file_path") or ti.get("path") or "")
        if target and rel(target, cwd).startswith("secrets/"):
            return "secrets/ holds the Google sign-in. Nothing in this repo reads it except the Apply connector."
        if tool != "Read" and "secrets" in str(ti.get("pattern", "")):
            return "secrets/ holds the Google sign-in and is not searched."

    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit") and not dev:
        target = str(ti.get("file_path") or ti.get("notebook_path") or "")
        if target and is_protected(rel(target, cwd)):
            return (f"{rel(target, cwd)} is owned by a person (limits, copy rules, settings, the Apply code or "
                    "the change log). Tell the person what you would change and why; they edit it by hand.")
    return None


def main() -> None:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        reason = decide(event)
    except Exception as e:  # fail closed
        deny(f"The guard could not check this call ({type(e).__name__}), so it is blocked.")
        return
    if reason:
        deny(reason)


if __name__ == "__main__":
    main()
