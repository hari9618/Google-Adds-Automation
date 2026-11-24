---
name: daily-review
description: The 7 AM review, run by the timer (scripts/daily-check) or by hand. The analyst writes yesterday's report and the optimizer adds up to 3 suggestions to the inbox. Reads and suggests only; it never changes the account.
---

This runs with nobody watching, so it must never change anything: no apply_change, no pause.

1. **analyst**: write `reports/<yesterday>.md` and `reports/latest.json` for yesterday.
2. **optimizer**: read the report and add at most 3 suggestions to `inbox/items/`.
3. Print one line: "Yesterday $X spent, N trials, M suggestions waiting." That is all.

If the read connector fails (sign-in expired, no access), write `reports/latest.json` with
`"headline": "the daily review could not read the account: <reason>"` so the next chat shows it.
