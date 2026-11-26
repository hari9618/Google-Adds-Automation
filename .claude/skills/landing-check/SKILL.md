---
name: landing-check
description: Use when the person asks about the page an ad sends people to ("is the landing page OK?", "people click but don't sign up", "check caughtleads.com/hvac"), before launching a new campaign, and when clicks are steady but trials drop. Checks that the page answers the ad, works on a phone and leads to the free trial. Read-only.
---

Our version of the landing-page review in Google-Ads-Copilot (`google-ads-landing-review`,
`audit-landing`) and claude-ads (`ads-landing`). Tracked in `upstream/catalog.json`. Their most useful
idea is kept: **separate a tracking problem from a page problem first**; they look the same ("clicks,
no trials") and need different fixes.

1. **Tracking first.** If `/tracking-check` has not said "Trustworthy" this week, run it. If tracking is
   broken, stop and say that is the problem; a page review would be guessing.
2. **Which page and which ads.** Have the **analyst** read the final URL and the headlines of the
   enabled ads that point at it:
   `SELECT ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.headlines, campaign.name,
    metrics.clicks, metrics.conversions FROM ad_group_ad
    WHERE ad_group_ad.status = 'ENABLED' AND segments.date DURING LAST_30_DAYS`
3. **Look at the page** (WebFetch the URL; `curl -s -o /dev/null -w "%{http_code} %{time_total}"` for
   status and time). Check, and name every failure:
   - It answers **200**, over https, in under about 3 seconds.
   - **Message match:** the first screen says what the ad promised (the trade, the problem: missed and
     after-hours calls). An ad for "HVAC answering service" landing on a generic home page is a fail.
   - **One clear next step:** the free trial, visible without scrolling, working on a phone.
   - **Same promises as the ad, and both within the copy rules** (`settings/copy_rules.json`): no
     "answers every call", no revenue or outcome promise, "appointment" not "job". A page breaking the
     rules is reported for the website team; the agents never edit the site.
   - The price shown matches the pricing page ($49/month plus usage, free trial).
4. Answer in 3 to 6 short lines: **Good / Needs work / Broken**, what fails, and who fixes it (the
   website, or an ad pointing at the wrong page). A wrong final URL can become an inbox suggestion for
   the optimizer; a page fix is for a person.
