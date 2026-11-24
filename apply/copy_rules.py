"""Ad copy rules. Checked twice: by a hook before the Apply tool is called, and inside the Apply tool
itself, so a rule cannot be skipped by calling the tool some other way.

Two kinds of rule:
  * Google's own limits for responsive search ads (counts, lengths, no "!" in a headline, no
    shouting), so a change does not fail at Google after you clicked Allow;
  * CaughtLeads' claims rules (settings/copy_rules.json): things we must never say in an ad.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = ROOT / "settings" / "copy_rules.json"

HEADLINE_MAX, DESCRIPTION_MAX = 30, 90
HEADLINES_MIN, HEADLINES_MAX = 3, 15
DESCRIPTIONS_MIN, DESCRIPTIONS_MAX = 2, 4


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: str
    why: str


def load_rules(path: Path | None = None) -> tuple[list[Rule], set[str]]:
    data = json.loads((path or RULES_FILE).read_text(encoding="utf-8"))
    rules = [Rule(r["id"], r["pattern"], r["why"]) for r in data["banned"]]
    return rules, {w.upper() for w in data.get("allowed_caps", [])}


def check_text(text: str, kind: str, rules: list[Rule], allowed_caps: set[str]) -> list[str]:
    """Problems with one headline or description; [] when it is fine."""
    problems: list[str] = []
    limit = HEADLINE_MAX if kind == "headline" else DESCRIPTION_MAX
    if not text.strip():
        problems.append(f"{kind} is empty")
    if len(text) > limit:
        problems.append(f"{kind} is {len(text)} characters, the limit is {limit}: {text!r}")
    if kind == "headline" and "!" in text:
        problems.append(f"Google does not allow '!' in a headline: {text!r}")
    shouting = [w for w in re.findall(r"\b[A-Z]{4,}\b", text) if w not in allowed_caps]
    if shouting:
        problems.append(f"words in capitals ({', '.join(shouting)}) break Google's capitalisation rule: {text!r}")
    for r in rules:
        if re.search(r.pattern, text, re.I):
            problems.append(f"breaks copy rule '{r.id}' ({r.why}): {text!r}")
    return problems


def check_ad(headlines: list[str], descriptions: list[str], rules_path: Path | None = None) -> list[str]:
    """Every problem with one responsive search ad. [] means it may go to Google."""
    rules, caps = load_rules(rules_path)
    problems: list[str] = []
    if not HEADLINES_MIN <= len(headlines) <= HEADLINES_MAX:
        problems.append(f"{len(headlines)} headlines: Google needs {HEADLINES_MIN} to {HEADLINES_MAX}")
    if not DESCRIPTIONS_MIN <= len(descriptions) <= DESCRIPTIONS_MAX:
        problems.append(f"{len(descriptions)} descriptions: Google needs {DESCRIPTIONS_MIN} to {DESCRIPTIONS_MAX}")
    dupes = {h for h in headlines if [x.lower() for x in headlines].count(h.lower()) > 1}
    if dupes:
        problems.append(f"repeated headlines: {sorted(dupes)}")
    for h in headlines:
        problems += check_text(h, "headline", rules, caps)
    for d in descriptions:
        problems += check_text(d, "description", rules, caps)
    return problems
