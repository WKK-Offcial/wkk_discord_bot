from __future__ import annotations

import logging
import sys
from typing import Literal, Optional, cast

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context, Greedy
from discord_bot import DiscordBot


class AdminCog(commands.Cog):
    """
    Class used for administrative bot commands.
    """

    def __init__(self, bot: DiscordBot) -> None:
        super().__init__()
        self.bot = bot

        @self.bot.command()
        @commands.guild_only()
        async def sync(
            ctx: Context, guilds: Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None
        ) -> None:
            """
            Syncs slash commands with Discord.

            Parameters:
                guilds (Greedy[discord.Object]): Guilds to sync the commands to.
                spec (Literal["~", "*", "^"], optional): Syncing option:
                    - "~": Sync only to the current guild.
                    - "*": Copy global commands to the current guild.
                    - "^": Clear commands from the current guild.
                    - None: Sync globally.
            """
            bot = cast(DiscordBot, ctx.bot)

            # Handle syncing based on spec and guilds
            if not guilds:
                if spec == "~":
                    synced = await bot.tree.sync(guild=ctx.guild)
                    location = "to the current guild"
                elif spec == "*":
                    bot.tree.copy_global_to(guild=ctx.guild)
                    synced = await bot.tree.sync(guild=ctx.guild)
                    location = "to the current guild (including global commands)"
                elif spec == "^":
                    bot.tree.clear_commands(guild=ctx.guild)
                    await bot.tree.sync(guild=ctx.guild)
                    synced = []
                    location = "after clearing commands from the current guild"
                else:
                    synced = await bot.tree.sync()
                    location = "globally"

                await ctx.send(f"Synced {len(synced)} commands {location}.")
                return

            # Sync to specific guilds
            successful_syncs = 0
            for guild in guilds:
                try:
                    await bot.tree.sync(guild=guild)
                except discord.HTTPException:
                    continue
                else:
                    successful_syncs += 1

            await ctx.send(f"Synced the tree to {successful_syncs}/{len(guilds)} guilds.")

    @commands.guild_only()
    @app_commands.command(name="restart")
    async def restart_bot(self, interaction: discord.Interaction) -> None:
        """
        Restarts the bot by exiting the program, which should trigger a container reboot.

        Parameters:
            interaction (discord.Interaction): The interaction triggering the command.
        """
        await interaction.response.send_message(content="BRB")
        logging.warning("Restart called from guild: %d", interaction.guild.id)
        sys.exit()
