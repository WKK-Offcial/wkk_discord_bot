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
    Class used for administrative bot commands
    """

    def __init__(self, bot: DiscordBot) -> None:
        super().__init__()
        self.bot: DiscordBot = bot

        # Implement meta functions
        @self.bot.command()
        @commands.guild_only()
        async def sync(
            ctx: Context, guilds: Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None
        ) -> None:
            """
            This command sync slash commands with discord
            """
            bot = cast(DiscordBot, ctx.bot)
            if not guilds:
                if spec == "~":
                    synced = await bot.tree.sync(guild=ctx.guild)
                elif spec == "*":
                    bot.tree.copy_global_to(guild=ctx.guild)
                    synced = await bot.tree.sync(guild=ctx.guild)
                elif spec == "^":
                    bot.tree.clear_commands(guild=ctx.guild)
                    await bot.tree.sync(guild=ctx.guild)
                    synced = []
                else:
                    synced = await bot.tree.sync()

                is_spec = 'globally' if spec is None else 'to the current guild.'
                await ctx.send(f"Synced {len(synced)} commands {is_spec}")
                return

            ret = 0
            for guild in guilds:
                try:
                    await bot.tree.sync(guild=guild)
                except discord.HTTPException:
                    pass
                else:
                    ret += 1

            await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

    @commands.guild_only()
    @app_commands.command(name="restart")
    async def restart_bot(self, interaction: discord.Interaction, member: discord.Member = None) -> None:
        """
        This command exits the program which should automatically reboot the container
        """
        await interaction.response.send_message(content="BRB")
        logging.warning('Restart called from %d', interaction.guild.id)
        sys.exit()
