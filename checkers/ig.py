import aiohttp
import re
from .token_manager import ig_sessions

NAME  = "Instagram"
EMOJI = "📸"
COLOR = 0xE91E8C
DELAY = 2.0
LINK  = "https://instagram.com/{}"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    token = ig_sessions.get()

    # Exact headers from the GUI version
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }
    if token:
        headers["Cookie"] = f"sessionid={token}"

    try:
        async with session.get(
            f"https://www.instagram.com/{username}/",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
            allow_redirects=True,
        ) as r:
            status = r.status

            if status == 404:
                return "available"

            if status == 429:
                ig_sessions.mark_rate_limited(10)
                ig_sessions.rotate()
                return "ratelimit"

            if status in (400, 403):
                ig_sessions.rotate()
                return "unclear"

            if "login" in str(r.url).lower():
                ig_sessions.rotate()
                return "unclear"

            body = await r.text(errors="ignore")
            body_lower = body.lower()

            # Not found signals — same as GUI
            not_found = [
                '"httpError":{"statusCode":404',
                'page_not_found',
                '"PageNotFound"',
                "sorry, this page isn't available",
                '"status_code":404',
            ]
            if any(s.lower() in body_lower for s in not_found):
                return "available"

            # Count profile signals — same logic as GUI
            signals = 0

            # Username match in data
            has_username = bool(re.search(rf'"username"\s*:\s*"{re.escape(username)}"', body, re.I))
            if has_username:
                signals += 1

            # Real user ID linked to username
            user_id_match = re.search(r'"user"\s*:\s*\{[^}]*"id"\s*:\s*"(\d{5,})"', body)
            has_real_id = False
            if user_id_match:
                uid = user_id_match.group(1)
                if re.search(rf'"username"\s*:\s*"{username}"[^}}]*"id"\s*:\s*"{uid}"', body, re.I):
                    has_real_id = True
                    signals += 1

            # Follower count
            if re.search(r'"edge_followed_by"\s*:\s*\{[^}]*"count"\s*:\s*\d+', body):
                signals += 1

            # Following count
            if re.search(r'"edge_follow"\s*:\s*\{[^}]*"count"\s*:\s*\d+', body):
                signals += 1

            # Post count
            if re.search(r'"edge_owner_to_timeline_media"\s*:\s*\{[^}]*"count"\s*:\s*\d+', body):
                signals += 1

            # Profile pic
            if re.search(r'"profile_pic_url"\s*:\s*"https://[^"]+scontent[^"]*"', body):
                signals += 1

            # Biography with content
            bio = re.search(r'"biography"\s*:\s*"([^"]+)"', body)
            if bio and bio.group(1).strip():
                signals += 1

            # Decision — same as GUI
            if has_username and has_real_id:
                return "taken"
            if signals >= 4:
                return "taken"

            engagement = sum([
                bool(re.search(r'"edge_followed_by"', body)),
                bool(re.search(r'"edge_follow"', body)),
                bool(re.search(r'"edge_owner_to_timeline_media"', body)),
            ])
            if engagement >= 2 and bool(re.search(r'"profile_pic_url"', body)):
                return "taken"

            # Check title
            title = re.search(r'<title>([^<]+)</title>', body, re.I)
            if title:
                t = title.group(1)
                if username.lower() in t.lower() and ('posts' in t.lower() or 'followers' in t.lower()):
                    if signals >= 2:
                        return "taken"

            if signals <= 1:
                return "available"

            if signals == 2 and not has_username:
                return "available"

            return "unclear"

    except Exception:
        return "unclear"
