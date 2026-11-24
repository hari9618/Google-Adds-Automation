# caughtleads-ads

CaughtLeads' Google Ads, run from a Claude Code chat. You type what you want; a skill picks it up; four
sub-agents (Builder, Operator, Analyst, Optimizer) do the work. **Nothing that spends money or changes an ad
happens until you click Allow.** It runs on the Claude Code plan: no API key, no per-use AI bill.

| You type | What happens | Your click? |
|---|---|---|
| "Make a campaign for HVAC owners in Texas, $20 a day, send them to caughtleads.com/hvac" | Builder plans and test-runs it | Allow to create it (switched off), Allow again to launch |
| "How did ads do yesterday?" | Analyst answers in plain English | No |
| "What's waiting for me?" | The Optimizer's suggestions, numbered | No |
| "Approve 1 and 2, skip 3" | Operator makes those changes | Allow on each |
| "Pause everything" | Done at once | No |
| "Turn on the daily check" | 7 AM read-only review on this computer | No |

## How it is kept safe (in code, not just instructions)

- **Agents only read.** Google's connector is configured read-only (`google-ads-mcp/tools_config.yaml`), its
  write tools are denied in `.claude/settings.json`, and the guard hook blocks every google-ads tool except
  the three read tools.
- **One way to change the account: the Apply connector** (`apply/`). `preview_change` checks the copy rules
  and the spending limits and asks Google to test-run the change (`validate_only`: nothing changes).
  `apply_change` is on "ask", so Claude Code shows you Allow every time; it re-checks the limits against
  the account as it is at that moment, then makes the change.
- **Hard limits** (`settings/limits.json`, edited by a person only): daily cap, monthly cap (Google can
  spend up to 2x a daily budget in a day, so the month is tracked separately), the biggest new-campaign
  budget, at most +20% budget a week with 7 days between raises. While the caps are 0 nothing can spend.
- **New campaigns and ads start switched off.** Launching is a separate Allow.
- **Every change is logged** in `log/changes.jsonl` with before, after and its undo.
- **Emergency pause inside Google** (`google-scripts/emergency-pause.js`), hourly, works with every laptop off.
- **The guard hook fails closed**, and Claude Code's "skip permissions" mode is disabled for this repo.

## Setup (once)

1. **Tools:** [Claude Code](https://claude.com/claude-code), [uv](https://docs.astral.sh/uv/),
   [pipx](https://pipx.pypa.io/), the [gcloud CLI](https://cloud.google.com/sdk/docs/install), Python 3.11+.
   Then `uv sync` in this folder.
2. **Google Cloud project** with the Google Ads API enabled, and an OAuth client (Desktop app).
3. **Google Ads API developer token**: Google Ads (the manager account) > Tools > API Center. A new token
   starts at test access. Apply for Basic access for live accounts and for Keyword Planner (the Builder
   uses it for search volumes).
4. **Read connector sign-in** (Google's google-ads-mcp):
   `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform --client-id-file=<your OAuth client json>`
   Then set `GOOGLE_APPLICATION_CREDENTIALS` (the path gcloud prints) and `GOOGLE_CLOUD_PROJECT` in your
   environment, and `GOOGLE_ADS_LOGIN_CUSTOMER_ID` if access goes through a manager account. If the
   connector asks for the developer token, follow its README.
5. **Apply connector sign-in:** `secrets/google-ads.yaml` in Google's standard format (`developer_token`,
   `client_id`, `client_secret`, `refresh_token`, `login_customer_id`, `use_proto_plus: True`).
   `secrets/` is git-ignored and blocked from every agent.
6. **Account and limits:** fill `settings/account.json` (customer id) and `settings/limits.json` (daily
   cap, monthly cap, biggest new-campaign budget). Until the caps are set, nothing can spend.
7. **Emergency pause:** paste `google-scripts/emergency-pause.js` into Google Ads > Tools > Scripts, set its
   CONFIG (emails, the same monthly cap), Preview, then schedule it hourly.
8. **Open this folder in Claude Code** and say "how did ads do yesterday?". Optional: "turn on the daily check".

## Layout

```
CLAUDE.md                who we are, copy rules, the one rule
.mcp.json                google-ads (Google's, read-only) + apply (ours)
.claude/agents/          builder, operator, analyst, optimizer
.claude/skills/          new-campaign, report, inbox, approve, pause, daily-review, weekly-review, daily-check
.claude/hooks/           guard.py (fails closed), startup_summary.py
.claude/settings.json    allow reads, ASK for apply_change, deny Google's write tools, hooks
apply/                   the Apply connector (MCP server) on Google's google-ads library
settings/                limits.json, copy_rules.json, account.json (a person edits these)
briefs/ inbox/items/ reports/ log/
google-scripts/          emergency-pause.js (runs inside Google)
scripts/                 daily-check.ps1 / .sh (the 7 AM timer)
tools/inbox.py           list and check the inbox
```

## Develop

`uv run pytest` and `uv run ruff check .`. To edit protected files from inside Claude Code, start it from
a shell with `CL_ADS_DEV=1` (never for day-to-day use).

## Not built yet (from the plan)

- **Measurement** (in the CaughtLeads app, not here): the Google tag on caughtleads.com and the ad click id
  saved with every signup. Until then the Analyst reports clicks and cost, not trials.
- **Closing the loop:** sending trials and paid customers back to Google (Data Manager API) from the
  CaughtLeads backend, nightly.
