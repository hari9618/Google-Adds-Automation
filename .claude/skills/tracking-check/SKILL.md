---
name: tracking-check
description: Use when the person asks whether trials are being counted ("is tracking working?", "why are conversions zero?", "can we trust cost per trial?"), before raising a budget, and once a week in the weekly review. The analyst reads the conversion setup and says in plain English whether the numbers can be trusted. Read-only; it never changes the account.
---

Our version of the "is conversion tracking trustworthy?" check that Google-Ads-Copilot
(`google-ads-tracking`), claude-ads (`audit-tracking`), marketingskills (`conversion-tracking`) and
Google's developer assistant (`troubleshoot-conversions`) all have. Tracked in `upstream/catalog.json`.

**Why it matters here:** every suggestion the optimizer makes and every budget raise rests on "trials".
If the trial conversion is missing, doubled or counting the wrong thing, the agents optimise noise.

1. Hand it to the **analyst** sub-agent. It runs these through `mcp__google-ads__search_search`
   (if one is refused for a field name, look the field up with `metadata_get_resource_metadata`):
   - The setup:
     `SELECT customer.auto_tagging_enabled, customer.conversion_tracking_setting.conversion_tracking_status
      FROM customer`
   - The conversion actions:
     `SELECT conversion_action.name, conversion_action.status, conversion_action.type,
      conversion_action.category, conversion_action.counting_type, conversion_action.primary_for_goal,
      conversion_action.include_in_conversions_metric FROM conversion_action`
   - What each action recorded, last 30 days:
     `SELECT segments.conversion_action_name, metrics.conversions, metrics.all_conversions
      FROM customer WHERE segments.date DURING LAST_30_DAYS`
2. Judge it against these, in this order, and say which ones fail:
   - Auto-tagging is on (without it Google cannot tie a signup to a click).
   - There is exactly **one** enabled, primary conversion for a **trial signup**, counted **once per
     click** (`ONE_PER_CLICK`). Two primary signup actions means trials are counted twice.
   - Page views, clicks on the pricing page and other soft actions are **not** primary (they make cost
     per trial look better than it is).
   - The trial action recorded something in the last 30 days if there were clicks. Clicks with zero
     trials for 30 days is a tracking question before it is an ads question.
3. Answer in 3 to 6 short lines: **Trustworthy / Not yet / Broken**, the failing checks in plain words,
   and what a person has to do (in the CaughtLeads app or in Google Ads; the agents cannot fix it).
   Until the Google tag and trial conversion exist (README, "Not built yet"), the answer is
   "Not yet: trials are not tracked", never a guess.
4. If it is not trustworthy, say so at the top of the next daily report, and the optimizer must not
   propose budget raises until it is.
