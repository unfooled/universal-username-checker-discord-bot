import aiohttp

NAME   = "Steam"
EMOJI  = "🎲"
COLOR  = 0x1B2838
DELAY  = 0.5
LINK   = "https://steamcommunity.com/id/{}"

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    try:
        async with session.get(
            f"https://steamcommunity.com/id/{username}/?xml=1",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 429: return "ratelimit"
            if r.status != 200: return "unclear"
            text = (await r.text(errors="ignore")).lower()
            if "could not be found" in text or "<e>" in text:
                return "available"
            if "<steamid>" in text or "<steamid64>" in text:
                return "taken"
            return "unclear"
    except Exception:
        return "unclear"
