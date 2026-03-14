import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import aiohttp
import random
import string
import os
import asyncio

from checkers import mc, roblox, github, ig, tiktok, steam, psn, gd, discord_checker
from checkers.token_manager import discord_tokens, ig_sessions

# ─────────────────────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# guild_id → asyncio.Event  (set = stop signal)
active_checks: dict[int, asyncio.Event] = {}


# ── Username generator ────────────────────────────────────────────────────────
def gen_names(length: int, underscores: bool, charset: str, amount: int) -> list[str]:
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
        if 3 <= len(name) <= 25:
            names.add(name)
    return list(names)[:amount]


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
):
    gid = interaction.guild_id or interaction.user.id
    available_list, unavailable, unclear = [], 0, 0
    token_msgs: list[str] = []

    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            for username in usernames:
                if stop_event.is_set():
                    break

                raw = await mod.check(session, username)

                # Some checkers return (result, token_status_msg)
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

                await asyncio.sleep(mod.DELAY)

    finally:
        active_checks.pop(gid, None)

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
    store[interaction.user.id] = now
    return True

def cap_amount(interaction: discord.Interaction, amount: int, limit: int) -> int:
    """Caps amount to limit unless user has paid role."""
    if has_paid_role(interaction):
        return amount
    return min(amount, limit)


# ── Guard helper ──────────────────────────────────────────────────────────────
async def start_check(interaction: discord.Interaction, mod, length, underscores, charset, amount):
    gid = interaction.guild_id or interaction.user.id
    if gid in active_checks:
        await interaction.response.send_message(
            "⚠️ A check is already running here. Use `/stopcheck` first.", ephemeral=True)
        return

    names = gen_names(length, underscores == "yes", charset, amount)
    stop  = asyncio.Event()
    active_checks[gid] = stop

    await interaction.response.send_message(
        f"{mod.EMOJI} **{interaction.user.mention}** started `/check{mod.NAME.lower().replace(' ', '')}` "
        f"(length=**{length}**, underscores=**{underscores}**, charset=**{charset}**, amount=**{amount}**)\n"
        f"⏳ Checking… use `/stopcheck` to cancel."
    )
    asyncio.create_task(run_check(interaction, mod, names, stop))


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
    await start_check(interaction, mc, length, underscores.value, charset.value, cap_amount(interaction, amount, 50))


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
    await start_check(interaction, roblox, length, underscores.value, charset.value, cap_amount(interaction, amount, 50))


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
    await start_check(interaction, github, length, underscores.value, charset.value, cap_amount(interaction, amount, 50))


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
    await start_check(interaction, ig, length, underscores.value, charset.value, cap_amount(interaction, amount, 50))


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
    await start_check(interaction, tiktok, length, underscores.value, charset.value, cap_amount(interaction, amount, 50))


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
    await start_check(interaction, steam, length, underscores.value, charset.value, cap_amount(interaction, amount, 50))


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
    await start_check(interaction, psn, length, underscores.value, charset.value, cap_amount(interaction, amount, 50))


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
    await start_check(interaction, gd, length, underscores.value, charset.value, cap_amount(interaction, amount, 50))


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
    await start_check(interaction, discord_checker, length, underscores.value, charset.value, cap_amount(interaction, amount, 20))


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
# /stopcheck
# ─────────────────────────────────────────────────────────────────────────────
@bot.tree.command(name="stopcheck", description="🛑 Stop the currently running check")
async def stopcheck(interaction: discord.Interaction):
    gid = interaction.guild_id or interaction.user.id
    if gid not in active_checks:
        await interaction.response.send_message("ℹ️ No check is running right now.", ephemeral=True)
        return
    active_checks[gid].set()
    await interaction.response.send_message("🛑 **Stopping… partial results will be sent shortly.**")


# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.tree.sync()
    dc = f"{discord_tokens.count} token(s)" if discord_tokens.available else "no tokens (unauthed)"
    ig_s = f"{ig_sessions.count} session(s)" if ig_sessions.available else "no sessions ⚠️"
    print(f"✅ Logged in as {bot.user}")
    print(f"   Discord tokens : {dc}")
    print(f"   IG sessions    : {ig_s}")
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
