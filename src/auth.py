"""
Google OAuth2 Token Management

Shared module for handling OAuth2 tokens for Google Photos API.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import aiohttp
import aiofiles

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages OAuth2 tokens with automatic refresh."""

    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

    def __init__(self, credentials_path: Path, token_path: Path):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self._client_id: Optional[str] = None
        self._client_secret: Optional[str] = None

    async def load_credentials(self):
        """Load OAuth client credentials."""
        if not self.credentials_path.exists():
            raise FileNotFoundError(f"Credentials not found: {self.credentials_path}")

        async with aiofiles.open(self.credentials_path, 'r') as f:
            creds = json.loads(await f.read())

        client_creds = creds.get('installed', creds.get('web', {}))
        self._client_id = client_creds.get('client_id')
        self._client_secret = client_creds.get('client_secret')

        if not self._client_id or not self._client_secret:
            raise ValueError("Invalid credentials file - missing client_id or client_secret")

    async def load_token(self):
        """Load existing token from file."""
        if not self.token_path.exists():
            raise FileNotFoundError(f"Token not found: {self.token_path} - run auth.py first")

        async with aiofiles.open(self.token_path, 'r') as f:
            token_data = json.loads(await f.read())

        self._access_token = token_data.get('access_token')
        self._refresh_token = token_data.get('refresh_token')

        expires_at = token_data.get('expires_at')
        if expires_at:
            self._expires_at = datetime.fromisoformat(expires_at)
        else:
            # No expiry info, assume expired
            self._expires_at = datetime.now() - timedelta(hours=1)

    def is_expired(self) -> bool:
        """Check if access token is expired or about to expire."""
        if not self._expires_at:
            return True
        # Consider expired if less than 5 minutes remaining
        return datetime.now() >= (self._expires_at - timedelta(minutes=5))

    async def get_valid_token(self, session: aiohttp.ClientSession) -> str:
        """Get a valid access token, refreshing if needed."""
        if not self._access_token:
            await self.load_token()

        if self.is_expired():
            await self.refresh(session)

        return self._access_token

    async def refresh(self, session: aiohttp.ClientSession):
        """Refresh the access token using refresh_token."""
        if not self._refresh_token:
            raise ValueError("No refresh token available - re-run auth.py")

        if not self._client_id:
            await self.load_credentials()

        logger.info("Refreshing OAuth access token...")

        async with session.post(
            self.TOKEN_ENDPOINT,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            }
        ) as response:
            if response.status != 200:
                body = await response.text()
                logger.error(f"Token refresh failed: {body}")
                raise RuntimeError(f"Token refresh failed: {body[:200]}")

            new_token_data = await response.json()

        # Update in-memory state
        self._access_token = new_token_data['access_token']
        self._expires_at = datetime.now() + timedelta(
            seconds=new_token_data.get('expires_in', 3600)
        )

        # Preserve refresh_token if not returned
        if 'refresh_token' not in new_token_data:
            new_token_data['refresh_token'] = self._refresh_token

        # Add expiry timestamp
        new_token_data['expires_at'] = self._expires_at.isoformat()

        # Save to file
        await self._save_token(new_token_data)

        logger.info("Access token refreshed successfully")

    async def _save_token(self, token_data: dict):
        """Save token data to file."""
        async with aiofiles.open(self.token_path, 'w') as f:
            await f.write(json.dumps(token_data, indent=2))

    @property
    def access_token(self) -> Optional[str]:
        return self._access_token
