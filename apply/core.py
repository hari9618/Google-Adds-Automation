"""Preview -> Allow -> apply, with the limits and the log. No AI in here.

  preview(change)  checks the change (shape, copy rules, spending limits), reads the account, asks
                   Google to TEST-RUN it (validate_only: nothing changes), and keeps the result in
                   memory under a preview id. It returns what would change, before and after.
  apply(id)        only a fresh preview can be applied. It re-reads the account and re-checks the
                   limits (the account may have changed since), makes the change for real, and
                   writes it to log/changes.jsonl with before, after and how to undo it.
  pause(...)       stopping spend is always safe: no preview, no limits, still logged.

Previews live only in this process's memory, so nothing on disk can be edited into an approval.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from apply.copy_rules import check_ad
from apply.gateway import MICROS, CampaignState, Gateway

ROOT = Path(__file__).resolve().parents[1]
LIMITS_FILE = ROOT / "settings" / "limits.json"
LOG_DIR = ROOT / "log"
PREVIEW_TTL_S = 30 * 60
DAYS_PER_MONTH = 30.4          # Google's own figure for a monthly budget from a daily one
MATCH_TYPES = {"EXACT", "PHRASE", "BROAD"}


class Refused(Exception):
    """A change the Apply tool will not make. The message says why, in plain words."""


@dataclass
class Preview:
    id: str
    change: dict[str, Any]
    ops: list[dict[str, Any]]
    summary: str
    before: dict[str, Any]
    after: dict[str, Any]
    undo: dict[str, Any] | None
    created: float = field(default_factory=time.time)


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def usd(micros: int) -> str:
    return f"${micros / MICROS:,.2f}"


class Applier:
    def __init__(self, gateway: Gateway, limits_file: Path = LIMITS_FILE, log_dir: Path = LOG_DIR) -> None:
        self.gw = gateway
        self.limits_file = limits_file
        self.log_dir = log_dir
        self.previews: dict[str, Preview] = {}

    # --------------------------------------------------------------- helpers
    def limits(self) -> dict[str, Any]:
        lim = json.loads(self.limits_file.read_text(encoding="utf-8"))
        return {k: v for k, v in lim.items() if not k.startswith("_")}

    def _campaign(self, campaigns: list[CampaignState], campaign_id: str) -> CampaignState:
        for c in campaigns:
            if c.id == str(campaign_id):
                return c
        raise Refused(f"there is no campaign {campaign_id} in this account")

    def _log(self, entry: dict[str, Any]) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with (self.log_dir / "changes.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def history(self) -> list[dict[str, Any]]:
        path = self.log_dir / "changes.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # ---------------------------------------------------------------- limits
    def _spend_limits(self, lim: dict[str, Any], enabled_daily_micros: int) -> None:
        """Refuse anything that lets the account spend past a cap."""
        daily_cap = int(float(lim.get("daily_cap_usd") or 0) * MICROS)
        monthly_cap = int(float(lim.get("monthly_cap_usd") or 0) * MICROS)
        if daily_cap <= 0 or monthly_cap <= 0:
            raise Refused("the spending limits in settings/limits.json are not filled in (they are 0), so "
                          "nothing that can spend is allowed. A person sets them by hand.")
        if enabled_daily_micros > daily_cap:
            raise Refused(f"the live campaigns' daily budgets would add up to {usd(enabled_daily_micros)}, over the "
                          f"daily limit of {usd(daily_cap)}")
        if enabled_daily_micros * DAYS_PER_MONTH > monthly_cap:
            raise Refused(f"at {usd(enabled_daily_micros)} a day the account could spend "
                          f"{usd(int(enabled_daily_micros * DAYS_PER_MONTH))} a month, over the monthly limit of "
                          f"{usd(monthly_cap)}")
        mtd = self.gw.month_to_date_cost_micros()
        if mtd >= monthly_cap:
            raise Refused(f"this month has already spent {usd(mtd)}, the monthly limit is {usd(monthly_cap)}")

    def _last_increase(self, campaign_id: str) -> datetime | None:
        for e in reversed(self.history()):
            if (e.get("kind") == "set_daily_budget" and str(e["change"].get("campaign_id")) == str(campaign_id)
                    and e["after"].get("daily_budget_micros", 0) > e["before"].get("daily_budget_micros", 0)):
                return datetime.strptime(e["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        return None

    # --------------------------------------------------------------- preview
    def plan(self, change: dict[str, Any]) -> Preview:
        """Check one change and work out its before/after, without Google's test run."""
        kind = change.get("kind")
        lim = self.limits()
        campaigns = self.gw.campaigns()
        enabled = sum(c.daily_budget_micros for c in campaigns if c.status == "ENABLED")

        if kind in ("pause_campaign", "enable_campaign"):
            c = self._campaign(campaigns, change["campaign_id"])
            target = "PAUSED" if kind == "pause_campaign" else "ENABLED"
            if c.status == target:
                raise Refused(f"'{c.name}' is already {target.lower()}")
            if target == "ENABLED":
                self._spend_limits(lim, enabled + c.daily_budget_micros)
            undo = {"kind": "enable_campaign" if target == "PAUSED" else "pause_campaign", "campaign_id": c.id}
            return self._new(change, [{"op": "campaign_status", "campaign_id": c.id, "status": target}],
                             f"{'switch off' if target == 'PAUSED' else 'switch on'} '{c.name}'",
                             {"status": c.status}, {"status": target}, undo)

        if kind == "set_daily_budget":
            c = self._campaign(campaigns, change["campaign_id"])
            if c.budget_shared:
                raise Refused(f"'{c.name}' uses a shared budget; change it in Google Ads by hand")
            new = round(float(change["daily_budget"]) * MICROS)
            if new <= 0:
                raise Refused("a daily budget must be more than $0 (to stop spending, pause the campaign)")
            if new > c.daily_budget_micros:
                pct = float(lim.get("max_budget_increase_pct_per_week", 20))
                if new > c.daily_budget_micros * (1 + pct / 100):
                    raise Refused(f"raising '{c.name}' from {usd(c.daily_budget_micros)} to {usd(new)} is more than "
                                  f"the {pct:g}% a week the limits allow")
                last = self._last_increase(c.id)
                wait = int(lim.get("min_days_between_increases", 7))
                if last and datetime.now(UTC) - last < timedelta(days=wait):
                    raise Refused(f"'{c.name}' was last raised on {last:%d %b}; the limits ask for {wait} days "
                                  "between increases")
                if c.status == "ENABLED":
                    self._spend_limits(lim, enabled - c.daily_budget_micros + new)
            undo = {"kind": "set_daily_budget", "campaign_id": c.id, "daily_budget": c.daily_budget_micros / MICROS}
            return self._new(change, [{"op": "budget_amount", "budget_resource": c.budget_resource,
                                       "amount_micros": new}],
                             f"daily budget of '{c.name}': {usd(c.daily_budget_micros)} -> {usd(new)}",
                             {"daily_budget_micros": c.daily_budget_micros}, {"daily_budget_micros": new}, undo)

        if kind == "add_negative_keywords":
            c = self._campaign(campaigns, change["campaign_id"])
            match = str(change.get("match_type", "PHRASE")).upper()
            words = [str(w).strip() for w in change.get("keywords", []) if str(w).strip()]
            if match not in MATCH_TYPES or not words:
                raise Refused("give at least one search to block and a match type (EXACT, PHRASE or BROAD)")
            kws = [{"text": w, "match_type": match} for w in words]
            return self._new(change, [{"op": "campaign_negatives", "campaign_id": c.id, "keywords": kws}],
                             f"block {len(kws)} search(es) on '{c.name}': {', '.join(words[:6])}",
                             {}, {"blocked": words}, {"kind": "remove_criteria"})

        if kind == "create_search_campaign":
            problems = check_ad(change.get("headlines", []), change.get("descriptions", []))
            if problems:
                raise Refused("the ad copy breaks the rules: " + "; ".join(problems))
            budget = round(float(change["daily_budget"]) * MICROS)
            cap = int(float(lim.get("max_new_campaign_daily_budget_usd") or 0) * MICROS)
            if cap <= 0:
                raise Refused("max_new_campaign_daily_budget_usd in settings/limits.json is 0, so no campaign can be "
                              "created. A person sets it by hand.")
            if budget <= 0 or budget > cap:
                raise Refused(f"a new campaign's daily budget must be between $0 and {usd(cap)} (asked: {usd(budget)})")
            if not str(change.get("final_url", "")).startswith("https://"):
                raise Refused("the landing page must be an https:// address")
            if not change.get("locations"):
                raise Refused("pick at least one location (a Google geo target id)")
            kws = self._keywords(change.get("keywords", []), "keywords")
            negs = self._keywords(change.get("negative_keywords", []), "blocked searches", required=False)
            op = {"op": "create_search_campaign", "name": change["name"], "daily_budget_micros": budget,
                  "final_url": change["final_url"], "locations": [str(x) for x in change["locations"]],
                  "keywords": kws, "negative_keywords": negs,
                  "headlines": change["headlines"], "descriptions": change["descriptions"]}
            return self._new(change, [op],
                             f"create campaign '{change['name']}' SWITCHED OFF, {usd(budget)} a day, "
                             f"{len(kws)} keywords, {len(negs)} blocked searches, 1 ad",
                             {}, {"status": "PAUSED", "daily_budget_micros": budget}, {"kind": "pause_created"})

        if kind == "add_responsive_search_ad":
            problems = check_ad(change.get("headlines", []), change.get("descriptions", []))
            if problems:
                raise Refused("the ad copy breaks the rules: " + "; ".join(problems))
            if not str(change.get("final_url", "")).startswith("https://"):
                raise Refused("the landing page must be an https:// address")
            op = {"op": "create_rsa", "ad_group_id": str(change["ad_group_id"]), "final_url": change["final_url"],
                  "headlines": change["headlines"], "descriptions": change["descriptions"]}
            return self._new(change, [op], f"add a new ad (switched off) to ad group {change['ad_group_id']}",
                             {}, {"status": "PAUSED"}, None)

        raise Refused(f"unknown change {kind!r}. Known: pause_campaign, enable_campaign, set_daily_budget, "
                      "add_negative_keywords, create_search_campaign, add_responsive_search_ad")

    @staticmethod
    def _keywords(items: list[Any], what: str, required: bool = True) -> list[dict[str, str]]:
        out = []
        for k in items:
            text = k.get("text") if isinstance(k, dict) else k
            match = (k.get("match_type") if isinstance(k, dict) else None) or "PHRASE"
            if not str(text or "").strip() or str(match).upper() not in MATCH_TYPES:
                raise Refused(f"every one of the {what} needs text and a match type (EXACT, PHRASE or BROAD)")
            out.append({"text": str(text).strip(), "match_type": str(match).upper()})
        if required and not out:
            raise Refused(f"add at least one of the {what}")
        return out

    def _new(self, change: dict[str, Any], ops: list[dict[str, Any]], summary: str, before: dict[str, Any],
             after: dict[str, Any], undo: dict[str, Any] | None) -> Preview:
        return Preview(secrets.token_hex(4), change, ops, summary, before, after, undo)

    def preview(self, change: dict[str, Any]) -> Preview:
        p = self.plan(change)
        try:
            self.gw.mutate(p.ops, validate_only=True)
        except Refused:
            raise
        except Exception as e:  # Google's own refusal, in Google's words
            raise Refused(f"Google's test run refused it: {_google_error(e)}") from None
        self.previews[p.id] = p
        return p

    # ----------------------------------------------------------------- apply
    def apply(self, preview_id: str) -> dict[str, Any]:
        p = self.previews.pop(preview_id, None)
        if p is None:
            raise Refused(f"no preview {preview_id!r} in this session (previews are kept in memory only). "
                          "Preview the change again.")
        if time.time() - p.created > PREVIEW_TTL_S:
            raise Refused("that preview is more than 30 minutes old; preview it again so the limits are re-checked")
        # Re-check against the account as it is NOW. Removing what an earlier change added (an undo)
        # spends nothing, so it has no limits to re-check.
        fresh = p if p.change.get("kind") == "remove_criteria" else self.plan(p.change)
        try:
            names = self.gw.mutate(fresh.ops, validate_only=False)
        except Exception as e:
            raise Refused(f"Google refused it: {_google_error(e)}") from None
        undo = fresh.undo
        if undo and undo.get("kind") == "remove_criteria":
            undo = {"kind": "remove_criteria", "resource_names": names}
        if undo and undo.get("kind") == "pause_created":
            created = [n for n in names if "/campaigns/" in n]
            undo = {"kind": "pause_campaign", "campaign_id": created[0].rsplit("/", 1)[-1]} if created else None
        entry = {"id": p.id, "at": now(), "kind": p.change["kind"], "change": p.change, "summary": fresh.summary,
                 "before": fresh.before, "after": fresh.after, "resources": names, "undo": undo}
        self._log(entry)
        return entry

    def pause(self, campaign_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Switch campaigns off at once (all live ones when none are named). Always allowed."""
        live = [c for c in self.gw.campaigns() if c.status == "ENABLED"]
        targets = [c for c in live if campaign_ids is None or c.id in {str(x) for x in campaign_ids}]
        if not targets:
            return []
        ops = [{"op": "campaign_status", "campaign_id": c.id, "status": "PAUSED"} for c in targets]
        self.gw.mutate(ops, validate_only=False)
        out = []
        for c in targets:
            entry = {"id": secrets.token_hex(4), "at": now(), "kind": "pause_campaign",
                     "change": {"kind": "pause_campaign", "campaign_id": c.id}, "summary": f"switch off '{c.name}'",
                     "before": {"status": "ENABLED"}, "after": {"status": "PAUSED"}, "resources": [],
                     "undo": {"kind": "enable_campaign", "campaign_id": c.id}}
            self._log(entry)
            out.append(entry)
        return out

    def undo_preview(self, change_id: str) -> Preview:
        """Preview the change that undoes a logged one. It still needs Allow, and the limits."""
        entry = next((e for e in self.history() if e["id"] == change_id), None)
        if entry is None:
            raise Refused(f"no logged change {change_id!r}")
        undo = entry.get("undo")
        if not undo:
            raise Refused(f"change {change_id} has no automatic undo; reverse it in Google Ads by hand")
        if undo["kind"] == "remove_criteria":
            p = Preview(secrets.token_hex(4), {"kind": "remove_criteria", "undoes": change_id},
                        [{"op": "remove_criteria", "resource_names": undo["resource_names"]}],
                        f"remove the {len(undo['resource_names'])} item(s) added by change {change_id}",
                        {"present": undo["resource_names"]}, {"present": []}, None)
            try:
                self.gw.mutate(p.ops, validate_only=True)
            except Exception as e:
                raise Refused(f"Google's test run refused it: {_google_error(e)}") from None
            self.previews[p.id] = p
            return p
        return self.preview(undo)


def _google_error(e: Exception) -> str:
    failure = getattr(e, "failure", None)
    if failure is not None:
        try:
            return "; ".join(err.message for err in failure.errors)[:500]
        except Exception:
            pass
    return f"{type(e).__name__}: {str(e)[:400]}"
