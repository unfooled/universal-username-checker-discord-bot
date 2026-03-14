import aiohttp

NAME   = "PlayStation"
EMOJI  = "🕹️"
COLOR  = 0x003087
DELAY  = 1.2
LINK   = "https://www.playstation.com/en-us/profiles/{}/"

_URL = "https://accounts.api.playstation.com/api/v1/accounts/onlineIds"
_HEADERS = {
    "Host": "accounts.api.playstation.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json; charset=UTF-8",
    "Accept": "*/*",
    "Origin": "https://id.sonyentertainmentnetwork.com",
    "Referer": "https://id.sonyentertainmentnetwork.com/",
}

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    try:
        async with session.post(
            _URL,
            json={"onlineId": username, "reserveIfAvailable": False},
            headers=_HEADERS,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status in (200, 201): return "available"
            if r.status == 429:        return "ratelimit"
            if r.status == 406:        return "invalid"
            if r.status == 400:
                try:
                    data = await r.json()
                    code = str(data[0].get("code", "")) if isinstance(data, list) and data else ""
                    if code == "3101": return "taken"
                    if code in ("1100", "3208"): return "invalid"
                except Exception:
                    pass
                return "taken"
            return "unclear"
    except Exception:
        return "unclear"
