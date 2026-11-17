"""Obtain a Tumblr OAuth2 access token for the posting API.

Tumblr does not hand out postable tokens in its UI; one browser round-trip is
required. This script runs the authorization-code flow for you.

Setup (once):
    1. Create an app at https://www.tumblr.com/oauth/apps
    2. Set its "Default callback URL" to:  http://localhost:8765/callback
    3. Copy the OAuth Consumer Key and Secret Key into .env:

           TUMBLR_CLIENT_ID=...
           TUMBLR_CLIENT_SECRET=...
           TUMBLR_REDIRECT_URI=http://localhost:8765/callback

Run:
    python scripts/tumblr_auth.py

The browser opens, you approve the app, and the script prints the
TUMBLR_ACCESS_TOKEN line to paste into .env. Nothing is written automatically,
so secrets never land in a tracked file.
"""

from __future__ import annotations

import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

sys.path.insert(0, ".")

from app.config import Settings  # noqa: E402

AUTHORIZE_URL = "https://www.tumblr.com/oauth2/authorize"
TOKEN_URL = "https://api.tumblr.com/v2/oauth2/token"
SCOPES = "basic write offline_access"


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None
    expected_state: str = ""

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_error(404)
            return

        params = urllib.parse.parse_qs(parsed.query)
        state = (params.get("state") or [""])[0]
        code = (params.get("code") or [""])[0]
        error = (params.get("error") or [""])[0]

        if error:
            type(self).error = f"Tumblr returned an error: {error}"
        elif state != type(self).expected_state:
            type(self).error = "State mismatch: the callback did not come from this run."
        elif not code:
            type(self).error = "Tumblr did not return an authorization code."
        else:
            type(self).code = code

        body = b"<h2>posting-api: authorization received</h2><p>You can close this tab.</p>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Silence the default per-request logging."""


def main() -> int:
    settings = Settings()
    client_id = settings.tumblr_client_id
    client_secret = settings.tumblr_client_secret
    redirect_uri = settings.tumblr_redirect_uri

    if not client_id or not client_secret:
        print("Set TUMBLR_CLIENT_ID and TUMBLR_CLIENT_SECRET in .env first.")
        return 1

    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname not in {"localhost", "127.0.0.1"} or not parsed.port:
        print("TUMBLR_REDIRECT_URI must be a local address such as http://localhost:8765/callback")
        return 1

    state = secrets.token_urlsafe(16)
    _CallbackHandler.expected_state = state

    authorize = (
        AUTHORIZE_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "scope": SCOPES,
                "state": state,
                "redirect_uri": redirect_uri,
            }
        )
    )

    print("Opening the Tumblr authorization page. If it does not open, visit:\n")
    print(authorize)
    print()
    webbrowser.open(authorize)

    server = HTTPServer((parsed.hostname, parsed.port), _CallbackHandler)
    server.timeout = 300
    print(f"Waiting for the callback on {redirect_uri} (5 minute timeout)...")
    server.handle_request()
    server.server_close()

    if _CallbackHandler.error:
        print(f"\n{_CallbackHandler.error}")
        return 1
    if not _CallbackHandler.code:
        print("\nNo callback received. Re-run the script and approve the app.")
        return 1

    print("\nExchanging the code for a token...")
    with httpx.Client(timeout=30) as client:
        response = client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": _CallbackHandler.code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
        )

    if response.status_code != 200:
        print(f"Token exchange failed: HTTP {response.status_code} {response.text[:300]}")
        return 1

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        print(f"No access_token in the response: {payload}")
        return 1

    print("\nSuccess. Add these lines to .env:\n")
    print(f"TUMBLR_ACCESS_TOKEN={access_token}")
    print("TUMBLR_BLOG_IDENTIFIER=<your-blog>.tumblr.com")
    print()
    if payload.get("refresh_token"):
        print("A refresh token was also issued (not needed by the API, tokens are long-lived).")
    print("\nThis terminal output now contains a secret: do not paste it into chat or commit it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
