import aiohttp
from .token_manager import pinterest_tokens

NAME  = "Pinterest"
EMOJI = "📌"
COLOR = 0xE60023
DELAY = 1.0
LINK  = "https://pinterest.com/{}"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    token = pinterest_tokens.get()

    headers = {
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
    }
    if token:
        headers["Cookie"]      = f"csrftoken={token}"
        headers["X-CSRFToken"] = token

    try:
        async with session.get(
            f"https://www.pinterest.com/{username}/",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
            allow_redirects=True,
        ) as r:
            if r.status == 404:
                return "available"
            if r.status == 429:
                pinterest_tokens.mark_rate_limited(10)
                pinterest_tokens.rotate()
                return "ratelimit"
            if r.status == 200:
                body = await r.text(errors="ignore")
                # Available pages return 200 but have NO "username" field at all
                if '"username"' not in body:
                    return "available"
                # Taken pages have "username":"<name>" in body
                if f'"username":"{username}"' in body or f'"username": "{username}"' in body:
                    return "taken"
                return "unclear"
            return "unclear"
    except Exception:
        return "unclear"
