import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import aiohttp
import random
import string
import os
import asyncio

from checkers import mc, roblox, github, ig, tiktok, steam, psn, gd, discord_checker, pinterest, youtube, twitch, reddit
from checkers.token_manager import discord_tokens, ig_sessions, youtube_api_key, pinterest_tokens, twitch_credentials

# ─────────────────────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# user_id → asyncio.Event  (set = stop signal)
active_checks: dict[int, asyncio.Event] = {}


# ── Username generator ────────────────────────────────────────────────────────
def gen_names(length: int, underscores: bool, charset: str, amount: int, platform: str = "") -> list[str]:
    if charset == "letters":
        pool = string.ascii_lowercase
    elif charset == "numbers":
        pool = string.digits
    else:
        pool = string.ascii_lowercase + string.digits

    names: set[str] = set()
    for _ in range(amount * 30):
        if len(names) >= amount:
            break
        if underscores and length >= 3 and random.random() < 0.3:
            pos  = random.randint(1, length - 2)
            name = ("".join(random.choices(pool, k=pos))
                    + "_"
                    + "".join(random.choices(pool, k=length - pos - 1)))
        else:
            name = "".join(random.choices(pool, k=length))

        # Pinterest requires at least 3 letters — no numbers-only or letter-starved names
        if platform == "pinterest":
            letter_count = sum(1 for c in name if c.isalpha())
            if letter_count < 3:
                continue

        if 3 <= len(name) <= 25:
            names.add(name)
    return list(names)[:amount]


def parse_custom_names(text: str) -> list[str]:
    """Parse newline-separated usernames from user input."""
    names = []
    for line in text.strip().splitlines():
        name = line.strip()
        if name:
            names.append(name)
    return names


# ── Shared options (DRY) ──────────────────────────────────────────────────────
_underscore_choices = [
    app_commands.Choice(name="Yes", value="yes"),
    app_commands.Choice(name="No",  value="no"),
]
_charset_choices = [
    app_commands.Choice(name="Letters only",              value="letters"),
    app_commands.Choice(name="Numbers only",              value="numbers"),
    app_commands.Choice(name="Mixed (letters + numbers)", value="mixed"),
]


# ── Core runner (used by every command) ───────────────────────────────────────
async def run_check(
    interaction: discord.Interaction,
    mod,
    usernames: list[str],
    stop_event: asyncio.Event,
    cooldown_store: dict = None,
):
    uid = interaction.user.id
    available_list, unavailable, unclear = [], 0, 0
    token_msgs: list[str] = []

    try:
        connector = aiohttp.TCPConnector(ssl=True)
        from checkers.discord_checker import SESSION_HEADERS
        session_headers = SESSION_HEADERS if mod.__name__ == "checkers.discord_checker" else {}
        async with aiohttp.ClientSession(connector=connector, headers=session_headers) as session:
            for username in usernames:
                if stop_event.is_set():
                    break

                raw = await mod.check(session, username)

                if isinstance(raw, tuple):
                    result, tmsg = raw
                    if tmsg and tmsg not in token_msgs:
                        token_msgs.append(tmsg)
                else:
                    result = raw

                if result == "available":
                    available_list.append(username)
                elif result == "taken":
                    unavailable += 1
                elif result == "ratelimit":
                    unclear += 1
                    await asyncio.sleep(3)
                elif result == "invalid":
                    unclear += 1
                elif result == "session_expired":
                    unclear += 1
                else:
                    unclear += 1

                if mod.__name__ == "checkers.discord_checker":
                    base = 2.5
                    delay = max(0.5, base + random.uniform(-base * 0.3, base * 0.3))
                    await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(mod.DELAY)

    finally:
        active_checks.pop(uid, None)
        if cooldown_store is not None and not has_paid_role(interaction):
            import time
            cooldown_store[interaction.user.id] = time.time()

    # ── Build embed ───────────────────────────────────────────────────────────
    stopped = stop_event.is_set()
    total   = len(available_list) + unavailable + unclear

    embed = discord.Embed(
        title=f"{'🛑 Stopped' if stopped else '✅ Finished'}",
        color=mod.COLOR,
    )
    embed.set_author(name=f"{mod.EMOJI}  {mod.NAME} Checker")
    embed.add_field(name="✅ Available",   value=f"**{len(available_list)}**", inline=True)
    embed.add_field(name="❌ Unavailable", value=f"**{unavailable}**",         inline=True)
    embed.add_field(name="⚠️ Unclear",    value=f"**{unclear}**",             inline=True)

    if available_list:
        shown = available_list[:25]
        if getattr(mod, "LINK", None):
            val = "\n".join(f"[`{n}`]({mod.LINK.format(n)})" for n in shown[:15])
        else:
            val = "\n".join(f"`{n}`" for n in shown)
        if len(available_list) > 25:
            val += f"\n*…and {len(available_list) - 25} more*"
        embed.add_field(name="🎉 Available", value=val, inline=False)

    # Show token status (safe - no actual token values)
    if token_msgs:
        embed.set_footer(text=" · ".join(token_msgs[-3:]))
    else:
        embed.set_footer(text=f"Checked {total} username{'s' if total != 1 else ''}")

    status = "🛑 stopped" if stopped else "✅ finished"
    await interaction.followup.send(
        f"{mod.EMOJI} **{interaction.user.mention}** — check {status}.",
        embed=embed,
    )


