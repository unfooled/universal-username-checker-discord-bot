import aiohttp

NAME   = "Minecraft"
EMOJI  = "⛏️"
COLOR  = 0x3BA55D
DELAY  = 0.4
LINK   = "https://namemc.com/name/{}"

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    try:
        url = f"https://api.mojang.com/users/profiles/minecraft/{username}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status == 404:  return "available"
            if r.status == 200:  return "taken"
            if r.status == 429:  return "ratelimit"
            return "unclear"
    except Exception:
        return "unclear"
