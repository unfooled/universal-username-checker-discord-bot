"""
sessions.py — Private checker session system

- /setup  → creates the #get-access channel with the button (run once as admin)
- Members click "Open Checker Session" → permanent private channel created for them
- Only that member + server owner can see it
- They can invite a friend to their channel
- They can delete the channel and create a new one anytime (still 1 at a time)
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands


class OpenSessionButton(discord.ui.View):
    """The big button that lives in #get-access."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔍 Open Checker Session",
        style=discord.ButtonStyle.primary,
        custom_id="open_session",
    )
    async def open_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild  = interaction.guild
        member = interaction.user

        # Block if they already have one open
        existing = discord.utils.get(
            guild.text_channels, name=f"session-{member.name.lower()}"
        )
        if existing:
            await interaction.response.send_message(
                f"⚠️ You already have a session open: {existing.mention}\n"
                f"Delete it first if you want a fresh one.",
                ephemeral=True,
            )
            return

        # Find or create "Sessions" category
        category = discord.utils.get(guild.categories, name="Sessions")
        if not category:
            category = await guild.create_category("Sessions")

        # Hidden from everyone except the member + owner + bot
        bot_member = guild.get_member(interaction.client.user.id)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                use_application_commands=True,
            ),
            guild.owner: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                use_application_commands=True,
            ),
        }
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_permissions=True,
            )

        channel = await guild.create_text_channel(
            name=f"session-{member.name.lower()}",
            category=category,
            overwrites=overwrites,
            topic=f"Private checker session for {member.name}",
        )

        embed = discord.Embed(
            title="🔍 Your Private Checker Session",
            description=(
                f"Welcome {member.mention}! This is your personal checker channel.\n\n"
                "**Available commands:**\n"
                "`/checkmc` · `/checkroblox` · `/checkgithub` · `/checkig`\n"
                "`/checktiktok` · `/checksteam` · `/checkpsn` · `/checkgd` · `/checkdiscord`\n\n"
                "**Buttons below:**\n"
                "➕ Invite a friend to join your session\n"
                "🗑️ Delete this channel (you can always make a new one)"
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Only you and the server owner can see this channel.")

        await channel.send(
            content=member.mention,
            embed=embed,
            view=SessionControlView(),
        )

        await interaction.response.send_message(
            f"✅ Your session channel has been created: {channel.mention}",
            ephemeral=True,
        )


class SessionControlView(discord.ui.View):
    """Buttons pinned inside the private channel."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="➕ Invite a Friend",
        style=discord.ButtonStyle.secondary,
        custom_id="invite_friend",
    )
    async def invite_friend(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only the session owner can invite
        channel_owner_name = interaction.channel.name.replace("session-", "")
        if interaction.user.name.lower() != channel_owner_name:
            await interaction.response.send_message(
                "⚠️ Only the session owner can invite friends.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "📩 **Mention the friend you want to invite** (e.g. `@username`):",
            ephemeral=True,
        )

        # Store pending invite so on_message can pick it up
        if not hasattr(interaction.client, "_pending_invites"):
            interaction.client._pending_invites = {}
        interaction.client._pending_invites[interaction.channel.id] = interaction.user.id

    @discord.ui.button(
        label="🗑️ Delete Channel",
        style=discord.ButtonStyle.danger,
        custom_id="delete_session",
    )
    async def delete_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild              = interaction.guild
        channel_owner_name = interaction.channel.name.replace("session-", "")
        is_session_owner   = interaction.user.name.lower() == channel_owner_name
        is_server_owner    = interaction.user.id == guild.owner_id

        if not (is_session_owner or is_server_owner):
            await interaction.response.send_message(
                "⚠️ Only the session owner or server owner can delete this channel.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "🗑️ Deleting channel in 3 seconds… You can open a new one anytime!"
        )
        await asyncio.sleep(3)
        await interaction.channel.delete(reason=f"Session deleted by {interaction.user.name}")


class Sessions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register persistent views so buttons survive bot restarts
        bot.add_view(OpenSessionButton())
        bot.add_view(SessionControlView())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle friend invite — user mentions someone after clicking Invite."""
        if message.author.bot:
            return
        pending = getattr(self.bot, "_pending_invites", {})
        if message.channel.id not in pending:
            return
        if message.author.id != pending[message.channel.id]:
            return
        if not message.mentions:
            return

        invited = message.mentions[0]
        channel = message.channel

        await channel.set_permissions(
            invited,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            use_application_commands=True,
        )

        del pending[message.channel.id]
        await message.delete()

        embed = discord.Embed(
            description=f"✅ {invited.mention} has been added to this session!",
            color=0x57F287,
        )
        await channel.send(embed=embed)

    @app_commands.command(
        name="setup",
        description="⚙️ Set up the #get-access channel (run once, admin only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        # Find or create a "Checker Bot" category
        category = discord.utils.get(guild.categories, name="Checker Bot")
        if not category:
            category = await guild.create_category("Checker Bot")

        # Create #get-access if it doesn't exist
        existing = discord.utils.get(guild.text_channels, name="get-access")
        if existing:
            await interaction.followup.send(
                f"⚠️ #get-access already exists: {existing.mention}", ephemeral=True
            )
            return

        channel = await guild.create_text_channel(
            name="get-access",
            category=category,
            topic="Click the button to open your private checker session!",
        )
        # Make it read-only for everyone
        await channel.set_permissions(guild.default_role, send_messages=False, view_channel=True)

        embed = discord.Embed(
            title="🔍 Username Checker — Get Access",
            description=(
                "Click the button below to open your **private checker session**.\n\n"
                "Your session is a private channel only **you** can see.\n"
                "Run any check command inside it, invite a friend, or delete it anytime.\n\n"
                "**One session per user.**"
            ),
            color=0x5865F2,
        )

        await channel.send(embed=embed, view=OpenSessionButton())
        await interaction.followup.send(
            f"✅ Setup complete! Check out {channel.mention}", ephemeral=True
        )

    @setup.error
    async def setup_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need **Administrator** permission to run this.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Sessions(bot))
