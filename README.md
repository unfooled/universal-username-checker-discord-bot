# Username Checker Bot

## Commands
| Command | Platform | Tokens needed? |
|---|---|---|
| `/checkmc` | Minecraft | ❌ |
| `/checkroblox` | Roblox | ❌ |
| `/checkgithub` | GitHub | ❌ |
| `/checkig` | Instagram | ✅ `tokens/ig_sessions.txt` |
| `/checktiktok` | TikTok | ❌ |
| `/checksteam` | Steam | ❌ |
| `/checkpsn` | PlayStation | ❌ |
| `/checkgd` | Geometry Dash | ❌ |
| `/checkdiscord` | Discord (pomelo) | ✅ `tokens/discord_tokens.txt` (optional — works without) |
| `/stopcheck` | — | — |

All commands take: `length` · `underscores` · `charset` · `amount`

---

## Setup

```
pip install -r requirements.txt
```

Paste your bot token in `bot.py` where it says `YOUR_BOT_TOKEN_HERE` (or set env var `DISCORD_TOKEN`).

### Adding tokens
- Open `tokens/discord_tokens.txt` — paste Discord tokens, one per line
- Open `tokens/ig_sessions.txt` — paste Instagram sessionid cookies, one per line

Users will **never** see the actual token values. The bot only shows things like:
> "Using token 1/3" · "⚠️ Rotating to token 2/3..."

### Run
```
python bot.py
```

---

## File structure
```
bot/
├── bot.py
├── requirements.txt
├── tokens/
│   ├── discord_tokens.txt   ← your Discord tokens (hidden from users)
│   └── ig_sessions.txt      ← your IG sessions  (hidden from users)
└── checkers/
    ├── token_manager.py
    ├── mc.py
    ├── roblox.py
    ├── github.py
    ├── ig.py
    ├── tiktok.py
    ├── steam.py
    ├── psn.py
    ├── gd.py
    └── discord_checker.py
```
