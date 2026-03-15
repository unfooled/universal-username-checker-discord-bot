import asyncio
import aiohttp
from .token_manager import twitch_credentials

NAME  = "Twitch"
EMOJI = "🟣"
COLOR = 0x9146FF
DELAY = 0.3
LINK  = "https://twitch.tv/{}"

_token_cache: dict = {"token": None, "expires_at": 0}

async def _get_token(session: aiohttp.ClientSession) -> str:
    import time
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 3600:
        return _token_cache["token"]

    creds = twitch_credentials.get()
    if not creds:
        return ""

    try:
        client_id, client_secret = creds.split(":", 1)
    except ValueError:
        return ""

    try:
        async with session.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id":     client_id,
                "client_secret": client_secret,
                "grant_type":    "client_credentials",
            },
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status != 200:
                return ""
            data = await r.json()
            token = data.get("access_token", "")
            expires_in = data.get("expires_in", 3600)
            _token_cache["token"] = token
            _token_cache["expires_at"] = time.time() + expires_in
            return token
    except Exception:
        return ""

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    creds = twitch_credentials.get()
    if not creds:
        return "unclear"

    try:
        client_id = creds.split(":", 1)[0]
    except ValueError:
        return "unclear"

    token = await _get_token(session)
    if not token:
        return "unclear"

    try:
        async with session.get(
            "https://api.twitch.tv/helix/users",
            params={"login": username},
            headers={
                "Authorization": f"Bearer {token}",
                "Client-Id":     client_id,
            },
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 429:
                twitch_credentials.mark_rate_limited(30)
                return "ratelimit"
            if r.status == 401:
                # Token expired — clear cache and retry once
                _token_cache["token"] = None
                return "unclear"
            if r.status != 200:
                return "unclear"
            data = await r.json()
            return "taken" if data.get("data") else "available"
    except Exception:
        return "unclear"
