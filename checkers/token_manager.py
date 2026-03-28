"""
Token manager — loads tokens from files in the tokens/ folder.
Tokens are NEVER exposed to Discord users. Only status messages like
"Using token 1/3" or "⚠️ Rotating to token 2/3..." are shown.
"""

import os
import time
from typing import Optional

TOKENS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tokens")


def _load(filename: str) -> list[str]:
    path = os.path.join(TOKENS_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]


class TokenManager:
    """Rotates through a list of tokens. Never returns the raw token to callers
    except via get() which is only used internally by checkers."""

    def __init__(self, tokens: list[str], label: str = "token"):
        self._tokens = tokens
        self._index = 0
        self._rate_limited_until: dict[int, float] = {}
        self.label = label

    @property
    def count(self) -> int:
        return len(self._tokens)

    @property
    def available(self) -> bool:
        return len(self._tokens) > 0

    def get(self) -> Optional[str]:
        """Returns current token value. INTERNAL USE ONLY — do not show to users."""
        if not self._tokens:
            return None
        return self._tokens[self._index]

    def status_message(self) -> str:
        """Safe status string — shows index/count but NOT the token value."""
        if not self._tokens:
            return "no tokens loaded"
        return f"{self.label} {self._index + 1}/{len(self._tokens)}"

    def rotate(self) -> str:
        """Rotate to next available token. Returns a safe status message."""
        if not self._tokens or len(self._tokens) == 1:
            return self.status_message()
        now = time.time()
        for _ in range(len(self._tokens)):
            self._index = (self._index + 1) % len(self._tokens)
            if self._rate_limited_until.get(self._index, 0) <= now:
                return f"⚠️ Rotating to {self.status_message()}"
        # all rate limited — pick soonest
        best = min(range(len(self._tokens)),
                   key=lambda i: self._rate_limited_until.get(i, 0))
        self._index = best
        wait = max(0, self._rate_limited_until.get(self._index, 0) - now)
        return f"⚠️ All {self.label}s rate limited — {self.status_message()} ready in {wait:.1f}s"

    def mark_rate_limited(self, retry_after: float = 5.0):
        self._rate_limited_until[self._index] = time.time() + retry_after


# ── Singletons loaded at startup ──────────────────────────────────────────────
discord_tokens     = TokenManager(_load("discord_tokens.txt"),    label="token")
ig_sessions        = TokenManager(_load("ig_sessions.txt"),       label="session")
youtube_api_key    = TokenManager(_load("youtube_api_key.txt"),   label="yt_key")
pinterest_tokens   = TokenManager(_load("pinterest_tokens.txt"),  label="pinterest_token")
twitch_credentials = TokenManager(_load("twitch_credentials.txt"), label="twitch")
github_token       = TokenManager(_load("github_token.txt"),      label="github_token")
