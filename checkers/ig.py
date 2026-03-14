import aiohttp, re
from .token_manager import ig_sessions

NAME   = "Instagram"
EMOJI  = "📸"
COLOR  = 0xE91E8C
DELAY  = 2.5
LINK   = "https://instagram.com/{}"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def check(session: aiohttp.ClientSession, username: str, **_) -> tuple[str, str]:
    """Returns (result, token_status_msg)"""
    token = ig_sessions.get()
    token_msg = f"Using {ig_sessions.status_message()}" if token else "No session loaded"

    try:
        headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }
        if token:
            headers["Cookie"] = f"sessionid={token}"

        async with session.get(
            f"https://www.instagram.com/{username}/",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
            allow_redirects=True,
        ) as r:
            if r.status == 404:
                return "available", token_msg
            if r.status == 429:
                ig_sessions.mark_rate_limited(10)
                msg = ig_sessions.rotate()
                return "ratelimit", msg
            if r.status in (400, 403):
                msg = ig_sessions.rotate()
                return "unclear", msg
            if "login" in str(r.url).lower():
                msg = ig_sessions.rotate()
                return "session_expired", f"Session expired — {msg}"

            body = await r.text(errors="ignore")
            not_found = ["page_not_found", '"pagenotfound"',
                         "sorry, this page isn't available", '"statuscode":404']
            if any(s in body.lower() for s in not_found):
                return "available", token_msg
            if re.search(rf'"username"\s*:\s*"{re.escape(username)}"', body, re.I):
                return "taken", token_msg
            if re.search(r'"edge_followed_by"\s*:\s*\{[^}]*"count"\s*:\s*\d+', body):
                return "taken", token_msg
            return "unclear", token_msg

    except Exception:
        return "unclear", token_msg
