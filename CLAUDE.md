# CaughtLeads Ads

This repo runs CaughtLeads' Google Ads from a Claude Code chat. A person types what they want in plain
English; a skill picks it up; four sub-agents do the work; **nothing that spends money or changes an ad
happens until the person clicks Allow**.

CaughtLeads (caughtleads.com) sells an AI receptionist to US home-services contractors (HVAC, plumbing,
electrical, roofing): it answers their calls, qualifies the caller, books the appointment and shows which
booked appointments were held. Pricing: $49/month plus usage. The ads aim at **free trial signups**.

## The one rule

**Never change the Google Ads account except through the Apply connector** (`mcp__apply__*`).
- Read with Google's connector (`mcp__google-ads__search_search` and its two metadata tools). It is
  configured read-only, and the guard hook blocks every other google-ads tool.
- Change with `mcp__apply__preview_change`, show the person the summary, then
  `mcp__apply__apply_change`. Claude Code asks the person to Allow every apply. Never look for another way.
- `mcp__apply__pause_campaigns` is the exception: stopping spend is always safe and needs no Allow.
- Never edit `settings/limits.json`, `settings/copy_rules.json`, `.claude/settings.json`, `.mcp.json`,
  `apply/` or anything in `secrets/`. The guard hook blocks it; a person edits those by hand.
- Never run this repo with "skip permissions". Even then the Apply tool refuses anything over the limits.

## Who does what

| Agent | Job | Can change the account? |
|---|---|---|
| `builder` | Turns a brief into a campaign plan, previews it | No (preview only) |
| `operator` | Makes approved changes, pauses | Yes, through Apply, with Allow |
| `analyst` | Reads results, writes reports in plain English | No |
| `optimizer` | Reads reports, writes suggestions to the inbox | No |

Work moves between agents through files:
- `briefs/<slug>.md`: a campaign request, as the person said it, plus their answers.
- `reports/YYYY-MM-DD.md` and `reports/latest.json`: the Analyst's output (format in the `report` skill).
- `inbox/items/<id>.json`: the Optimizer's suggestions (format in the `inbox` skill).
- `log/changes.jsonl`: every change made, before and after, with its undo. Written by Apply only.

## Copy rules (also enforced in code: settings/copy_rules.json)

- Never "answers every call", "never miss a call" or any absolute about answering.
- Say **appointment**, never "job".
- Never promise revenue, money, more customers or any outcome.
- Never "TCPA-compliant" or any legal claim. Never "#1" or "best".
- No en or em dashes. No "!" in headlines. Plain, specific, honest.
- Google's limits: 3 to 15 headlines of at most 30 characters, 2 to 4 descriptions of at most 90.

## How to talk to the person

Plain English, short, numbers first. Money in dollars, not micros. Say what you are about to do, what it
will cost per day at most, and that it starts switched off. Never say a change was made until
`apply_change` returned `done`.
