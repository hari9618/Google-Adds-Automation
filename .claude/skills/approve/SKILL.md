---
name: approve
description: Use when the person approves or skips inbox suggestions ("approve 1 and 2, skip 3", "do that", "yes to the headline test"). The operator makes each approved change through the Apply connector; the person clicks Allow on each.
---

1. Map the numbers to the inbox items you last listed. If you did not list them in this conversation,
   list them first and ask again (never guess which item "1" is).
2. Skipped items: set `status` to `skipped` (add `"skipped_note"` if the person gave a reason, e.g. "next week").
3. Approved items: hand them to the **operator**, one change each. The person clicks Allow per change.
4. Report one line per item: done (before and after), refused (the reason) or declined.
