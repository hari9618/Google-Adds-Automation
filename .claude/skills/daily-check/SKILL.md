---
name: daily-check
description: Use when the person says "turn on the daily check", "turn off the daily check" or asks whether it is on. Installs or removes the 7 AM timer that runs the read-only daily review.
---

Windows: `powershell -File scripts\daily-check.ps1 -Install` (or `-Uninstall`, or `-Status`).
Mac / Linux: `bash scripts/daily-check.sh --install` (or `--uninstall`, `--status`).

Run the right one for this machine, then tell the person:
- it runs every day at 7 AM and only reads and suggests (it cannot change the account);
- a laptop that is asleep at 7 runs it when it wakes; one that is shut down skips that day;
- the emergency pause runs inside Google and does not need the laptop.
