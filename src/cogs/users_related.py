from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from main import DiscordBot


class UsersRelated(commands.Cog):
    """
    Class for commands related with users
    """

    def __init__(self, bot: DiscordBot) -> None:
        super().__init__()
        self.bot: DiscordBot = bot

    @app_commands.command(name="avatar")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None) -> None:
        """
        Command to get user avatar
        """
        avatar_url = member.avatar.url
        embed = discord.Embed()
        embed.set_image(url=avatar_url)
        await interaction.response.send_message(embed=embed)
