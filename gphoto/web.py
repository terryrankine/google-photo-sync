"""Status page. Shows what the other services recorded and changes nothing.

Cloudflare Access sits in front. Its signed token is checked again here, so a
device on the LAN that talks to Traefik directly is refused too.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import anyio.to_thread
import jwt
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from gphoto import status

logger = logging.getLogger(__name__)

TOKEN_HEADER = "Cf-Access-Jwt-Assertion"
REQUIRED = ("CF_ACCESS_TEAM", "CF_ACCESS_AUD", "ALLOWED_EMAIL")
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


@dataclass
class Access:
    """Who may look. Anything that does not check out is refused."""

    team: str
    audience: str
    email: str
    key_for: Callable[[str], Any] | None = None
    _keys: Any = field(default=None, repr=False)

    def _key(self, token: str) -> Any:
        if self.key_for is not None:
            return self.key_for(token)
        if self._keys is None:
            self._keys = jwt.PyJWKClient(f"{self.team}/cdn-cgi/access/certs", timeout=10)
        return self._keys.get_signing_key_from_jwt(token).key

    def allows(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            claims = jwt.decode(
                token, self._key(token), algorithms=["RS256"], audience=self.audience,
                issuer=self.team, options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError as error:
            logger.warning("Refused: %s", error)
            return False
        if str(claims.get("email") or "").lower() != self.email.lower():
            logger.warning("Refused: valid token for someone else")
            return False
        return True


def _ago(now: float, then: float | None) -> str:
    if then is None:
        return "never"
    seconds = max(0, int(now - then))
    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= size:
            count = seconds // size
            return f"{count} {unit}{'' if count == 1 else 's'} ago"
    return "just now"


def _until(now: float, then: float) -> str:
    minutes = max(0, int(then - now + 59) // 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def create_app(
    state: Path,
    access: Access,
    wait_seconds: float,
    clock: Callable[[], float] = time.time,
    chrome_url: str = "",
    zone: str = "Australia/Perth",
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    pages = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(default=True, default_for_string=True),
    )
    local = ZoneInfo(zone)

    @app.middleware("http")
    async def only_allowed(request: Request, call_next):
        if request.url.path == "/healthz":
            return PlainTextResponse("ok")
        # Key lookup can reach out to Cloudflare, so it must not block the loop.
        token = request.headers.get(TOKEN_HEADER)
        if not await anyio.to_thread.run_sync(access.allows, token):
            return PlainTextResponse("Not allowed", status_code=403, headers=SECURITY_HEADERS)
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    def current() -> status.Status:
        return status.read(state, now=clock(), wait_seconds=wait_seconds)

    @app.get("/")
    def page() -> HTMLResponse:
        s = current()

        def when(then: float | None) -> str:
            return datetime.fromtimestamp(then, local).strftime("%d %b %H:%M") if then else ""

        def taken(value: str | None) -> str:
            return datetime.fromisoformat(value).strftime("%d %b %Y %H:%M") if value else ""

        return HTMLResponse(
            pages.get_template("status.html").render(
                s=s, chrome_url=chrome_url, when=when, taken=taken,
                ago=lambda t: _ago(s.now, t), until=lambda t: _until(s.now, t),
            )
        )

    @app.get("/api/status")
    def api() -> JSONResponse:
        s = current()
        return JSONResponse({"ok": s.ok, **asdict(s)})

    return app


def from_env() -> FastAPI:
    """Build the app from the environment. Refuses to start without access settings."""
    missing = [name for name in REQUIRED if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"missing settings: {', '.join(missing)}")
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
    )
    return create_app(
        state=Path(os.getenv("STATE_DIR", "/state")),
        access=Access(
            team=os.environ["CF_ACCESS_TEAM"].rstrip("/"),
            audience=os.environ["CF_ACCESS_AUD"],
            email=os.environ["ALLOWED_EMAIL"],
        ),
        wait_seconds=float(os.getenv("WAIT_HOURS", "4")) * 3600,
        chrome_url=os.getenv("CHROME_URL", ""),
        zone=os.getenv("TZ", "Australia/Perth"),
    )
