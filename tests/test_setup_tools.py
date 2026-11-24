"""The setup checker and the sign-in file writer: plain answers, and no secret ever printed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools import doctor, google_signin

ROOT = Path(__file__).resolve().parents[1]


def repo_copy(tmp_path: Path) -> Path:
    for d in ("settings", "google-scripts"):
        shutil.copytree(ROOT / d, tmp_path / d)
    return tmp_path


def by_name(results):
    return {c.name: c for c in results}


def test_a_fresh_repo_lists_what_is_missing(tmp_path):
    r = by_name(doctor.checks(repo_copy(tmp_path), env={}))
    assert not r["Google Ads account number"].ok
    assert not r["Spending limits"].ok and "nothing can spend" in r["Spending limits"].detail
    assert "google_signin.py" in r["Apply connector sign-in"].detail
    assert not r["Read connector sign-in"].ok and not r["Google Cloud project"].ok


def test_a_filled_in_repo_is_ready_and_never_prints_a_secret(tmp_path):
    root = repo_copy(tmp_path)
    (root / "settings" / "account.json").write_text(json.dumps({"customer_id": "123-456-7890"}))
    (root / "settings" / "limits.json").write_text(json.dumps(
        {"daily_cap_usd": 30, "monthly_cap_usd": 900, "max_new_campaign_daily_budget_usd": 20}))
    (root / "secrets").mkdir()
    (root / "secrets" / "google-ads.yaml").write_text(google_signin.yaml_text(
        "DEVTOKEN-SECRET", "cid.apps.googleusercontent.com", "CLIENT-SECRET", "REFRESH-SECRET", "9998887777"))
    adc = root / "adc.json"
    adc.write_text("{}")
    results = doctor.checks(root, env={"GOOGLE_APPLICATION_CREDENTIALS": str(adc), "GOOGLE_CLOUD_PROJECT": "cl-ads"})
    r = by_name(results)
    assert r["Google Ads account number"].detail == "customer 123-456-7890"
    assert all(c.ok for c in results if c.required and c.name not in ("claude installed", "uv installed",
                                                                         "pipx installed", "gcloud installed"))
    printed = " ".join(c.detail for c in results)
    for secret in ("DEVTOKEN-SECRET", "CLIENT-SECRET", "REFRESH-SECRET"):
        assert secret not in printed


def test_the_sign_in_file_is_googles_format():
    text = google_signin.yaml_text("tok", "id", "sec", "ref", "")
    assert "use_proto_plus: True" in text and "login_customer_id" not in text
    assert doctor.yaml_keys.__doc__ and {"developer_token", "client_id", "client_secret", "refresh_token"} <= {
        line.split(":")[0] for line in text.splitlines() if ":" in line and not line.startswith("#")}
