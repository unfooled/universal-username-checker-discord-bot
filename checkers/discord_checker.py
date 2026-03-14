import aiohttp, asyncio, time
from .token_manager import discord_tokens

NAME   = "Discord"
EMOJI  = "💬"
COLOR  = 0x5865F2
DELAY  = 0.5
LINK   = None

_POMELO_URL = "https://discord.com/api/v9/users/@me/pomelo-attempt"
_UNAUTHED_URL = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_HEADERS_BASE = {
    "Content-Type": "application/json",
    "Origin": "https://discord.com",
    "Referer": "https://discord.com/",
    "User-Agent": _UA,
}

async def check(session: aiohttp.ClientSession, username: str, **_) -> tuple[str, str]:
    """Returns (result, token_status_msg)"""
    token = discord_tokens.get()
    token_msg = f"Using {discord_tokens.status_message()}" if token else "No tokens — using unauthed endpoint"

    url = _POMELO_URL if token else _UNAUTHED_URL
    headers = dict(_HEADERS_BASE)
    if token:
        headers["Authorization"] = token

    for attempt in range(3):
        try:
            async with session.post(
                url,
                json={"username": username},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                status = r.status

                if status in (200, 201):
                    data = await r.json()
                    taken = data.get("taken", True)
                    return ("taken" if taken else "available"), token_msg

                if status == 429:
                    try:
                        data = await r.json()
                        retry_after = float(data.get("retry_after", 5.0))
                    except Exception:
                        retry_after = 5.0
                    discord_tokens.mark_rate_limited(retry_after)
                    msg = discord_tokens.rotate()
                    token = discord_tokens.get()
                    if token:
                        headers["Authorization"] = token
                    await asyncio.sleep(min(retry_after, 2))
                    continue

                if status == 401:
                    msg = discord_tokens.rotate()
                    token = discord_tokens.get()
                    if token:
                        headers["Authorization"] = token
                    continue

                return "unclear", token_msg

        except Exception:
            if attempt == 2:
                return "unclear", token_msg
            await asyncio.sleep(1)

    return "unclear", token_msg
