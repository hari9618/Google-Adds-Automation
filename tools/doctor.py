"""Setup checker: what is ready and what is missing, in plain words. Never prints a secret.

    uv run python tools/doctor.py          check the files, settings and tools
    uv run python tools/doctor.py --live   also READ the Google Ads account once (campaigns and
                                           this month's spend), to prove the sign-in works

Exit code 0 when everything needed to run is ready, 1 otherwise.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YAML_KEYS = ("developer_token", "client_id", "client_secret", "refresh_token")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def yaml_keys(path: Path) -> set[str]:
    """Which keys the sign-in file has a value for (values are never returned)."""
    found = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.lstrip().startswith("#") and value.strip().strip("\"'"):
            found.add(key.strip())
    return found


def checks(root: Path = ROOT, env: dict[str, str] | None = None) -> list[Check]:
    env = dict(os.environ) if env is None else env
    out: list[Check] = []
    for tool, why in (("claude", "Claude Code is the chat"), ("uv", "uv runs the Apply connector and the hooks"),
                      ("pipx", "pipx runs Google's read connector"), ("gcloud", "gcloud signs the read connector in")):
        out.append(Check(f"{tool} installed", shutil.which(tool) is not None,
                         f"not found: {why}" if shutil.which(tool) is None else "found"))

    acct = _json(root / "settings" / "account.json")
    cid = str(acct.get("customer_id", "")).replace("-", "")
    out.append(Check("Google Ads account number", cid.isdigit() and len(cid) == 10,
                     f"customer {cid[:3]}-{cid[3:6]}-{cid[6:]}" if cid.isdigit() and len(cid) == 10
                     else "put the 10-digit customer id in settings/account.json"))

    lim = _json(root / "settings" / "limits.json")
    names = ("daily_cap_usd", "monthly_cap_usd", "max_new_campaign_daily_budget_usd")
    caps = {k: float(lim.get(k) or 0) for k in names}
    unset = [k for k, v in caps.items() if v <= 0]
    out.append(Check("Spending limits", not unset,
                     "daily ${daily_cap_usd:g}, monthly ${monthly_cap_usd:g}, new campaign up to "
                     "${max_new_campaign_daily_budget_usd:g}/day".format(**caps) if not unset
                     else "still 0 in settings/limits.json: " + ", ".join(unset) + " (nothing can spend until set)"))
    if not unset and caps["daily_cap_usd"] * 30.4 > caps["monthly_cap_usd"]:
        out.append(Check("Limits agree", True, f"note: ${caps['daily_cap_usd']:g}/day can reach "
                         f"${caps['daily_cap_usd'] * 30.4:,.0f} a month; the monthly cap will stop it first",
                         required=False))

    keys = yaml_keys(root / "secrets" / "google-ads.yaml")
    missing = [k for k in YAML_KEYS if k not in keys]
    out.append(Check("Apply connector sign-in", not missing,
                     "secrets/google-ads.yaml has every key" if not missing
                     else ("run: uv run python tools/google_signin.py --client-secrets <oauth-client.json>"
                           if not keys else "secrets/google-ads.yaml is missing " + ", ".join(missing))))

    adc = env.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    out.append(Check("Read connector sign-in", bool(adc) and Path(adc).is_file(),
                     "GOOGLE_APPLICATION_CREDENTIALS points at a file" if adc and Path(adc).is_file()
                     else "run the gcloud sign-in from README step 4 and set GOOGLE_APPLICATION_CREDENTIALS"))
    out.append(Check("Google Cloud project", bool(env.get("GOOGLE_CLOUD_PROJECT")),
                     env.get("GOOGLE_CLOUD_PROJECT") or "set GOOGLE_CLOUD_PROJECT to your project id"))

    script = (root / "google-scripts" / "emergency-pause.js").read_text(encoding="utf-8")
    out.append(Check("Emergency pause e-mail set", "you@example.com" not in script,
                     "set CONFIG.EMAILS in google-scripts/emergency-pause.js, then paste it into Google Ads "
                     "> Tools > Scripts and schedule it hourly (this checker cannot see Google's side)"
                     if "you@example.com" in script else "CONFIG.EMAILS is set; make sure it runs hourly in Google",
                     required=False))
    return out


def live(root: Path = ROOT) -> Check:
    sys.path.insert(0, str(root))
    try:
        from apply.gateway import MICROS, GoogleGateway

        acct = _json(root / "settings" / "account.json")
        gw = GoogleGateway(str(acct.get("customer_id", "")).replace("-", ""),
                           str(acct.get("login_customer_id", "")).replace("-", ""))
        campaigns = gw.campaigns()
        mtd = gw.month_to_date_cost_micros() / MICROS
        live_n = sum(c.status == "ENABLED" for c in campaigns)
        return Check("Reading the account", True,
                     f"{len(campaigns)} campaign(s), {live_n} live; ${mtd:,.2f} spent this month")
    except Exception as e:
        failure = getattr(e, "failure", None)
        msg = "; ".join(x.message for x in failure.errors) if failure else f"{type(e).__name__}: {str(e)[:200]}"
        return Check("Reading the account", False, msg)


def main(argv: list[str]) -> int:
    results = checks()
    if "--live" in argv:
        results.append(live())
    for c in results:
        mark = "OK  " if c.ok else ("TODO" if c.required else "note")
        print(f"[{mark}] {c.name}: {c.detail}")
    todo = [c for c in results if c.required and not c.ok]
    print("\nReady." if not todo else f"\n{len(todo)} thing(s) to do before the first campaign.")
    return 0 if not todo else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
