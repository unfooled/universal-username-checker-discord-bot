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
        url = (
            f"https://www.googleapis.com/youtube/v3/channels"
            f"?part=id&forHandle=%40{username}&key={key}"
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 403:
                youtube_api_key.mark_rate_limited(60)
                youtube_api_key.rotate()
                return "ratelimit"
            if r.status not in (200,):
                return "unclear"
            data = await r.json()
            if not data.get("items"):
                return "available"
            return "taken"
    except Exception:
        return "unclear"
