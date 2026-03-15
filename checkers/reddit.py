import aiohttp

NAME  = "Reddit"
EMOJI = "🤖"
COLOR = 0xFF4500
DELAY = 2.0
LINK  = "https://reddit.com/u/{}"

# Reddit requires a descriptive User-Agent or it blocks immediately
HEADERS = {
    "User-Agent": "UsernameChecker/1.0 by skiesfr",
}

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    try:
        async with session.get(
            "https://www.reddit.com/api/username_available.json",
            params={"user": username},
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 429:
                return "ratelimit"
            if r.status == 404:
                # Reddit rejects invalid username formats (starts with number etc)
                return "invalid"
            if r.status != 200:
                return "unclear"
            text = (await r.text()).strip()
            if text == "true":
                return "available"
            if text == "false":
                return "taken"
            return "unclear"
    except Exception:
        return "unclear"
