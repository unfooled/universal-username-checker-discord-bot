import aiohttp
from checkers.token_manager import github_token

NAME  = "GitHub"
EMOJI = "🐙"
COLOR = 0x24292E
DELAY = 0.5   # API allows way faster checks than scraping
LINK  = "https://github.com/{}"

_API = "https://api.github.com/users/{}"

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    try:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        token = github_token.get()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with session.get(
            _API.format(username),
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 404:
                return "available"
            if r.status == 200:
                return "taken"
            if r.status == 429 or r.status == 403:
                # Check if rate limited
                remaining = r.headers.get("X-RateLimit-Remaining", "1")
                if remaining == "0":
                    tmsg = github_token.rotate()
                    return ("ratelimit", tmsg)
                return "ratelimit"
            return "unclear"
    except Exception:
        return "unclear"
