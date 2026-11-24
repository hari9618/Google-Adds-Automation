"""The inbox format and the copy rules on their own."""

from __future__ import annotations

import json

from apply.copy_rules import check_ad
from tools import inbox

GOOD_H = ["A Receptionist For HVAC Calls", "After-Hours Calls Answered", "Book Appointments By Phone"]
GOOD_D = ["Our AI receptionist answers, qualifies and books appointments.", "Try it free. Set up in a day."]


def test_good_copy_passes():
    assert check_ad(GOOD_H, GOOD_D) == []


def test_googles_limits_are_checked_before_google_is_asked():
    problems = check_ad(["Way Too Long A Headline For Google Ads"] * 2, ["d"])
    text = " ".join(problems)
    assert "2 headlines" in text and "1 descriptions" in text and "limit is 30" in text and "repeated" in text


def test_shouting_and_exclamation_marks_are_refused_but_trade_acronyms_are_fine():
    assert any("capitals" in p for p in check_ad(["FREE TRIAL TODAY", *GOOD_H[1:]], GOOD_D))
    assert any("'!'" in p for p in check_ad(["Try It Free!", *GOOD_H[1:]], GOOD_D))
    assert check_ad(["HVAC Answering Service", *GOOD_H[1:]], GOOD_D) == []


def test_negative_keywords_may_say_jobs_but_ads_may_not():
    assert any("job-not-appointment" in p for p in check_ad(["Book More HVAC Jobs", *GOOD_H[1:]], GOOD_D))


def test_inbox_lists_only_waiting_items_oldest_first(tmp_path):
    items = tmp_path / "items"
    items.mkdir()
    rows = [("2026-11-25", "waiting"), ("2026-11-24", "waiting"), ("2026-11-23", "done")]
    for i, (created, status) in enumerate(rows):
        (items / f"{i:04d}.json").write_text(json.dumps({
            "id": f"{i:04d}", "created": created, "by": "optimizer", "status": status, "title": f"t{i}", "why": "w",
            "change": {"kind": "pause_campaign", "campaign_id": "1"}}))
    assert [i["id"] for i in inbox.waiting(items)] == ["0001", "0000"]
    assert all(inbox.problems(i) == [] for i in inbox.load(items))


def test_a_malformed_suggestion_is_caught():
    assert inbox.problems({"id": "1", "status": "maybe", "change": {"kind": "delete_account"}})
