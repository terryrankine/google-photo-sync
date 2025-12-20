"""
Google Photos OAuth Authentication

Run this script to authenticate with Google Photos.
It will open a browser, you log in and click Allow,
then it saves the token for future use.

Usage:
    python auth.py
"""

import json
import webbrowser
import http.server
import urllib.parse
from pathlib import Path
import requests

CONFIG_DIR = Path(__file__).parent / "config"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.appendonly",
]

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}"


def load_credentials():
    """Load OAuth credentials from file."""
    with open(CREDENTIALS_FILE) as f:
        creds = json.load(f)
    return creds["installed"]


def get_auth_url(client_id: str) -> str:
    """Build the OAuth authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    base = "https://accounts.google.com/o/oauth2/v2/auth"
    return f"{base}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(code: str, client_id: str, client_secret: str) -> dict:
    """Exchange authorization code for access token."""
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
    )
    response.raise_for_status()
    return response.json()


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    """Handle OAuth callback."""

    auth_code = None

    def do_GET(self):
        """Handle the OAuth redirect."""
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "code" in params:
            OAuthHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body style="font-family: system-ui; text-align: center; padding: 50px;">
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """)
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            error = params.get("error", ["Unknown error"])[0]
            self.wfile.write(f"<h1>Error: {error}</h1>".encode())

    def log_message(self, format, *args):
        """Suppress HTTP logs."""
        pass


def main():
    print("=" * 60)
    print("Google Photos Authentication")
    print("=" * 60)

    # Load credentials
    if not CREDENTIALS_FILE.exists():
        print(f"\nError: {CREDENTIALS_FILE} not found")
        print("Please download credentials from Google Cloud Console")
        return 1

    creds = load_credentials()
    client_id = creds["client_id"]
    client_secret = creds["client_secret"]

    print(f"\nProject: {creds['project_id']}")
    print(f"Client ID: {client_id[:20]}...")

    # Build auth URL and open browser
    auth_url = get_auth_url(client_id)
    print(f"\nOpening browser for authentication...")
    print(f"If browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Start local server to catch callback
    print(f"Waiting for authorization (listening on port {REDIRECT_PORT})...")
    server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), OAuthHandler)
    server.handle_request()

    if not OAuthHandler.auth_code:
        print("\nError: No authorization code received")
        return 1

    print("\nGot authorization code, exchanging for token...")

    # Exchange code for token
    try:
        token_data = exchange_code_for_token(
            OAuthHandler.auth_code, client_id, client_secret
        )
    except requests.exceptions.HTTPError as e:
        print(f"\nError getting token: {e}")
        print(e.response.text)
        return 1

    # Save token
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nToken saved to: {TOKEN_FILE}")
    print("\n" + "=" * 60)
    print("Authentication successful!")
    print("=" * 60)
    print(f"\nAccess token: {token_data['access_token'][:20]}...")
    print(f"Expires in: {token_data.get('expires_in', 'N/A')} seconds")
    print(f"Refresh token: {'Yes' if 'refresh_token' in token_data else 'No'}")

    return 0


if __name__ == "__main__":
    exit(main())
