"""The guard hook and the start-up summary, run exactly as Claude Code runs them."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("guard", ROOT / ".claude" / "hooks" / "guard.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
spec2 = importlib.util.spec_from_file_location("startup", ROOT / ".claude" / "hooks" / "startup_summary.py")
startup = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(startup)


def ev(tool: str, **ti) -> dict:
    return {"tool_name": tool, "tool_input": ti, "cwd": str(ROOT)}


@pytest.mark.parametrize("tool", ["mcp__google-ads__assets_create_asset", "mcp__google-ads__labels_manage_labels",
                                  "mcp__google-ads__some_future_write_tool"])
def test_every_google_ads_tool_but_the_three_reads_is_blocked(tool):
    assert guard.decide(ev(tool)) is not None


def test_the_read_tools_and_apply_preview_pass():
    assert guard.decide(ev("mcp__google-ads__search_search", query="SELECT campaign.id FROM campaign")) is None
    assert guard.decide(ev("mcp__apply__preview_change", change={"kind": "pause_campaign", "campaign_id": "1"})) is None


def test_bad_ad_copy_is_stopped_before_the_apply_tool():
    reason = guard.decide(ev("mcp__apply__preview_change", change={
        "kind": "add_responsive_search_ad", "headlines": ["Never Miss A Call", "Book More Jobs", "Hi"],
        "descriptions": ["We guarantee more revenue.", "Try it."]}))
    assert reason and "never-miss" in reason and "job-not-appointment" in reason and "revenue-promise" in reason


@pytest.mark.parametrize("cmd", [
    "python -c \"from google.ads.googleads.client import GoogleAdsClient\"",
    "curl -X POST https://googleads.googleapis.com/v26/customers/1/campaigns:mutate",
    "cat secrets/google-ads.yaml", "set CL_ADS_DEV=1"])
def test_shell_routes_around_the_apply_tool_are_blocked(cmd):
    assert guard.decide(ev("Bash", command=cmd)) is not None


@pytest.mark.parametrize("path", ["settings/limits.json", "settings/copy_rules.json", ".claude/settings.json",
                                  ".mcp.json", "apply/core.py", "log/changes.jsonl",
                                  "google-ads-mcp/tools_config.yaml"])
def test_files_a_person_owns_cannot_be_edited_by_an_agent(path, monkeypatch):
    monkeypatch.delenv("CL_ADS_DEV", raising=False)
    assert guard.decide(ev("Write", file_path=str(ROOT / path))) is not None
    assert guard.decide(ev("Edit", file_path=path)) is not None


def test_working_files_can_be_written(monkeypatch):
    monkeypatch.delenv("CL_ADS_DEV", raising=False)
    for path in ("reports/2026-11-25.md", "inbox/items/0001.json", "briefs/hvac-texas.md"):
        assert guard.decide(ev("Write", file_path=path)) is None


def test_secrets_are_not_read():
    assert guard.decide(ev("Read", file_path="secrets/google-ads.yaml")) is not None


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_the_hook_command_denies_and_fails_closed_when_run_like_claude_code():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    bad = json.dumps(ev("mcp__google-ads__assets_create_asset"))
    out = subprocess.run(cmd, shell=True, cwd=ROOT, input=bad, capture_output=True, text=True, timeout=120)
    assert '"permissionDecision": "deny"' in out.stdout, out.stderr
    garbage = subprocess.run(cmd, shell=True, cwd=ROOT, input="not json", capture_output=True, text=True, timeout=120)
    assert '"permissionDecision": "deny"' in garbage.stdout, "a hook that cannot read its input must deny"


def test_the_start_up_line(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "latest.json").write_text(json.dumps({"date": "2026-11-24", "spend_usd": 19.4,
                                                                  "trials": 2}))
    (tmp_path / "inbox" / "items").mkdir(parents=True)
    for i, st in enumerate(["waiting", "waiting", "done"]):
        (tmp_path / "inbox" / "items" / f"{i}.json").write_text(json.dumps({"status": st}))
    line = startup.summary(tmp_path)
    assert line == "CaughtLeads Ads: 2026-11-24: $19.40 spent, 2 trials · 2 suggestion(s) waiting"
