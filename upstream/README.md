# Upstream sync: keeping the Ads agents current

This repo was built from other people's repos: Google's Ads API client and read connector, Google's
own Ads skills and developer assistant, Claude Code, and several ads skill sets (adloop, claude-ads,
marketingskills, google-ads-copilot, negative_keyword_cleaner, free-google-ads-scripts). They
change every week. This folder is how we notice, without anything changing on its own.

## How it works

```
Every Monday (GitHub Actions, upstream-sync.yml)
   |
   |  for each repo in sources.json that is due (every 7, 14 or 28 days):
   |    1. UPDATED?  "what changed in the files we watch since the commit we last took?"
   |    2. MISSING?  "which skills/agents in its catalog folder have we never reviewed?"
   |
   |-- nothing changed, nothing new ............... done, no PR, no noise
   |
   '-- something changed or turned up
         |
         v
   ONE pull request, branch upstream-sync
     - moves the pins in sources.json (and in .mcp.json for Google's read connector)
     - adds reports/<date>.md: what changed, the commits, the text diff,
       which of OUR files came from that repo, and the new upstream skills
     - changes none of our skills or agents
         |
         v
   Someone adapts our files on that branch
     - by hand, or /upstream-sync in Claude Code (our own Claude plan), or
     - the optional "adapt" job in GitHub (off by default)
     adopts the new skills worth having (our own version), records every decision in
     catalog.json, and writes reports/<date>-review.md: changed / left for a person / not for us
         |
         v
   tests.yml passes, a person merges. Never automatic.
```

If a PR is still open the next Monday, the new report is added to the same branch, on top of any
edits already made there.

## Why Google's read connector is pinned

`.mcp.json` runs `google-ads-mcp` at one exact commit. Before, it ran whatever was newest on Google's
`main`, so a new connector tool could appear overnight, and some of its tools change the account.
Now a new version only arrives through the sync PR, where a person reads what changed first. The
three read-only rails (its `tools_config.yaml`, the denied tools in `.claude/settings.json`, the
guard hook) stay as they were.

## The files

| File | What it is |
|---|---|
| `sources.json` | The list: each upstream repo, the files we watch in it, which of our files came from it, how often to check, and the exact commit we last took (the "pin"). Only the script moves a pin. The guard hook stops agents editing it. |
| `catalog.json` | Our decision on every upstream skill/agent we have looked at: adopted (and where), later, or skipped (and why). Anything not in here is listed as new in the next report. |
| `reports/<date>.md` | What changed upstream that week, and the new skills/agents to review. Written by the script. |
| `reports/<date>-review.md` | What we did about it. Written by whoever adapted our files. |
| `../scripts/upstream_sync.py` | The checker. Standard-library Python, no AI. |
| `../.claude/skills/upstream-sync/` | The `/upstream-sync` skill that adapts our files. |
| `../.github/workflows/upstream-sync.yml` | The weekly run. `tests.yml` runs the tests on every PR. |

## Commands

```bash
python scripts/upstream_sync.py status                    # every source, how old its pin is
python scripts/upstream_sync.py check --force --dry-run   # what a run would report today; changes nothing
python scripts/upstream_sync.py diff claude-ads OLD NEW   # the full diff behind one report section
python scripts/upstream_sync.py init                      # pin a source you just added
```

## Safety

- **Upstream text is someone else's.** In reports it sits in fenced blocks only, and the skill treats
  it as information, never as commands.
- **Code and config are never copied.** An upstream change to a script, hook or config file is
  marked "needs a careful read" and is ported by a person, with the tests run.
  `free-google-ads-scripts` is GPL-3.0: ideas only, never its code.
- **Limits, copy rules, the guard and the Allow prompts are never loosened** because an upstream does
  it differently.
- **The optional adapt job in GitHub** can only read and edit files (no shell, no web, no push
  credentials). A guard then rejects any edit outside our derived, non-code files, and any edit to
  the sync itself, the workflows, hooks, settings, `.mcp.json` or CLAUDE.md, before anything is
  pushed.
- **Nothing merges itself.**

## What this does not cover

- **Python packages** (`google-ads`, `mcp`): Dependabot (`.github/dependabot.yml`) opens those PRs.
- **The Google Ads API itself**: Google announces version sunsets in the google-ads-python ChangeLog,
  which this does watch.
