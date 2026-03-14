import aiohttp

NAME   = "GitHub"
EMOJI  = "🐙"
COLOR  = 0x24292E
DELAY  = 1.2
LINK   = "https://github.com/{}"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    try:
        async with session.get(
            f"https://github.com/{username}",
            headers={"User-Agent": UA},
            timeout=aiohttp.ClientTimeout(total=10),
            allow_redirects=True,
        ) as r:
            if r.status == 404:  return "available"
            if r.status == 200:  return "taken"
            if r.status in (429, 403): return "ratelimit"
            return "unclear"
    except Exception:
        return "unclear"
