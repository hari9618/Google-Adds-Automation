---
name: report
description: Use when the person asks how the ads did ("how did ads do yesterday?", "why did cost per trial go up?", "what did we spend this month?"). The analyst reads the account and answers in plain English. Read-only.
---

1. Hand the question to the **analyst** sub-agent with the period (default: yesterday).
2. Answer in 3 to 6 short lines: spend vs budget, clicks, trials and cost per trial, the biggest waste,
   anything broken (disapproved ad, landing page). Numbers first.
3. For "yesterday" questions, the analyst also writes `reports/YYYY-MM-DD.md` and `reports/latest.json`.
4. End with one line: how many suggestions are waiting (`inbox/items/*.json` with status "waiting").