# ── Cooldown system ───────────────────────────────────────────────────────────
PAID_ROLE = "paid"

# user_id -> timestamp of last use, per command type
_cooldowns_regular: dict[int, float] = {}   # 1 min cooldown
_cooldowns_discord: dict[int, float] = {}   # 1 hour cooldown

def has_paid_role(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False
    return any(r.name.lower() == PAID_ROLE for r in interaction.user.roles)

async def check_cooldown(
    interaction: discord.Interaction,
    store: dict,
    seconds: int,
) -> bool:
    """Returns True if user is allowed to proceed. Sends error and returns False if on cooldown."""
    if has_paid_role(interaction):
        return True
    import time
    now     = time.time()
    last    = store.get(interaction.user.id, 0)
    remaining = seconds - (now - last)
    if remaining > 0:
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        if mins > 0:
            time_str = f"{mins}m {secs}s"
        else:
            time_str = f"{secs}s"
        await interaction.response.send_message(
            f"🕐 You're on cooldown for **{time_str}**!\n"
            f"*(Get the **{PAID_ROLE}** role to bypass all cooldowns & limits)*",
            ephemeral=True,
        )
        return False
    # Don't record time here — recorded after check finishes
    return True

def cap_amount(interaction: discord.Interaction, amount: int, limit: int) -> int:
    """Caps amount to limit unless user has paid role."""
    if has_paid_role(interaction):
        return amount
    return min(amount, limit)


# ── Guard helper ──────────────────────────────────────────────────────────────
class CustomNamesModal(discord.ui.Modal, title="Enter your usernames"):
    names_input = discord.ui.TextInput(
        label="Usernames (one per line)",
        style=discord.TextStyle.paragraph,
        placeholder="hello\nworld\ntest123",
        required=True,
        max_length=2000,
    )

    def __init__(self, mod, length, underscores, charset, amount, cooldown_store):
        super().__init__()
        self.mod            = mod
        self.length         = length
        self.underscores    = underscores
        self.charset        = charset
        self.amount         = amount
        self.cooldown_store = cooldown_store

    async def on_submit(self, interaction: discord.Interaction):
        parsed = [n.strip() for n in self.names_input.value.splitlines() if n.strip()]
        if not parsed:
            await interaction.response.send_message("⚠️ No valid usernames found.", ephemeral=True)
            return

        if not has_paid_role(interaction):
            parsed = parsed[:self.amount]

        await _launch_check(interaction, self.mod, self.length, self.underscores,
                            self.charset, self.amount, self.cooldown_store, custom_names=parsed)


class CheckModeView(discord.ui.View):
    def __init__(self, mod, length, underscores, charset, amount, cooldown_store):
        super().__init__(timeout=60)
        self.mod            = mod
        self.length         = length
        self.underscores    = underscores
        self.charset        = charset
        self.amount         = amount
        self.cooldown_store = cooldown_store

    @discord.ui.button(label="🎲 Random names", style=discord.ButtonStyle.primary)
    async def random_names(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self._owner_id:
            await interaction.response.send_message("⚠️ This isn't your check!", ephemeral=True)
            return
        self.stop()
        await interaction.message.delete()
        await _launch_check(interaction, self.mod, self.length, self.underscores,
                            self.charset, self.amount, self.cooldown_store)

    @discord.ui.button(label="✏️ My own names", style=discord.ButtonStyle.secondary)
    async def custom_names(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self._owner_id:
            await interaction.response.send_message("⚠️ This isn't your check!", ephemeral=True)
            return
        self.stop()
        await interaction.message.delete()
        modal = CustomNamesModal(self.mod, self.length, self.underscores,
                                 self.charset, self.amount, self.cooldown_store)
        await interaction.response.send_modal(modal)

    async def on_timeout(self):
        try:
            await self._message.delete()
        except Exception:
            pass


async def ask_check_mode(interaction: discord.Interaction, mod, length, underscores, charset, amount, cooldown_store):
    """Send the Random / My own names prompt."""
    uid = interaction.user.id
    if uid in active_checks:
        await interaction.response.send_message(
            "⚠️ You already have a check running. Use `/stopcheck` first.", ephemeral=True)
        return

    view = CheckModeView(mod, length, underscores, charset, amount, cooldown_store)
    view._owner_id = uid

    await interaction.response.send_message(
        f"{mod.EMOJI} **{mod.NAME} Checker** — how do you want to check?",
        view=view,
        ephemeral=True,
    )
    view._message = await interaction.original_response()


async def _launch_check(interaction: discord.Interaction, mod, length, underscores, charset, amount, cooldown_store, custom_names=None):
    """Actually start the check after mode is chosen."""
    uid = interaction.user.id
    if uid in active_checks:
        await interaction.response.send_message(
            "⚠️ You already have a check running. Use `/stopcheck` first.", ephemeral=True)
        return

    if custom_names:
        names = custom_names
        # Pinterest: filter out names with less than 3 letters
        if mod.NAME.lower() == "pinterest":
            names = [n for n in names if sum(1 for c in n if c.isalpha()) >= 3]
            if not names:
                await interaction.response.send_message(
                    "⚠️ None of your names are valid for Pinterest — they need at least 3 letters.",
                    ephemeral=True)
                return
    else:
        names = gen_names(length, underscores == "yes", charset, amount,
                          platform=mod.NAME.lower().replace(" ", ""))

    stop = asyncio.Event()
    active_checks[uid] = stop

    mode = "custom names" if custom_names else f"length=**{length}**, underscores=**{underscores}**, charset=**{charset}**"
    await interaction.response.send_message(
        f"{mod.EMOJI} **{interaction.user.mention}** started `/check{mod.NAME.lower().replace(' ', '')}` "
        f"({mode}, amount=**{len(names)}**)\n"
        f"⏳ Checking… use `/stopcheck` to cancel."
    )
    asyncio.create_task(run_check(interaction, mod, names, stop, cooldown_store))


# ─────────────────────────────────────────────────────────────────────────────
# /checkmc
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checkmc", description="⛏️ Check Minecraft username availability")
@app_commands.describe(length="Username length (3–16)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checkmc(interaction: discord.Interaction,
                  length: app_commands.Range[int, 3, 16],
                  underscores: app_commands.Choice[str],
                  charset: app_commands.Choice[str],
                  amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, mc, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checkroblox
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checkroblox", description="🎮 Check Roblox username availability")
@app_commands.describe(length="Username length (3–20)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checkroblox(interaction: discord.Interaction,
                      length: app_commands.Range[int, 3, 20],
                      underscores: app_commands.Choice[str],
                      charset: app_commands.Choice[str],
                      amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, roblox, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checkgithub
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checkgithub", description="🐙 Check GitHub username availability")
@app_commands.describe(length="Username length (3–39)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checkgithub(interaction: discord.Interaction,
                      length: app_commands.Range[int, 3, 39],
                      underscores: app_commands.Choice[str],
                      charset: app_commands.Choice[str],
                      amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, github, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checkig
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checkig", description="📸 Check Instagram username availability")
@app_commands.describe(length="Username length (3–30)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checkig(interaction: discord.Interaction,
                  length: app_commands.Range[int, 3, 30],
                  underscores: app_commands.Choice[str],
                  charset: app_commands.Choice[str],
                  amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    if not ig_sessions.available:
        await interaction.response.send_message(
            "⚠️ No Instagram sessions loaded. Add `sessionid` cookies to `tokens/ig_sessions.txt`.",
            ephemeral=True)
        return
    await ask_check_mode(interaction, ig, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checktiktok
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checktiktok", description="🎵 Check TikTok username availability")
@app_commands.describe(length="Username length (3–24)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checktiktok(interaction: discord.Interaction,
                      length: app_commands.Range[int, 3, 24],
                      underscores: app_commands.Choice[str],
                      charset: app_commands.Choice[str],
                      amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, tiktok, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checksteam
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checksteam", description="🎲 Check Steam custom URL availability")
@app_commands.describe(length="ID length (3–32)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checksteam(interaction: discord.Interaction,
                     length: app_commands.Range[int, 3, 32],
                     underscores: app_commands.Choice[str],
                     charset: app_commands.Choice[str],
                     amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, steam, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checkpsn
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checkpsn", description="🕹️ Check PlayStation Network ID availability")
@app_commands.describe(length="ID length (3–16)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checkpsn(interaction: discord.Interaction,
                   length: app_commands.Range[int, 3, 16],
                   underscores: app_commands.Choice[str],
                   charset: app_commands.Choice[str],
                   amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, psn, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checkgd
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checkgd", description="🔺 Check Geometry Dash username availability")
@app_commands.describe(length="Username length (3–15)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checkgd(interaction: discord.Interaction,
                  length: app_commands.Range[int, 3, 15],
                  underscores: app_commands.Choice[str],
                  charset: app_commands.Choice[str],
                  amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, gd, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checkdiscord
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checkdiscord", description="💬 Check Discord (pomelo) username availability")
@app_commands.describe(length="Username length (2–32)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–20, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checkdiscord(interaction: discord.Interaction,
                       length: app_commands.Range[int, 2, 32],
                       underscores: app_commands.Choice[str],
                       charset: app_commands.Choice[str],
                       amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_discord, 3600): return
    await ask_check_mode(interaction, discord_checker, length, underscores.value, charset.value, cap_amount(interaction, amount, 20), _cooldowns_discord)


# ─────────────────────────────────────────────────────────────────────────────
# /purge
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="purge", description="🗑️ Delete messages from this channel")
@app_commands.describe(amount="Number of messages to delete (1–500)")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 500]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(
        f"🗑️ Deleted **{len(deleted)}** message{'s' if len(deleted) != 1 else ''}.",
        ephemeral=True,
    )

@purge.error
async def purge_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You need **Manage Messages** permission to use this.", ephemeral=True
        )


# ─────────────────────────────────────────────────────────────────────────────
# /checkpinterest
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checkpinterest", description="📌 Check Pinterest username availability")
@app_commands.describe(length="Username length (3–30)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checkpinterest(interaction: discord.Interaction,
                         length: app_commands.Range[int, 3, 30],
                         underscores: app_commands.Choice[str],
                         charset: app_commands.Choice[str],
                         amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, pinterest, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checkyoutube
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checkyoutube", description="▶️ Check YouTube handle availability")
@app_commands.describe(length="Handle length (3–30)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checkyoutube(interaction: discord.Interaction,
                       length: app_commands.Range[int, 3, 30],
                       underscores: app_commands.Choice[str],
                       charset: app_commands.Choice[str],
                       amount: app_commands.Range[int, 1, 100]):
    if not youtube_api_key.available:
        await interaction.response.send_message(
            "⚠️ No YouTube API key loaded. Add it to `tokens/youtube_api_key.txt`.",
            ephemeral=True)
        return
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, youtube, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checktwitch
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checktwitch", description="🟣 Check Twitch username availability")
@app_commands.describe(length="Username length (4–25)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checktwitch(interaction: discord.Interaction,
                      length: app_commands.Range[int, 4, 25],
                      underscores: app_commands.Choice[str],
                      charset: app_commands.Choice[str],
                      amount: app_commands.Range[int, 1, 100]):
    if not twitch_credentials.available:
        await interaction.response.send_message(
            "⚠️ No Twitch credentials loaded. Add them to `tokens/twitch_credentials.txt`.",
            ephemeral=True)
        return
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, twitch, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checkreddit
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checkreddit", description="🤖 Check Reddit username availability")
@app_commands.describe(length="Username length (3–20)", underscores="Allow underscores?", charset="Character set", amount="How many to check (1–50, paid: unlimited)")
@app_commands.choices(underscores=_underscore_choices, charset=_charset_choices)
async def checkreddit(interaction: discord.Interaction,
                      length: app_commands.Range[int, 3, 20],
                      underscores: app_commands.Choice[str],
                      charset: app_commands.Choice[str],
                      amount: app_commands.Range[int, 1, 100]):
    if not await check_cooldown(interaction, _cooldowns_regular, 60): return
    await ask_check_mode(interaction, reddit, length, underscores.value, charset.value, cap_amount(interaction, amount, 50), _cooldowns_regular)


# ─────────────────────────────────────────────────────────────────────────────
# /checknames  — check custom usernames on any platform
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="checknames", description="🔎 Check your own list of usernames on any platform")
@app_commands.describe(
    platform="Which platform to check",
    names="Usernames to check, separated by spaces or new lines (e.g. hello world test)",
)
@app_commands.choices(
    platform=[
        app_commands.Choice(name="⛏️  Minecraft",         value="mc"),
        app_commands.Choice(name="🎮  Roblox",             value="roblox"),
        app_commands.Choice(name="🐙  GitHub",             value="github"),
        app_commands.Choice(name="📸  Instagram",          value="ig"),
        app_commands.Choice(name="🎵  TikTok",             value="tiktok"),
        app_commands.Choice(name="🎲  Steam",              value="steam"),
        app_commands.Choice(name="🕹️  PlayStation",       value="psn"),
        app_commands.Choice(name="🔺  Geometry Dash",     value="gd"),
        app_commands.Choice(name="💬  Discord",           value="discord"),
        app_commands.Choice(name="📌  Pinterest",         value="pinterest"),
        app_commands.Choice(name="▶️  YouTube",           value="youtube"),
        app_commands.Choice(name="🟣  Twitch",            value="twitch"),
        app_commands.Choice(name="🤖  Reddit",            value="reddit"),
    ]
)
async def checknames(
    interaction: discord.Interaction,
    platform: app_commands.Choice[str],
    names: str,
):
    _platform_map = {
        "mc": mc, "roblox": roblox, "github": github, "ig": ig,
        "tiktok": tiktok, "steam": steam, "psn": psn, "gd": gd,
        "discord": discord_checker, "pinterest": pinterest, "youtube": youtube,
        "twitch": twitch, "reddit": reddit,
    }
    mod = _platform_map[platform.value]

    parsed = [n.strip() for n in names.replace("\n", " ").split() if n.strip()]

    if not parsed:
        await interaction.response.send_message("⚠️ No valid usernames found.", ephemeral=True)
        return

    limit = 20 if platform.value == "discord" else 50
    store = _cooldowns_discord if platform.value == "discord" else _cooldowns_regular
    secs  = 3600 if platform.value == "discord" else 60

    if not await check_cooldown(interaction, store, secs): return

    if not has_paid_role(interaction):
        parsed = parsed[:limit]

    await _launch_check(interaction, mod, 5, "no", "letters", len(parsed), store, custom_names=parsed)


# ─────────────────────────────────────────────────────────────────────────────
# /stopcheck
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="stopcheck", description="🛑 Stop the currently running check")
async def stopcheck(interaction: discord.Interaction):
    uid = interaction.user.id
    if uid not in active_checks:
        await interaction.response.send_message("ℹ️ You don't have a check running.", ephemeral=True)
        return
    active_checks[uid].set()
    await interaction.response.send_message("🛑 **Stopping… partial results will be sent shortly.**")


# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.tree.sync()
    dc   = f"{discord_tokens.count} token(s)"      if discord_tokens.available    else "no tokens (unauthed)"
    ig_s = f"{ig_sessions.count} session(s)"       if ig_sessions.available       else "no sessions ⚠️"
    yt   = f"{youtube_api_key.count} key(s)"       if youtube_api_key.available   else "no key ⚠️"
    pin  = f"{pinterest_tokens.count} token(s)"    if pinterest_tokens.available  else "no token (scrape only)"
    tw   = f"{twitch_credentials.count} cred(s)"   if twitch_credentials.available else "no credentials ⚠️"
    print(f"✅ Logged in as {bot.user}")
    print(f"   Discord tokens   : {dc}")
    print(f"   IG sessions      : {ig_s}")
    print(f"   YouTube key      : {yt}")
    print(f"   Pinterest token  : {pin}")
    print(f"   Twitch creds     : {tw}")
    print("   Commands synced.")


async def main():
    async with bot:
        try:
            await bot.load_extension("sessions")
            print("✅ Sessions cog loaded.")
        except Exception as e:
            print(f"❌ Failed to load sessions cog: {e}")
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
