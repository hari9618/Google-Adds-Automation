---
name: new-campaign
description: Use when the person wants a new Google Ads campaign or new ads, e.g. "make a campaign for HVAC owners in Texas, $20 a day". Saves the brief, has the builder plan and preview it, then creates it switched off after the person clicks Allow.
---

1. **Brief.** From the message, collect: who (trade), where (states or cities), daily budget in dollars,
   landing page (https://caughtleads.com/...), goal (default: free trial signups), words to avoid.
   Ask at most two short questions for anything missing. Never guess the budget.
2. Save it as `briefs/<short-slug>.md` (the person's words, then the answers).
3. Hand it to the **builder** sub-agent: "Build a campaign from briefs/<slug>.md".
4. Show the person the builder's plan in 5 to 6 lines: keyword count with 3 examples, blocked-search count,
   3 example headlines, daily budget, "copy rules passed, Google's test run passed", "it will be created
   switched off". Then ask: "Create it switched off?"
5. On yes: hand the preview id to the **operator** to apply (the person clicks Allow). Say: "Created and
   switched off. Nothing is spending. Say 'launch <name>' when you're ready."
6. "Launch <name>": the operator previews `{"kind": "enable_campaign", "campaign_id": ...}` and applies it
   (Allow). If the limits refuse it, say which limit and stop.
