---
name: inbox
description: Use when the person asks what is waiting ("what's waiting for me?", "show the inbox", "any suggestions?"). Lists the waiting suggestions, numbered, each with its reason.
---

1. Run `uv run --no-project --quiet python tools/inbox.py list` (or read `inbox/items/*.json` with status
   "waiting", oldest first).
2. Show them numbered 1, 2, 3 in the order listed: the title, then the reason in one line with its numbers.
   Keep the inbox id next to each number so "approve 1" maps to the right item.
3. End with: "Approve, skip, or ask about any of them."

Item format (written by the optimizer): `id`, `created`, `by`, `status` (waiting | done | skipped | refused),
`title`, `why`, `change` (what the Apply tool accepts), `risk`.
