import aiohttp

NAME  = "Pinterest"
EMOJI = "📌"
COLOR = 0xE60023
DELAY = 1.0
LINK  = "https://pinterest.com/{}"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    try:
        async with session.get(
            f"https://www.pinterest.com/{username}/",
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=aiohttp.ClientTimeout(total=10),
            allow_redirects=True,
        ) as r:
            if r.status == 404:
                return "available"
            if r.status == 429:
                return "ratelimit"
            if r.status == 200:
                body = await r.text(errors="ignore")
                if "sorry, we couldn't find that page" in body.lower():
                    return "available"
                if '"username"' in body and username.lower() in body.lower():
                    return "taken"
                return "taken"
            return "unclear"
    except Exception:
        return "unclear"
