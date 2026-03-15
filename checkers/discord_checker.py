"""
Discord checker — identical logic to the GUI version.
Uses the same headers, retry loop, token rotation, and delay as the desktop app.
"""
import asyncio
import time
import random
import aiohttp
from .token_manager import discord_tokens

NAME  = "Discord"
EMOJI = "💬"
COLOR = 0x5865F2
DELAY = 0  # We handle delay manually inside check() to match GUI logic
LINK  = None

POMELO_URL = "https://discord.com/api/v9/users/@me/pomelo-attempt"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Shared rate limit state across all calls (mirrors GUI's self.rate_limit_until)
_rate_limit_until: dict[int, float] = {}

def _get_token_index():
    return discord_tokens._index

def _next_token() -> str:
    """Rotate to next free token. Returns a safe status message."""
    tokens = discord_tokens._tokens
    if not tokens:
        return ""
    now = time.time()
    for _ in range(len(tokens)):
        discord_tokens._index = (discord_tokens._index + 1) % len(tokens)
        if _rate_limit_until.get(discord_tokens._index, 0) <= now:
            return f"[TOKEN] Switched to token {discord_tokens._index + 1}/{len(tokens)}"
    # All rate limited — pick soonest
    best = min(range(len(tokens)), key=lambda i: _rate_limit_until.get(i, 0))
    discord_tokens._index = best
    wait = max(0, _rate_limit_until.get(best, 0) - now)
    return f"[TOKEN] All tokens rate limited. Token {discord_tokens._index + 1} ready in {wait:.2f}s"

def _current_token() -> str:
    tokens = discord_tokens._tokens
    if not tokens:
        return ""
    return tokens[discord_tokens._index]

async def check(session: aiohttp.ClientSession, username: str, **_) -> str:
    """
    Identical retry loop to the GUI version:
    - Uses Authorization header with current token
    - On 429: reads retry_after, marks token rate limited, rotates, retries immediately
    - On 401: rotates token, retries
    - Random delay 2.5s ±30% after each username (handled in run_check via DELAY=0 + sleep here)
    """
    payload = {"username": username}

    # Retry loop — same as GUI's while True
    for attempt in range(10):  # max 10 retries per username
        token = _current_token()
        req_headers = {"Authorization": token} if token else {}

        try:
            async with session.post(
                POMELO_URL,
                json=payload,
                headers=req_headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                status = resp.status

                if status in (200, 201):
                    data = await resp.json()
                    if "taken" in data:
                        return "taken" if data["taken"] else "available"
                    return "unclear"

                elif status == 429:
                    try:
                        data = await resp.json()
                        retry_after = float(data.get("retry_after", 5.0))
                    except Exception:
                        retry_after = 5.0
                    idx = _get_token_index()
                    _rate_limit_until[idx] = time.time() + retry_after
                    msg = _next_token()
                    # Only sleep if all tokens are busy
                    new_idx = _get_token_index()
                    wait = max(0, _rate_limit_until.get(new_idx, 0) - time.time())
                    if wait > 1:
                        await asyncio.sleep(wait + 1)
                    continue  # retry same username with new token

                elif status == 401:
                    _next_token()
                    continue  # retry with new token

                else:
                    return "unclear"

        except asyncio.TimeoutError:
            return "unclear"
        except Exception:
            return "unclear"

    return "unclear"


# Session-level setup — called once per check run to match GUI's aiohttp.ClientSession setup
SESSION_HEADERS = {
    "Content-Type": "application/json",
    "Origin":       "https://discord.com",
    "Referer":      "https://discord.com/",
    "User-Agent":   USER_AGENT,
}
