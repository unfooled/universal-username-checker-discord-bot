import aiohttp

NAME   = "Roblox"
EMOJI  = "🎮"
COLOR  = 0xE8373E
DELAY  = 0.5
LINK   = "https://www.roblox.com/search/users?keyword={}"

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    try:
        async with session.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username]},
            timeout=aiohttp.ClientTimeout(total=8)
        ) as r:
            if r.status == 429: return "ratelimit"
            if r.status != 200: return "unclear"
            data = await r.json()
            return "taken" if (data.get("data") and len(data["data"]) > 0) else "available"
    except Exception:
        return "unclear"
