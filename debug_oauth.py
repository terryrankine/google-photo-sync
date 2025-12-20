"""
Debug Google OAuth flow using Playwright - Automatic version
"""

import asyncio
import json
import urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright

CONFIG_DIR = Path(__file__).parent / "config"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary",
]

def load_credentials():
    with open(CREDENTIALS_FILE) as f:
        creds = json.load(f)
    return creds["installed"]

def get_auth_url(client_id: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": "http://127.0.0.1:8766",
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    base = "https://accounts.google.com/o/oauth2/v2/auth"
    return f"{base}?{urllib.parse.urlencode(params)}"


async def main():
    print("=" * 60)
    print("OAuth Debug with Playwright (Automatic)")
    print("=" * 60)

    creds = load_credentials()
    auth_url = get_auth_url(creds["client_id"])

    print(f"\nClient ID: {creds['client_id'][:30]}...")
    print(f"Project: {creds['project_id']}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("\nNavigating to OAuth URL...")
        await page.goto(auth_url)

        print("\n--- Browser opened ---")
        print("Complete the login flow manually.")
        print("I'll monitor for errors and success...")
        print("-" * 40)

        last_url = ""
        check_count = 0
        max_checks = 120  # 2 minutes

        while check_count < max_checks:
            await asyncio.sleep(1)
            check_count += 1

            try:
                url = page.url

                # Only report if URL changed
                if url != last_url:
                    last_url = url
                    title = await page.title()
                    print(f"\n[{check_count}s] URL changed:")
                    print(f"  URL: {url[:100]}...")
                    print(f"  Title: {title}")

                    # Check for callback
                    if "127.0.0.1:8766" in url or "localhost:8766" in url:
                        print("\n*** SUCCESS - Redirected to callback! ***")
                        parsed = urllib.parse.urlparse(url)
                        params = urllib.parse.parse_qs(parsed.query)
                        if "code" in params:
                            print(f"Authorization code received!")
                            print(f"Code: {params['code'][0][:30]}...")
                        if "error" in params:
                            print(f"ERROR: {params['error']}")
                        break

                    # Check for error in URL
                    if "unknownerror" in url.lower() or "error" in url.lower():
                        print("\n*** ERROR URL detected ***")
                        body = await page.inner_text("body")
                        print(f"Page content:\n{body[:1500]}")

                        # Screenshot
                        ss_path = CONFIG_DIR / "oauth_error.png"
                        await page.screenshot(path=str(ss_path))
                        print(f"\nScreenshot: {ss_path}")

                # Check page content for error
                try:
                    body = await page.inner_text("body")
                    if "Something went wrong" in body and check_count % 5 == 0:
                        print(f"\n[{check_count}s] 'Something went wrong' detected on page")

                        # Get more details
                        ss_path = CONFIG_DIR / f"oauth_error_{check_count}.png"
                        await page.screenshot(path=str(ss_path))
                        print(f"Screenshot: {ss_path}")

                        # Try to get any error details
                        print("\nPage text snippet:")
                        print("-" * 40)
                        print(body[:1000])
                        print("-" * 40)
                except:
                    pass

            except Exception as e:
                if "Target closed" in str(e) or "closed" in str(e).lower():
                    print("\nBrowser was closed.")
                    break
                print(f"[{check_count}s] Check error: {e}")

        print("\nDone monitoring. Closing browser...")
        try:
            await browser.close()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())
