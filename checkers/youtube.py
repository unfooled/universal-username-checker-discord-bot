import aiohttp
from .token_manager import youtube_api_key

NAME  = "YouTube"
EMOJI = "▶️"
COLOR = 0xFF0000
DELAY = 0.5
LINK  = "https://youtube.com/@{}"

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    key = youtube_api_key.get()
    if not key:
        return "unclear"

    try:
        # forHandle needs the @ included as plain text
        params = {
            "part": "id",
            "forHandle": f"@{username}",
            "key": key,
        }
        async with session.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 403:
                youtube_api_key.mark_rate_limited(60)
                youtube_api_key.rotate()
                return "ratelimit"
            if r.status == 400:
                return "unclear"
            if r.status != 200:
                return "unclear"
            data = await r.json()
            # Empty items list = handle is available
            if not data.get("items"):
                return "available"
            return "taken"
    except Exception:
        return "unclear"
