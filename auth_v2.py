"""
Google Photos OAuth Authentication (using official library)

Run this script to authenticate with Google Photos.
It will open a browser, you log in and click Allow,
then it saves the token for future use.

Usage:
    python auth_v2.py
"""

import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

CONFIG_DIR = Path(__file__).parent / "config"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"

# Full library access (easier to configure for testing)
SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary",
]


def main():
    print("=" * 60)
    print("Google Photos Authentication (v2)")
    print("=" * 60)

    if not CREDENTIALS_FILE.exists():
        print(f"\nError: {CREDENTIALS_FILE} not found")
        print("Please download credentials from Google Cloud Console")
        return 1

    creds = None

    # Check for existing token
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            print("\nFound existing token")
        except Exception as e:
            print(f"\nExisting token invalid: {e}")

    # If no valid creds, do the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("\nRefreshing expired token...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Refresh failed: {e}")
                creds = None

        if not creds:
            print("\nStarting OAuth flow...")
            print("A browser window will open. Sign in and click 'Allow'.\n")

            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE),
                    SCOPES
                )
                # This handles everything - opens browser, runs local server, etc.
                creds = flow.run_local_server(
                    port=8766,
                    prompt="consent",
                    access_type="offline"
                )
            except Exception as e:
                print(f"\nOAuth error: {e}")
                print("\nTroubleshooting:")
                print("1. Make sure Photos Library API is enabled")
                print("2. Add test user email to OAuth consent screen")
                print("3. Check redirect URIs include http://localhost:8765")
                return 1

    # Save the token
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"\nToken saved to: {TOKEN_FILE}")
    print("\n" + "=" * 60)
    print("Authentication successful!")
    print("=" * 60)
    print(f"\nToken valid: {creds.valid}")
    print(f"Has refresh token: {creds.refresh_token is not None}")

    return 0


if __name__ == "__main__":
    exit(main())
