"""The Apply connector's promises, against a fake Google account: limits hold, copy rules hold,
previews are the only way in, every change is logged with an undo, and pausing always works."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from apply.core import Applier, Refused
from apply.gateway import MICROS, CampaignState

GOOD_AD = {
    "headlines": ["A Receptionist For HVAC Calls", "After-Hours Calls Answered", "Book Appointments By Phone"],
    "descriptions": ["Our AI receptionist answers, qualifies and books appointments.",
                     "Try it free. Set up in a day."],
}


class FakeGoogle:
    def __init__(self, campaigns: list[CampaignState], mtd_usd: float = 0, refuse: str = "") -> None:
        self.customer_id = "1234567890"
        self.state = {c.id: c for c in campaigns}
        self.mtd = int(mtd_usd * MICROS)
        self.refuse = refuse
        self.calls: list[tuple[list[dict[str, Any]], bool]] = []

    def campaigns(self) -> list[CampaignState]:
        return [CampaignState(**vars(c)) for c in self.state.values()]

    def month_to_date_cost_micros(self) -> int:
        return self.mtd

    def mutate(self, ops: list[dict[str, Any]], validate_only: bool) -> list[str]:
        self.calls.append((ops, validate_only))
        if self.refuse:
            raise RuntimeError(self.refuse)
        names = []
        for op in ops:
            if validate_only:
                continue
            if op["op"] == "campaign_status":
                self.state[op["campaign_id"]].status = op["status"]
            elif op["op"] == "budget_amount":
                c = next(c for c in self.state.values() if c.budget_resource == op["budget_resource"])
                c.daily_budget_micros = op["amount_micros"]
            elif op["op"] == "campaign_negatives":
                names += [f"customers/1/campaignCriteria/{op['campaign_id']}~{i}" for i in range(len(op["keywords"]))]
            elif op["op"] == "create_search_campaign":
                names += ["customers/1/campaignBudgets/77", "customers/1/campaigns/900"]
        return names


def camp(cid: str, status: str = "ENABLED", usd: float = 20, shared: bool = False) -> CampaignState:
    return CampaignState(cid, f"Campaign {cid}", status, f"customers/1/campaignBudgets/{cid}",
                         int(usd * MICROS), shared)


@pytest.fixture
def lim(tmp_path: Path) -> Path:
    p = tmp_path / "limits.json"
    p.write_text(json.dumps({"daily_cap_usd": 50, "monthly_cap_usd": 1500, "max_new_campaign_daily_budget_usd": 30,
                             "max_budget_increase_pct_per_week": 20, "min_days_between_increases": 7}))
    return p


def make(tmp_path: Path, lim: Path, *campaigns: CampaignState, **kw: Any) -> tuple[Applier, FakeGoogle]:
    g = FakeGoogle(list(campaigns), **kw)
    return Applier(g, limits_file=lim, log_dir=tmp_path / "log"), g


def test_a_preview_only_test_runs_and_apply_makes_it_and_logs_an_undo(tmp_path, lim):
    a, g = make(tmp_path, lim, camp("1", "PAUSED"))
    p = a.preview({"kind": "enable_campaign", "campaign_id": "1"})
    assert g.calls == [([{"op": "campaign_status", "campaign_id": "1", "status": "ENABLED"}], True)]
    assert g.state["1"].status == "PAUSED", "a preview changes nothing"
    done = a.apply(p.id)
    assert g.state["1"].status == "ENABLED" and g.calls[-1][1] is False
    assert done["undo"] == {"kind": "pause_campaign", "campaign_id": "1"}
    assert a.history()[-1]["before"] == {"status": "PAUSED"}


def test_only_a_preview_from_this_session_can_be_applied_and_only_once(tmp_path, lim):
    a, _ = make(tmp_path, lim, camp("1", "PAUSED"))
    with pytest.raises(Refused, match="no preview"):
        a.apply("deadbeef")
    p = a.preview({"kind": "enable_campaign", "campaign_id": "1"})
    a.apply(p.id)
    with pytest.raises(Refused, match="no preview"):
        a.apply(p.id)


def test_nothing_that_spends_is_allowed_until_a_person_sets_the_limits(tmp_path):
    zero = tmp_path / "limits.json"
    zero.write_text(json.dumps({"daily_cap_usd": 0, "monthly_cap_usd": 0, "max_new_campaign_daily_budget_usd": 0}))
    a, _ = make(tmp_path, zero, camp("1", "PAUSED"))
    with pytest.raises(Refused, match="not filled in"):
        a.preview({"kind": "enable_campaign", "campaign_id": "1"})
    with pytest.raises(Refused, match="max_new_campaign_daily_budget_usd"):
        a.preview({"kind": "create_search_campaign", "name": "x", "daily_budget": 5, **GOOD_AD})


def test_switching_on_past_the_daily_or_monthly_limit_is_refused(tmp_path, lim):
    a, _ = make(tmp_path, lim, camp("1", "ENABLED", 40), camp("2", "PAUSED", 20))
    with pytest.raises(Refused, match="over the daily limit"):
        a.preview({"kind": "enable_campaign", "campaign_id": "2"})
    b, _ = make(tmp_path, lim, camp("3", "PAUSED", 20), mtd_usd=1500)
    with pytest.raises(Refused, match="already spent"):
        b.preview({"kind": "enable_campaign", "campaign_id": "3"})


def test_budget_raises_are_capped_per_week_and_spaced_out(tmp_path, lim):
    a, _ = make(tmp_path, lim, camp("1", "ENABLED", 20))
    with pytest.raises(Refused, match="more than the 20% a week"):
        a.preview({"kind": "set_daily_budget", "campaign_id": "1", "daily_budget": 30})
    a.apply(a.preview({"kind": "set_daily_budget", "campaign_id": "1", "daily_budget": 24}).id)
    with pytest.raises(Refused, match="days between increases"):
        a.preview({"kind": "set_daily_budget", "campaign_id": "1", "daily_budget": 26})
    assert a.preview({"kind": "set_daily_budget", "campaign_id": "1", "daily_budget": 10}), "lowering is always fine"


def test_a_raise_a_week_after_the_last_one_is_allowed(tmp_path, lim):
    a, _ = make(tmp_path, lim, camp("1", "ENABLED", 20))
    old = (datetime.now(UTC) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (tmp_path / "log").mkdir()
    (tmp_path / "log" / "changes.jsonl").write_text(json.dumps({
        "id": "x", "at": old, "kind": "set_daily_budget", "change": {"campaign_id": "1"},
        "before": {"daily_budget_micros": 17 * MICROS}, "after": {"daily_budget_micros": 20 * MICROS}}) + "\n")
    assert a.preview({"kind": "set_daily_budget", "campaign_id": "1", "daily_budget": 24})


def test_limits_are_checked_again_at_apply_time(tmp_path, lim):
    a, g = make(tmp_path, lim, camp("1", "PAUSED", 20))
    p = a.preview({"kind": "enable_campaign", "campaign_id": "1"})
    g.mtd = 2000 * MICROS                     # the month's spend moved on after the preview
    with pytest.raises(Refused, match="already spent"):
        a.apply(p.id)
    assert g.state["1"].status == "PAUSED"


def test_ad_copy_that_breaks_our_rules_never_reaches_google(tmp_path, lim):
    a, g = make(tmp_path, lim)
    bad = {"kind": "create_search_campaign", "name": "TX", "daily_budget": 20, "final_url": "https://caughtleads.com",
           "locations": ["21176"], "keywords": [{"text": "hvac answering service", "match_type": "PHRASE"}],
           "headlines": ["Answers Every Call 24/7", "Book More Jobs Today", "Double Your Revenue Now"],
           "descriptions": ["TCPA-compliant texting for contractors.", "Try it free."]}
    with pytest.raises(Refused) as e:
        a.preview(bad)
    for rule in ("answers-every-call", "job-not-appointment", "revenue-promise", "tcpa"):
        assert rule in str(e.value)
    assert g.calls == [], "refused before Google was even asked"


def test_a_new_campaign_is_created_switched_off_and_its_undo_is_a_pause(tmp_path, lim):
    a, _g = make(tmp_path, lim)
    p = a.preview({"kind": "create_search_campaign", "name": "HVAC owners, Texas", "daily_budget": 20,
                   "final_url": "https://caughtleads.com/hvac", "locations": ["21176"],
                   "keywords": [{"text": "hvac answering service", "match_type": "PHRASE"}],
                   "negative_keywords": ["jobs", {"text": "salary", "match_type": "BROAD"}], **GOOD_AD})
    assert "SWITCHED OFF" in p.summary and p.after["status"] == "PAUSED"
    done = a.apply(p.id)
    assert done["undo"] == {"kind": "pause_campaign", "campaign_id": "900"}


def test_googles_own_refusal_is_reported_in_its_words(tmp_path, lim):
    a, _ = make(tmp_path, lim, camp("1", "PAUSED"), refuse="RESOURCE_NOT_FOUND")
    with pytest.raises(Refused, match="Google's test run refused it: RuntimeError: RESOURCE_NOT_FOUND"):
        a.preview({"kind": "enable_campaign", "campaign_id": "1"})


def test_pause_everything_always_works_and_is_logged(tmp_path, tmp_path_factory):
    zero = tmp_path / "limits.json"
    zero.write_text(json.dumps({"daily_cap_usd": 0, "monthly_cap_usd": 0}))
    a, g = make(tmp_path, zero, camp("1"), camp("2"), camp("3", "PAUSED"))
    done = a.pause()
    assert {e["change"]["campaign_id"] for e in done} == {"1", "2"} and g.state["1"].status == "PAUSED"
    assert len(a.history()) == 2


def test_blocked_searches_can_be_undone_exactly(tmp_path, lim):
    a, g = make(tmp_path, lim, camp("1"))
    done = a.apply(a.preview({"kind": "add_negative_keywords", "campaign_id": "1",
                              "keywords": ["jobs", "salary"], "match_type": "PHRASE"}).id)
    assert done["undo"]["kind"] == "remove_criteria" and len(done["undo"]["resource_names"]) == 2
    u = a.undo_preview(done["id"])
    a.apply(u.id)
    assert g.calls[-1] == ([{"op": "remove_criteria", "resource_names": done["undo"]["resource_names"]}], False)


def test_shared_budgets_are_left_to_a_person(tmp_path, lim):
    a, _ = make(tmp_path, lim, camp("1", shared=True))
    with pytest.raises(Refused, match="shared budget"):
        a.preview({"kind": "set_daily_budget", "campaign_id": "1", "daily_budget": 10})
