import aiohttp, re

NAME   = "TikTok"
EMOJI  = "🎵"
COLOR  = 0x010101
DELAY  = 2.5
LINK   = "https://tiktok.com/@{}"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    try:
        headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "max-age=0",
        }
        async with session.get(
            f"https://www.tiktok.com/@{username}",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
            allow_redirects=True,
            ssl=False,
        ) as r:
            if r.status in (429, 403): return "ratelimit"
            if username.lower() not in str(r.url).lower(): return "available"

            body = await r.text(errors="ignore")

            if re.search(rf'"uniqueId"\s*:\s*"{re.escape(username)}"', body, re.I):
                return "taken"

            has_id       = bool(re.search(r'"id"\s*:\s*"\d{10,}"', body))
            has_followers = bool(re.search(r'"followerCount"\s*:\s*\d+', body))
            if has_id and has_followers:
                return "taken"

            not_found = ["couldn't find this account", "user not found", '"statuscode":10202']
            signals = sum([has_id, has_followers,
                           bool(re.search(r'"videocount"\s*:\s*\d+', body.lower()))])
            if any(s in body.lower() for s in not_found) and signals == 0:
                return "available"
            if signals == 0:
                return "available"
            return "unclear"
    except Exception:
        return "unclear"
