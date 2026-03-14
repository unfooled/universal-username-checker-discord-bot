import aiohttp

NAME   = "Geometry Dash"
EMOJI  = "🔺"
COLOR  = 0xFF6B35
DELAY  = 1.2
LINK   = None  # no public profile URL

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    try:
        async with session.post(
            "http://www.boomlings.com/database/getGJUsers20.php",
            data={"str": username, "total": 0, "page": 0, "secret": "Wmfd2893gb7"},
            headers={"User-Agent": ""},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status != 200: return "unclear"
            text = (await r.text(errors="ignore")).strip()
            if text == "-1":   return "available"
            if text == "-2":   return "ratelimit"
            if "#" in text and ":" in text: return "taken"
            return "unclear"
    except Exception:
        return "unclear"
