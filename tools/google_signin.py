"""One-time Google sign-in for the Apply connector. Run it yourself in a terminal (not through Claude):

    uv run python tools/google_signin.py --client-secrets path/to/oauth-client.json

It opens Google's sign-in page in your browser (sign in with the account that has access to the
Google Ads account), asks for the developer token (typed, not shown), and writes
secrets/google-ads.yaml in Google's standard format. Nothing is printed except where it was saved.

Needs: an OAuth client of type "Desktop app" from your Google Cloud project (APIs & Services >
Credentials), downloaded as JSON; and the developer token from Google Ads > Tools > API Center.
"""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "secrets" / "google-ads.yaml"
SCOPE = "https://www.googleapis.com/auth/adwords"


def yaml_text(developer_token: str, client_id: str, client_secret: str, refresh_token: str,
              login_customer_id: str) -> str:
    lines = [
        "# Written by tools/google_signin.py. Secret: git-ignored and blocked from every agent.",
        f"developer_token: {json.dumps(developer_token)}",
        f"client_id: {json.dumps(client_id)}",
        f"client_secret: {json.dumps(client_secret)}",
        f"refresh_token: {json.dumps(refresh_token)}",
        "use_proto_plus: True",
    ]
    if login_customer_id:
        lines.append(f"login_customer_id: {json.dumps(login_customer_id)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--client-secrets", required=True, type=Path, help="the Desktop-app OAuth client JSON")
    ap.add_argument("--login-customer-id", default="", help="manager (MCC) account id, digits only, if any")
    args = ap.parse_args()

    from google_auth_oauthlib.flow import InstalledAppFlow

    client = json.loads(args.client_secrets.read_text(encoding="utf-8"))
    info = client.get("installed") or client.get("web") or {}
    if not info.get("client_id"):
        print("That file is not an OAuth client JSON (no client_id). Download it from Google Cloud > "
              "APIs & Services > Credentials > your Desktop app client.")
        return 2
    flow = InstalledAppFlow.from_client_secrets_file(str(args.client_secrets), scopes=[SCOPE])
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    if not creds.refresh_token:
        print("Google did not return a refresh token. Remove this app's access at "
              "https://myaccount.google.com/permissions and run this again.")
        return 3
    token = getpass.getpass("Google Ads developer token (not shown): ").strip()
    if not token:
        print("No developer token given; nothing was written.")
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(yaml_text(token, info["client_id"], info["client_secret"], creds.refresh_token,
                             args.login_customer_id.replace("-", "")), encoding="utf-8")
    print(f"Saved {OUT.relative_to(ROOT)}. Next: uv run python tools/doctor.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
