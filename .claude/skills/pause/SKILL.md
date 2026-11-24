---
name: pause
description: Use at once when the person says pause, stop, "pause everything", "turn the ads off" or anything urgent about spend. Stopping spend is always safe and needs no approval.
---

1. Call `mcp__apply__pause_campaigns` immediately: no ids for "everything", or the ids of the named
   campaigns (look them up with the read connector if only a name was given).
2. Say what was paused, in one line per campaign. If nothing was live, say so.
3. Do not ask questions first. Explaining why comes after the spend has stopped.
